"""
'Should have been challenged': taken pitches the umpire clearly got wrong by the ABS
zone, that nobody challenged (while a challenge was still available).

Independent of the challenge log — computes the ABS verdict on every taken pitch from
raw coordinates, so the play-level/pitch-level encoding issue is irrelevant here.
"""
import json, sys, csv, sqlite3
from pathlib import Path
from collections import Counter, defaultdict
from abs_pull import heights_inches, HALF_PLATE_FT, BALL_R_FT, ABS_BOT_PCT, ABS_TOP_PCT, entering_states
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parent
FEEDS = ROOT / "feeds"
MARGIN = 1.5     # lower bound: beat model (~1") + Hawk-Eye (~0.5") noise
MARGIN_HI = 6.0  # upper bound: beyond this is a tracking glitch, not a real call

def collect():
    pitches = []           # taken, non-reviewed pitches
    batter_ids = set()
    for fp in FEEDS.glob("*.json"):
        try: d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception: continue
        g = d["gameData"]["teams"]; home, away = g["home"]["id"], g["away"]["id"]
        gpk = d["gamePk"]; date = (d["gameData"].get("datetime", {}) or {}).get("officialDate", "")
        avail = {home: 2, away: 2}       # available challenges; 2/game, retained on success
        cur_inn = 0
        live = d["liveData"]["plays"]["allPlays"]; states = entering_states(live)
        for pi, play in enumerate(live):
            inn = play["about"]["inning"]
            if inn != cur_inn:           # extra-inning bonus: >=1 each extra inning, non-accumulating
                cur_inn = inn
                if inn >= 10:
                    for tt in (home, away): avail[tt] = max(avail[tt], 1)
            evl = play.get("playEvents", [])
            half = play["about"]["halfInning"]
            bat_team = away if half == "top" else home
            fld_team = home if half == "top" else away
            est = states.get(pi, {})
            score_diff = (est.get("a", 0) - est.get("h", 0)) if half == "top" else (est.get("h", 0) - est.get("a", 0))
            m = play.get("matchup", {})
            reviewed_pitch = any(e.get("reviewDetails", {}).get("reviewType") == "MJ" and e.get("isPitch") for e in evl)
            play_reviewed = (play.get("reviewDetails") or {}).get("reviewType") == "MJ"
            pb = ps = 0
            for ev in evl:
                if not ev.get("isPitch"):
                    continue
                det = ev.get("details", {}); code = det.get("call", {}).get("code")
                c = ev.get("pitchData", {}).get("coordinates", {})
                is_taken = code in ("C", "B")
                # only judge taken, *un-reviewed* pitches with coordinates
                if is_taken and not reviewed_pitch and not play_reviewed and c.get("pX") is not None:
                    bid = m.get("batter", {}).get("id"); batter_ids.add(bid)
                    pitches.append({
                        "gpk": gpk, "date": date, "inning": play["about"]["inning"], "half": half,
                        "code": code, "pX": c["pX"], "pZ": c["pZ"], "bid": bid,
                        "batter": m.get("batter", {}).get("fullName"),
                        "pitcher": m.get("pitcher", {}).get("fullName"),
                        "pre_b": pb, "pre_s": ps,
                        "bat_team": bat_team, "fld_team": fld_team,
                        "bat_rem": avail[bat_team], "fld_rem": avail[fld_team],
                        "score_diff": score_diff,
                    })
                # advance running count
                if det.get("isBall"): pb += 1
                elif det.get("isStrike") and ps < 2: ps += 1
            # after the play: if it carried a challenge that failed, decrement that team
            rd = play.get("reviewDetails") or next((e.get("reviewDetails") for e in evl
                  if e.get("reviewDetails", {}).get("reviewType") == "MJ"), None)
            if rd and rd.get("reviewType") == "MJ" and not rd.get("isOverturned"):
                t = rd.get("challengeTeamId")
                if t in avail: avail[t] = max(0, avail[t] - 1)
    return pitches, batter_ids

def main():
    pitches, bids = collect()
    print(f"taken, un-reviewed pitches: {len(pitches):,}  | distinct batters: {len(bids)}")
    H = heights_inches(bids)
    print(f"heights found: {len(H)}")
    missed = []
    for p in pitches:
        h = H.get(p["bid"])
        if not h: continue
        horiz = (abs(p["pX"]) - (HALF_PLATE_FT + BALL_R_FT)) * 12
        top = ABS_TOP_PCT * h / 12.0; bot = ABS_BOT_PCT * h / 12.0
        vert = max((bot - BALL_R_FT) - p["pZ"], p["pZ"] - (top + BALL_R_FT)) * 12
        miss = max(horiz, vert)               # + = outside zone, - = inside
        abs_strike = miss < 0
        ump_strike = p["code"] == "C"
        if abs_strike == ump_strike:
            continue                          # ump agreed with ABS
        # disagreement; require clear margin to count as a real miss
        depth = abs(miss)
        if not (MARGIN <= depth <= MARGIN_HI): continue
        if ump_strike:    # ump said strike, ABS says ball -> BATTER robbed; batter would challenge
            wronged, role, rem = p["batter"], "batter robbed (called strike was a ball)", p["bat_rem"]
        else:             # ump said ball, ABS says strike -> DEFENSE missed; they'd challenge
            wronged, role, rem = p["pitcher"], "defense missed (called ball was a strike)", p["fld_rem"]
        p.update(depth=round(depth, 2), role=role, wronged=wronged, had_challenge=rem > 0,
                 resp_team=(p["bat_team"] if ump_strike else p["fld_team"]))
        missed.append(p)
    print(f"\nclear missed calls (>= {MARGIN}\" past edge, un-challenged): {len(missed):,}")
    avail = [m for m in missed if m["had_challenge"]]
    print(f"  ...of which a challenge WAS available (truly 'should have'): {len(avail):,}")
    print(f"  rate per game (~1161 games): {len(avail)/1161:.1f} per game")
    bdir = Counter(m["role"] for m in avail)
    for k, v in bdir.items(): print(f"    {k}: {v}")
    # terminal pain: a called strike-three that was actually a ball, un-challenged
    k3 = [m for m in avail if m["role"].startswith("batter") and m["pre_s"] == 2]
    print(f"\n  un-challenged strike-THREES that were actually balls (free strikeouts given away): {len(k3)}")
    print("  most egregious of those:")
    for m in sorted(k3, key=lambda x: -x["depth"])[:8]:
        print(f"    {m['batter']:<20} {m['depth']:.1f}\" off  {m['pre_b']}-{m['pre_s']}  {m['date']} vs {m['pitcher']}")
    print("\n  most egregious missed call overall:")
    for m in sorted(avail, key=lambda x: -x["depth"])[:8]:
        print(f"    {m['depth']:5.1f}\"  {m['role'][:24]:<24} {m['wronged']:<18} {m['pre_b']}-{m['pre_s']} {m['date']}")
    # who's victimized / who fails to challenge
    print("\n  batters most often robbed (called K-zone balls, had challenge):")
    rob = Counter(m["batter"] for m in avail if m["role"].startswith("batter"))
    for n, c in rob.most_common(8): print(f"    {n}: {c}")
    # write csv
    with open(ROOT / "missed_calls.csv", "w", newline="", encoding="utf-8") as fh:
        cols = ["date","gpk","inning","role","wronged","batter","pitcher","pre_b","pre_s","depth","had_challenge","resp_team","score_diff","pX","pZ"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for m in missed: w.writerow(m)
    print(f"\nwrote missed_calls.csv ({len(missed)} rows)")

if __name__ == "__main__":
    main()
