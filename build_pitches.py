"""Build the persisted all-taken-pitch table (`pitches`) in abs.sqlite, with ABS verdict,
leverage, handedness, pitch type/velo, HP umpire, and challenge flags. The shared foundation
for ump grades, should-haves, and zone-shape work."""
import json, sys, sqlite3
from pathlib import Path
from abs_pull import entering_states, heights_inches, HALF_PLATE_FT, BALL_R_FT, ABS_BOT_PCT, ABS_TOP_PCT
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; FEEDS = ROOT / "feeds"

def collect():
    rows = []; bids = set()
    files = list(FEEDS.glob("*.json")); n = len(files)
    for k, fp in enumerate(files, 1):
        if k % 200 == 0: print(f"  [parse] {k}/{n}", flush=True)
        try: d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception: continue
        gpk = d["gamePk"]; date = (d["gameData"].get("datetime", {}) or {}).get("officialDate", "")
        ump = next((o["official"] for o in d["liveData"].get("boxscore", {}).get("officials", [])
                    if o.get("officialType") == "Home Plate"), {})
        live = d["liveData"]["plays"]["allPlays"]; states = entering_states(live)
        g = d["gameData"]["teams"]; home, away = g["home"]["id"], g["away"]["id"]
        for pi, play in enumerate(live):
            evl = play.get("playEvents", []); m = play.get("matchup", {})
            ab = play.get("about", {}); half = ab.get("halfInning")
            est = states.get(pi, {})
            bat_score = est.get("a", 0) if half == "top" else est.get("h", 0)
            fld_score = est.get("h", 0) if half == "top" else est.get("a", 0)
            play_rd = play.get("reviewDetails") if (play.get("reviewDetails") or {}).get("reviewType") == "MJ" else None
            last_pitch_i = max((i for i, e in enumerate(evl) if e.get("isPitch")), default=-1)
            pb = ps = 0
            for ei, ev in enumerate(evl):
                if not ev.get("isPitch"):
                    continue
                det = ev.get("details", {}); code = det.get("call", {}).get("code")
                c = ev.get("pitchData", {}).get("coordinates", {})
                if code in ("C", "B") and c.get("pX") is not None:
                    pitch_rd = ev.get("reviewDetails") if (ev.get("reviewDetails") or {}).get("reviewType") == "MJ" else None
                    rd = pitch_rd or (play_rd if ei == last_pitch_i else None)
                    reviewed = rd is not None
                    final_strike = code == "C"
                    ump_strike = (not final_strike) if (rd and rd.get("isOverturned")) else final_strike
                    bid = m.get("batter", {}).get("id"); bids.add(bid)
                    rows.append({
                        "gamePk": gpk, "date": date, "inning": ab.get("inning"), "half": half,
                        "umpId": ump.get("id"), "ump": ump.get("fullName"),
                        "batterId": bid, "batter": m.get("batter", {}).get("fullName"),
                        "pitcherId": m.get("pitcher", {}).get("id"), "pitcher": m.get("pitcher", {}).get("fullName"),
                        "batSide": (m.get("batSide") or {}).get("code"), "pitchHand": (m.get("pitchHand") or {}).get("code"),
                        "pre_balls": pb, "pre_strikes": ps, "outs": est.get("outs"),
                        "on1": est.get("on1"), "on2": est.get("on2"), "on3": est.get("on3"),
                        "score_diff": bat_score - fld_score,
                        "pitchType": det.get("type", {}).get("code"),
                        "startSpeed": ev.get("pitchData", {}).get("startSpeed"),
                        "pX": c["pX"], "pZ": c["pZ"], "ump_strike": int(ump_strike),
                        "reviewed": int(reviewed),
                    })
                if det.get("isBall"): pb += 1
                elif det.get("isStrike") and ps < 2: ps += 1
    return rows, bids

def main():
    print("parsing feeds for all taken pitches...", flush=True)
    rows, bids = collect()
    print(f"taken pitches: {len(rows):,} | batters: {len(bids)}", flush=True)
    H = heights_inches(bids)
    out = []
    for r in rows:
        h = H.get(r["batterId"])
        if not h:
            continue
        horiz = (abs(r["pX"]) - (HALF_PLATE_FT + BALL_R_FT)) * 12
        top = ABS_TOP_PCT * h / 12.0; bot = ABS_BOT_PCT * h / 12.0
        vert = max((bot - BALL_R_FT) - r["pZ"], r["pZ"] - (top + BALL_R_FT)) * 12
        miss = max(horiz, vert)
        r["miss_off_edge_in"] = round(miss, 2)
        r["abs_strike"] = int(miss < 0)
        r["correct"] = int((miss < 0) == bool(r["ump_strike"]))
        out.append(r)
    cols = ["gamePk","date","inning","half","umpId","ump","batterId","batter","pitcherId","pitcher",
            "batSide","pitchHand","pre_balls","pre_strikes","outs","on1","on2","on3","score_diff",
            "pitchType","startSpeed","pX","pZ","ump_strike","reviewed","miss_off_edge_in","abs_strike","correct"]
    con = sqlite3.connect(ROOT / "abs.sqlite")
    con.execute("DROP TABLE IF EXISTS pitches")
    con.execute(f"CREATE TABLE pitches ({','.join(cols)})")
    con.executemany(f"INSERT INTO pitches VALUES ({','.join('?'*len(cols))})",
                    [[r.get(k) for k in cols] for r in out])
    con.execute("CREATE INDEX ix_ump ON pitches(umpId)")
    con.execute("CREATE INDEX ix_bat ON pitches(batterId)")
    con.commit()
    acc = sum(r["correct"] for r in out) / len(out)
    print(f"persisted `pitches`: {len(out):,} rows (heights matched) | league call accuracy {acc*100:.1f}%", flush=True)
    con.close()

if __name__ == "__main__":
    main()
