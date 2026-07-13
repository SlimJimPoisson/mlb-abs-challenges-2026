#!/usr/bin/env python3
"""
Pull every ABS challenge of the 2026 MLB season from the public StatsAPI game feed,
join each challenge to its pitch coordinates, and compute miss distance from the zone edge.

Design goals:
  - Cheap & re-runnable: every game feed is cached to feeds/<gamePk>.json. Re-runs only
    fetch new/incomplete games. Network is the only cost; parsing is local.
  - Honest geometry: StatsAPI's per-pitch strikeZoneTop/Bottom is STANCE-based, not the ABS
    zone. ABS uses a fixed % of batter height (bottom 27%, top 55%; see ABS_TOP_PCT) at the plate midpoint.
    We store the raw coords + both zone definitions, and report how well each predicts the
    actual ABS verdict so the distances can be trusted before anyone leans on them.

Outputs:
  challenges.csv   one row per challenge
  abs.sqlite       same data, queryable
"""
import json, csv, sqlite3, urllib.request, concurrent.futures as cf
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEEDS = ROOT / "feeds"
FEEDS.mkdir(exist_ok=True)

SEASON_START = "2026-03-15"          # spring/opening cushion; schedule filter does the real work
SEASON_END   = "2026-07-12"
HALF_PLATE_FT = 17.0 / 2 / 12        # plate half-width in feet (0.708)
BALL_R_FT = 1.45 / 12                 # baseball radius; ABS = strike if ball clips the zone
# Calibrated against 3,568 actual 2026 verdicts (88.1% match on all-borderline pitches):
ABS_BOT_PCT, ABS_TOP_PCT = 0.27, 0.55    # 2026 ABS zone as fraction of batter height
REVIEW_TYPE = "MJ"                   # ABS ball/strike challenge review type in StatsAPI

def get_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "abs-pull/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def final_games():
    url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R"
           f"&startDate={SEASON_START}&endDate={SEASON_END}")
    sched = get_json(url)
    out = []
    for d in sched.get("dates", []):
        for g in d["games"]:
            if g["status"]["abstractGameState"] == "Final":
                out.append((g["gamePk"], d["date"]))
    return out

def feed_path(gpk): return FEEDS / f"{gpk}.json"

def fetch_feed(gpk):
    p = feed_path(gpk)
    if p.exists() and p.stat().st_size > 1000:
        return  # cached
    data = get_json(f"https://statsapi.mlb.com/api/v1.1/game/{gpk}/feed/live")
    p.write_text(json.dumps(data), encoding="utf-8")

def heights_inches(person_ids):
    """Batch-fetch batter heights -> inches. height looks like \"6' 2\\\"\"."""
    out = {}
    ids = [str(i) for i in person_ids if i]
    for i in range(0, len(ids), 100):
        chunk = ids[i:i+100]
        data = get_json("https://statsapi.mlb.com/api/v1/people?personIds=" + ",".join(chunk))
        for p in data.get("people", []):
            h = p.get("height", "")
            try:
                ft, inch = h.replace('"', '').split("'")
                out[p["id"]] = int(ft) * 12 + int(inch.strip())
            except Exception:
                pass
    return out

def entering_states(live):
    """Per-play base/out/score state ENTERING the at-bat (reconstructed forward)."""
    st = {}; last_half = None; outs = 0; runners = (False, False, False); a = h = 0
    for pi, play in enumerate(live):
        ab = play.get("about", {}); hk = (ab.get("inning"), ab.get("halfInning"))
        if hk != last_half:
            outs = 0; runners = (False, False, False); last_half = hk
        st[pi] = {"outs": outs, "on1": runners[0], "on2": runners[1], "on3": runners[2], "a": a, "h": h}
        outs = play.get("count", {}).get("outs", outs)
        mm = play.get("matchup", {})
        runners = (mm.get("postOnFirst") is not None, mm.get("postOnSecond") is not None, mm.get("postOnThird") is not None)
        rr = play.get("result", {}); a = rr.get("awayScore", a); h = rr.get("homeScore", h)
    return st

def parse_game(gpk, date):
    data = json.loads(feed_path(gpk).read_text(encoding="utf-8"))
    live = data["liveData"]["plays"]["allPlays"]
    teams = data["gameData"]["teams"]
    home_id, away_id = teams["home"]["id"], teams["away"]["id"]
    states = entering_states(live)
    rows = []
    for pi, play in enumerate(live):
        about = play.get("about", {})
        half = about.get("halfInning")           # 'top' => away bats, 'bottom' => home bats
        batting_team = away_id if half == "top" else home_id
        m = play.get("matchup", {})
        evlist = play.get("playEvents", [])
        pitch_idxs = [i for i, e in enumerate(evlist) if e.get("isPitch")]
        res = play.get("result", {})
        nxt = live[pi + 1] if pi + 1 < len(live) else None
        reached = res.get("eventType") in ("walk", "hit_by_pitch", "single", "double",
            "triple", "home_run", "intent_walk", "field_error", "catcher_interf")
        # --- UNION extraction: capture EVERY distinct challenge in the at-bat. A challenge
        #     is recorded at the pitch level (at-bat continued) OR at the play level
        #     (at-bat-ending / terminal). An at-bat can hold more than one (e.g. the batter
        #     challenges one pitch, the defense another) — emit a row for each. ---
        units = [(i, e, e["reviewDetails"], False) for i, e in enumerate(evlist)
                 if e.get("reviewDetails", {}).get("reviewType") == REVIEW_TYPE and e.get("isPitch")]
        play_rd = play.get("reviewDetails")
        play_mj = play_rd if (play_rd or {}).get("reviewType") == REVIEW_TYPE else None
        if play_mj and pitch_idxs:               # terminal play-level review, unless it dups a pitch one
            dup = any(rd.get("challengeTeamId") == play_mj.get("challengeTeamId")
                      and rd.get("isOverturned") == play_mj.get("isOverturned") for _, _, rd, _ in units)
            if not dup:
                li = pitch_idxs[-1]; units.append((li, evlist[li], play_mj, True))
        for ei, ev, rd, terminal_chal in units:
            pd = ev.get("pitchData", {}); c = pd.get("coordinates", {})
            if c.get("pX") is None or c.get("pZ") is None:
                continue
            # PRE-pitch count: walk prior pitches in this at-bat
            pb = ps = 0
            for e in evlist[:ei]:
                if not e.get("isPitch"): continue
                d = e.get("details", {})
                if d.get("isBall"): pb += 1
                elif d.get("isStrike") and ps < 2: ps += 1
            ch_team = rd.get("challengeTeamId")
            side = "batter" if ch_team == batting_team else "defense"
            chal = rd.get("player") or {}
            est = states.get(pi, {})
            bat_score = est.get("a", 0) if half == "top" else est.get("h", 0)
            fld_score = est.get("h", 0) if half == "top" else est.get("a", 0)
            det = ev.get("details", {})
            cnt = ev.get("count", {})
            rows.append({
                "gamePk": gpk, "date": date, "inning": about.get("inning"),
                "half": half, "side": side, "challengeTeamId": ch_team,
                "challengerId": chal.get("id"), "challenger": chal.get("fullName"),
                "pre_balls": pb, "pre_strikes": ps, "outs": est.get("outs"),
                "on1": est.get("on1"), "on2": est.get("on2"), "on3": est.get("on3"),
                "bat_score": bat_score, "fld_score": fld_score, "score_diff": bat_score - fld_score,
                "batSide": (m.get("batSide") or {}).get("code"), "pitchHand": (m.get("pitchHand") or {}).get("code"),
                "pitchType": det.get("type", {}).get("code"),
                "pa_event": res.get("event"), "pa_eventType": res.get("eventType"),
                "terminal_chal": terminal_chal,
                "is_terminal": (ei == pitch_idxs[-1]) and bool(res.get("eventType")),
                "reached_base": reached,
                "ended_inning": (nxt is None or nxt.get("about", {}).get("halfInning") != half
                                 or nxt.get("about", {}).get("inning") != about.get("inning")),
                "batter": m.get("batter", {}).get("fullName"),
                "batterId": m.get("batter", {}).get("id"),
                "pitcher": m.get("pitcher", {}).get("fullName"),
                "pitcherId": m.get("pitcher", {}).get("id"),
                "callCode": det.get("call", {}).get("code"),
                "call": det.get("call", {}).get("description"),
                "overturned": rd.get("isOverturned"),
                "pX": c["pX"], "pZ": c["pZ"],
                "szTop": pd.get("strikeZoneTop"), "szBot": pd.get("strikeZoneBottom"),
                "startSpeed": pd.get("startSpeed"),
            })
    return rows

def add_geometry(rows, heights):
    for r in rows:
        pX, pZ = r["pX"], r["pZ"]
        # horizontal miss from the ABS strike boundary (plate edge + ball radius). + = outside/ball.
        r["horiz_off_in"] = round((abs(pX) - (HALF_PLATE_FT + BALL_R_FT)) * 12, 2)
        # vertical via StatsAPI stance zone (reference only)
        szt, szb = r["szTop"], r["szBot"]
        r["vert_off_sz_in"] = round(max(szb - pZ, pZ - szt) * 12, 2) if szt and szb else None
        # vertical via calibrated ABS height-based zone (+ ball radius on top/bottom edges)
        h = heights.get(r["batterId"])
        if h:
            abs_top = ABS_TOP_PCT * h / 12.0   # ft
            abs_bot = ABS_BOT_PCT * h / 12.0
            r["abs_top_ft"] = round(abs_top, 3); r["abs_bot_ft"] = round(abs_bot, 3)
            r["vert_off_abs_in"] = round(max((abs_bot - BALL_R_FT) - pZ, pZ - (abs_top + BALL_R_FT)) * 12, 2)
            # signed miss from the nearest ABS strike boundary: + = ball (outside), - = strike (inside)
            r["miss_off_edge_in"] = round(max(r["horiz_off_in"], r["vert_off_abs_in"]), 2)
            r["pred_strike"] = (abs(pX) <= HALF_PLATE_FT + BALL_R_FT
                                and abs_bot - BALL_R_FT <= pZ <= abs_top + BALL_R_FT)
        else:
            r["abs_top_ft"] = r["abs_bot_ft"] = r["vert_off_abs_in"] = None
            r["miss_off_edge_in"] = r["pred_strike"] = None
        # the displayed call IS the final (post-challenge) ABS ruling; no flip needed
        r["abs_verdict_strike"] = (r["callCode"] == "C")
    return rows

def main():
    print("Fetching schedule...", flush=True)
    games = final_games()
    print(f"Final regular-season games {SEASON_START}..{SEASON_END}: {len(games)}", flush=True)
    # fetch feeds (cached) concurrently
    todo = [g for g in games if not (feed_path(g[0]).exists() and feed_path(g[0]).stat().st_size > 1000)]
    print(f"  need to fetch {len(todo)} feeds ({len(games)-len(todo)} cached)")
    done = 0; total = len(todo)
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_feed, g[0]): g[0] for g in todo}
        for f in cf.as_completed(futs):
            done += 1
            try: f.result()
            except Exception as e: print("  fetch fail", futs[f], e, flush=True)
            if done % 25 == 0 or done == total:
                print(f"  [fetch] {done}/{total} feeds ({done/total*100:.0f}%)", flush=True)
    # parse
    rows = []
    for i, (gpk, date) in enumerate(games, 1):
        try: rows.extend(parse_game(gpk, date))
        except Exception as e: print("  parse fail", gpk, e, flush=True)
        if i % 200 == 0 or i == len(games):
            print(f"  [parse] {i}/{len(games)} games -> {len(rows)} challenges so far", flush=True)
    print(f"Challenges parsed: {len(rows)}", flush=True)
    # heights for ABS zone
    hts = heights_inches({r["batterId"] for r in rows})
    rows = add_geometry(rows, hts)

    # write CSV
    cols = ["gamePk","date","inning","half","side","challengeTeamId","challengerId","challenger","batter","batterId",
            "pre_balls","pre_strikes","outs","on1","on2","on3","bat_score","fld_score","score_diff",
            "batSide","pitchHand","pitchType",
            "pa_event","pa_eventType","terminal_chal","is_terminal","reached_base","ended_inning",
            "pitcher","pitcherId","callCode","call","overturned","abs_verdict_strike",
            "pX","pZ","szTop","szBot","abs_top_ft","abs_bot_ft","startSpeed",
            "horiz_off_in","vert_off_sz_in","vert_off_abs_in","miss_off_edge_in","pred_strike"]
    with open(ROOT/"challenges.csv","w",newline="",encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({k:r.get(k) for k in cols})
    # write sqlite
    con = sqlite3.connect(ROOT/"abs.sqlite"); con.execute("DROP TABLE IF EXISTS challenges")
    con.execute(f"CREATE TABLE challenges ({','.join(cols)})")
    con.executemany(f"INSERT INTO challenges VALUES ({','.join('?'*len(cols))})",
                    [[r.get(k) for k in cols] for r in rows])
    con.commit(); con.close()

    # ---- summary + zone-model validation ----
    n = len(rows); ov = sum(1 for r in rows if r["overturned"])
    bat = [r for r in rows if r["side"]=="batter"]; deff = [r for r in rows if r["side"]=="defense"]
    print(f"\n=== SUMMARY ===")
    print(f"challenges={n}  overturned={ov} ({ov/n*100:.1f}%)  upheld={(n-ov)/n*100:.1f}%")
    print(f"batter-initiated={len(bat)} overturn {sum(r['overturned'] for r in bat)/max(len(bat),1)*100:.1f}%")
    print(f"defense-initiated={len(deff)} overturn {sum(r['overturned'] for r in deff)/max(len(deff),1)*100:.1f}%")
    valid = [r for r in rows if r["pred_strike"] is not None]
    match = sum(1 for r in valid if r["pred_strike"] == r["abs_verdict_strike"])
    print(f"\nABS zone model check: predicted call matches actual ABS verdict on "
          f"{match}/{len(valid)} = {match/max(len(valid),1)*100:.1f}% (heights found for {len(hts)} batters)")
    miss_ov = [abs(min(r['horiz_off_in'], r.get('vert_off_abs_in') or 99)) for r in valid if r['overturned']]
    print(f"\nWrote challenges.csv and abs.sqlite to {ROOT}")

if __name__ == "__main__":
    main()
