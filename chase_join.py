"""Wallner hypothesis: does plate discipline predict challenge skill?
Joins Savant per-batter discipline (chase/BB%/K%/whiff) to each batter's ABS challenge
success rate, and reports correlations + quartile splits. Library-free."""
import csv, sqlite3, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
ROOT = Path(__file__).resolve().parent

disc = {}
for r in csv.DictReader(open(ROOT / "chase_probe.csv", encoding="utf-8-sig")):
    try:
        disc[int(r["player_id"])] = {"name": r["last_name, first_name"], "pa": int(r["pa"]),
            "chase": float(r["oz_swing_percent"]), "bb": float(r["bb_percent"]),
            "k": float(r["k_percent"]), "whiff": float(r["whiff_percent"])}
    except Exception:
        pass

con = sqlite3.connect(ROOT / "abs.sqlite"); con.row_factory = sqlite3.Row
perf = defaultdict(lambda: [0, 0])   # batterId -> [n, overturned]
for r in con.execute("select batterId, overturned from challenges where side='batter'"):
    perf[r["batterId"]][0] += 1; perf[r["batterId"]][1] += r["overturned"]

MIN = 8
joined = []
for bid, (n, ov) in perf.items():
    if n >= MIN and bid in disc:
        d = disc[bid]
        joined.append({"name": d["name"], "n": n, "succ": ov / n, **{k: d[k] for k in ("chase", "bb", "k", "whiff")}})
print(f"batters with >={MIN} challenges AND discipline data: {len(joined)}")

def pearson(xs, ys):
    nn = len(xs); mx = sum(xs) / nn; my = sum(ys) / nn
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** .5; vy = sum((y - my) ** 2 for y in ys) ** .5
    return cov / (vx * vy) if vx and vy else 0

succ = [j["succ"] for j in joined]
print("\nCorrelation of batter CHALLENGE SUCCESS with plate-discipline metrics:")
for metric, lab in [("chase", "chase rate (O-Swing%)"), ("bb", "walk%"), ("k", "strikeout%"), ("whiff", "whiff%")]:
    r = pearson([j[metric] for j in joined], succ)
    print(f"   {lab:<22}: r = {r:+.3f}")

# quartile split by chase rate (low chase = best 'eye')
js = sorted(joined, key=lambda j: j["chase"])
q = len(js) // 4
def avg(g): return sum(x["succ"] for x in g) / len(g) * 100
print(f"\nChallenge success by CHASE-RATE quartile (low chase = better eye):")
print(f"   Q1 lowest chase  (best eye): {avg(js[:q]):.1f}%  (n={q})")
print(f"   Q4 highest chase (worst eye): {avg(js[-q:]):.1f}%  (n={q})")
# same for walk rate (high BB = patient)
jb = sorted(joined, key=lambda j: j["bb"])
print(f"Challenge success by WALK-RATE quartile:")
print(f"   Q1 lowest BB%:  {avg(jb[:q]):.1f}%")
print(f"   Q4 highest BB%: {avg(jb[-q:]):.1f}%")

# notable: best-eye hitters who are bad challengers (the 'Wallner' archetype)
print("\nLow-chase hitters (good eye) who are POOR challengers (the Wallner archetype):")
elite_eye = sorted(joined, key=lambda j: j["chase"])[:len(joined)//2]
for j in sorted(elite_eye, key=lambda j: j["succ"])[:8]:
    print(f"   {j['name']:<22} chase {j['chase']:.1f}%  challenge {j['succ']*100:.0f}% ({j['n']})")
with open(ROOT / "batter_discipline.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["name", "n", "succ", "chase", "bb", "k", "whiff"]); w.writeheader()
    for j in sorted(joined, key=lambda j: -j["succ"]): w.writerow(j)
print(f"\nwrote batter_discipline.csv ({len(joined)} batters)")
