"""Difficulty-adjusted umpire grades. Builds an empirical 'expected correctness' curve
P(correct | distance from zone edge) from all taken pitches, then scores each ump by
Correct-Above-Average (CAA) = actual correct - expected correct given the pitches they faced.
Library-free; addresses the 'absolute % are calibration-approximate' caveat by grading
umps relative to the difficulty of their own pitch mix."""
import sqlite3, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
con = sqlite3.connect(Path(__file__).resolve().parent / "abs.sqlite"); con.row_factory = sqlite3.Row
P = [dict(r) for r in con.execute("select umpId,ump,miss_off_edge_in,correct from pitches")]

# empirical difficulty curve: P(correct) by |miss| bin (0.25in bins, capped at 4in)
def binkey(m): return min(int(abs(m) / 0.25), 16)   # 0..16 (>=4in lumped)
curve_n = defaultdict(int); curve_ok = defaultdict(int)
for r in P:
    b = binkey(r["miss_off_edge_in"]); curve_n[b] += 1; curve_ok[b] += r["correct"]
curve = {b: curve_ok[b] / curve_n[b] for b in curve_n}
print("difficulty curve  P(correct | distance from edge):")
for b in sorted(curve):
    lab = f"{b*0.25:.2f}-{(b+1)*0.25:.2f}in" if b < 16 else ">=4in"
    print(f"   {lab:>12}: {curve[b]*100:5.1f}%  (n={curve_n[b]})")

agg = defaultdict(lambda: {"n": 0, "ok": 0, "exp": 0.0})
for r in P:
    a = agg[(r["umpId"], r["ump"])]
    a["n"] += 1; a["ok"] += r["correct"]; a["exp"] += curve[binkey(r["miss_off_edge_in"])]
rows = []
for (uid, name), v in agg.items():
    if v["n"] < 1500: continue
    caa = v["ok"] - v["exp"]                         # correct calls above expectation
    rows.append({"ump": name, "n": v["n"], "acc": v["ok"]/v["n"], "exp": v["exp"]/v["n"],
                 "caa": caa, "caa_per1000": caa / v["n"] * 1000})
print(f"\nqualified umps: {len(rows)}")
def show(title, rev):
    print(f"\n{title}  (CAA/1000 = correct calls above difficulty-adjusted expectation, per 1000 pitches)")
    for r in sorted(rows, key=lambda x: x["caa_per1000"], reverse=rev)[:8]:
        print(f"  {r['ump']:<22} raw {r['acc']*100:5.2f}%  exp {r['exp']*100:5.2f}%  "
              f"CAA/1000 {r['caa_per1000']:+5.1f}  (total CAA {r['caa']:+.0f}, N={r['n']})")
show("MOST accurate vs. expected (best umps):", True)
show("LEAST accurate vs. expected (worst umps):", False)
# does difficulty-adjustment change the story vs raw?
raw_rank = {r["ump"]: i for i, r in enumerate(sorted(rows, key=lambda x: -x["acc"]), 1)}
adj_rank = {r["ump"]: i for i, r in enumerate(sorted(rows, key=lambda x: -x["caa_per1000"]), 1)}
movers = sorted(rows, key=lambda r: abs(raw_rank[r["ump"]] - adj_rank[r["ump"]]), reverse=True)[:6]
print("\nbiggest rank shifts when adjusting for difficulty (faced harder/easier pitch mix):")
for r in movers:
    print(f"  {r['ump']:<22} raw#{raw_rank[r['ump']]:>2} -> adj#{adj_rank[r['ump']]:>2}")
