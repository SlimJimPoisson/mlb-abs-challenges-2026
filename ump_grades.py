"""
Umpire ball/strike accuracy grades from the ABS zone — independent of challenges.
Grades every taken pitch's ORIGINAL umpire call against the calibrated ABS zone.
(For challenged pitches the feed shows the corrected call, so we reverse overturns
to recover what the ump actually called.)
"""
import json, sys, csv
from pathlib import Path
from collections import defaultdict
from abs_pull import heights_inches, HALF_PLATE_FT, BALL_R_FT, ABS_BOT_PCT, ABS_TOP_PCT
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parent
FEEDS = ROOT / "feeds"

def collect():
    pitches = []; bids = set()
    for fp in FEEDS.glob("*.json"):
        try: d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception: continue
        ump = next((o["official"] for o in d["liveData"].get("boxscore", {}).get("officials", [])
                    if o.get("officialType") == "Home Plate"), None)
        if not ump: continue
        for play in d["liveData"]["plays"]["allPlays"]:
            evl = play.get("playEvents", [])
            play_rd = play.get("reviewDetails") if (play.get("reviewDetails") or {}).get("reviewType") == "MJ" else None
            m = play.get("matchup", {})
            for ev in evl:
                if not ev.get("isPitch"): continue
                det = ev.get("details", {}); code = det.get("call", {}).get("code")
                if code not in ("C", "B"): continue        # taken pitches only
                c = ev.get("pitchData", {}).get("coordinates", {})
                if c.get("pX") is None: continue
                rd = ev.get("reviewDetails") if (ev.get("reviewDetails") or {}).get("reviewType") == "MJ" else None
                # original ump call: reverse an overturn
                final_strike = code == "C"
                overturned = (rd or (play_rd if ev is evl[max(i for i,e in enumerate(evl) if e.get("isPitch"))] else None) or {}).get("isOverturned", False)
                ump_strike = (not final_strike) if overturned else final_strike
                bid = m.get("batter", {}).get("id"); bids.add(bid)
                pitches.append({"ump": ump["fullName"], "umpId": ump["id"], "bid": bid,
                                "pX": c["pX"], "pZ": c["pZ"], "ump_strike": ump_strike})
    return pitches, bids

def main():
    pitches, bids = collect()
    H = heights_inches(bids)
    print(f"taken calls: {len(pitches):,} | umps: {len(set(p['umpId'] for p in pitches))} | heights: {len(H)}")
    agg = defaultdict(lambda: {"n":0,"ok":0,"bn":0,"bok":0,"fs":0,"fb":0})  # totals + borderline + false strike/ball
    for p in pitches:
        h = H.get(p["bid"]);
        if not h: continue
        horiz = (abs(p["pX"]) - (HALF_PLATE_FT + BALL_R_FT)) * 12
        top = ABS_TOP_PCT*h/12.0; bot = ABS_BOT_PCT*h/12.0
        vert = max((bot-BALL_R_FT)-p["pZ"], p["pZ"]-(top+BALL_R_FT)) * 12
        miss = max(horiz, vert)                 # + outside (ball), - inside (strike)
        abs_strike = miss < 0
        a = agg[(p["umpId"], p["ump"])]
        a["n"] += 1
        correct = (abs_strike == p["ump_strike"])
        if correct: a["ok"] += 1
        else:
            if p["ump_strike"]: a["fs"] += 1      # called strike, was ball
            else: a["fb"] += 1                     # called ball, was strike
        if abs(miss) <= 2.0:                       # borderline ("hard") calls
            a["bn"] += 1; a["bok"] += correct
    rows = [{"ump": k[1], "n": v["n"], "acc": v["ok"]/v["n"], "bn": v["bn"],
             "bacc": v["bok"]/v["bn"] if v["bn"] else 0, "fs": v["fs"], "fb": v["fb"]}
            for k, v in agg.items() if v["n"] >= 1500]
    print(f"\nqualified umps (>=1500 calls): {len(rows)}")
    la = sum(v["ok"] for v in agg.values())/sum(v["n"] for v in agg.values())
    print(f"league overall call accuracy: {la*100:.1f}%")
    def show(title, key, rev):
        print(f"\n{title}")
        for r in sorted(rows, key=lambda r: r[key], reverse=rev)[:8]:
            print(f"  {r['ump']:<22} acc {r['acc']*100:5.2f}%  | borderline(<=2\") {r['bacc']*100:4.1f}% (n={r['bn']})  "
                  f"| missed: {r['fs']} strikes-that-were-balls, {r['fb']} balls-that-were-strikes  (N={r['n']})")
    show("BEST overall accuracy:", "acc", True)
    show("WORST overall accuracy:", "acc", False)
    show("BEST on borderline (<=2\") calls:", "bacc", True)
    show("WORST on borderline (<=2\") calls:", "bacc", False)
    with open(ROOT/"ump_grades.csv","w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh, fieldnames=["ump","n","acc","bn","bacc","fs","fb"]); w.writeheader()
        for r in sorted(rows,key=lambda r:-r["acc"]): w.writerow(r)
    print(f"\nwrote ump_grades.csv ({len(rows)} umps)")

if __name__ == "__main__":
    main()
