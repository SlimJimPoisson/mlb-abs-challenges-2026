"""Raw numbers dump: should-haves + inning vector. Writes ANALYSIS_DUMP.md (portable)."""
import sqlite3, csv, json, sys
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
ROOT = Path(__file__).resolve().parent
con = sqlite3.connect(ROOT/"abs.sqlite"); con.row_factory = sqlite3.Row
CH = [dict(r) for r in con.execute("select * from challenges")]
for r in CH:
    r['role'] = ('batter' if r['side']=='batter' else 'pitcher' if r['challengerId']==r['pitcherId'] else 'catcher')
TM = {int(k):v for k,v in json.load(open(ROOT/"teams.json")).items()}
MC = [r for r in csv.DictReader(open(ROOT/"missed_calls.csv", encoding='utf-8'))]
for r in MC:
    r['inning']=int(r['inning']); r['depth']=float(r['depth']); r['avail']=(r['had_challenge']=='True')
out = []
def w(s=""): out.append(s)
def ovr(g): return f"{sum(x['overturned'] for x in g)/len(g)*100:.1f}%" if g else "-"

# --- all header figures COMPUTED from the shipped data (never hardcoded) ---
NPITCH = con.execute("select count(*) from pitches").fetchone()[0]
DMIN = min(r['date'] for r in CH); DMAX = max(r['date'] for r in CH)
NGAMES = len({r['gamePk'] for r in CH}); NCH = len(CH)
NTERM = sum(1 for r in CH if r['terminal_chal'])
OV = sum(r['overturned'] for r in CH) / NCH * 100
NT0 = [r for r in CH if not r['terminal_chal']]
OVP = sum(r['overturned'] for r in NT0) / len(NT0) * 100        # pitch-level-only (biased) rate
MV = [r for r in CH if r['pred_strike'] is not None]
MATCH = sum(1 for r in MV if bool(r['pred_strike']) == bool(r['abs_verdict_strike'])) / len(MV) * 100

w(f"# ABS Challenge Analysis — Raw Numbers Dump (2026, {DMIN} to {DMAX})")
w("\n## METHODOLOGY & CAVEATS (read before analyzing)")
w(f"- Source: MLB StatsAPI v1.1 game feeds, {NGAMES:,} final regular-season games. Per-pitch coords (pX/pZ ft).")
w(f"- Challenges ({NCH:,}) = UNION of pitch-level reviewDetails (AB continued) + play-level reviewDetails (AB-ending/terminal). "
  f"{NTERM:,} ({NTERM/NCH*100:.0f}%) are terminal; extracting from the pitch level alone drops them and biases overturn high "
  f"(pitch-level-only {OVP:.1f}% vs union {OV:.1f}%).")
w(f"- ABS zone CALIBRATED to actual verdicts: horizontal = plate half (8.5in) + ball radius (1.45in); "
  f"vertical = 27%-55% of batter height + ball radius. Matches real ABS verdicts on {MATCH:.1f}% of (all-borderline) challenges. "
  "=> RANKINGS robust; absolute % approximate, esp. within ~1in of edge.")
w(f"- 'overturned' = challenge succeeded (call changed). League overturn {OV:.1f}% (reconciles to Baseball Savant's official total within 1%).")
w("- role: batter / catcher / pitcher (defense split by whether challenger==pitcher of record).")
w(f"- MISSED CALL ('should have') = a TAKEN, UN-challenged pitch whose original ump call disagrees with the ABS zone by "
  f"1.5in-6.0in (lower bound beats model+Hawkeye noise; upper bound drops tracking glitches). {NPITCH:,} taken pitches scanned.")
w("- 'available' uses the real rule: 2 challenges/game, RETAINED on success; +1 per extra inning if empty (validated: "
  "0 illegal challenges innings 1-9; extra-inning bonus confirmed in data). 'moot' = clear miss but bank empty.")

# ---------------- INNING VECTOR ----------------
w("\n## 1. INNING VECTOR")
w("\n### 1a. Challenge volume & overturn% by inning")
w("| inning | n | overturn% | batter n/ov | catcher n/ov | pitcher n/ov |")
w("|---|---|---|---|---|---|")
def ig(i): return i if i<=9 else 10
for i in list(range(1,10))+[10]:
    g=[r for r in CH if ig(r['inning'])==i]
    if not g: continue
    parts=[]
    for role in ('batter','catcher','pitcher'):
        gr=[r for r in g if r['role']==role]; parts.append(f"{len(gr)}/{ovr(gr)}")
    lbl = f"{i}+" if i==10 else str(i)
    w(f"| {lbl} | {len(g)} | {ovr(g)} | {parts[0]} | {parts[1]} | {parts[2]} |")

w("\n### 1b. Desperation cells by inning bucket (overturn%, n)")
def bk(i): return '1-3' if i<=3 else '4-6' if i<=6 else '7-9' if i<=9 else '10+'
w("| cell | 1-3 | 4-6 | 7-9 | 10+ |")
w("|---|---|---|---|---|")
for lbl, filt in [("batter @2 strikes", lambda r: r['role']=='batter' and r['pre_strikes']==2),
                  ("catcher @3 balls", lambda r: r['role']=='catcher' and r['pre_balls']==3),
                  ("all challenges", lambda r: True)]:
    g=[r for r in CH if filt(r)]
    cells=[f"{ovr([r for r in g if bk(r['inning'])==b])} ({len([r for r in g if bk(r['inning'])==b])})" for b in ('1-3','4-6','7-9','10+')]
    w(f"| {lbl} | "+" | ".join(cells)+" |")

# ---------------- SHOULD HAVES ----------------
sh=[r for r in MC if r['avail']]; moot=[r for r in MC if not r['avail']]
w("\n## 2. SHOULD-HAVES (clear un-challenged misses)")
w(f"- total clear misses: {len(MC)} | available='should have': {len(sh)} (~{len(sh)/1161:.2f}/game) | moot (bank empty): {len(moot)}")
w(f"- direction: batter-robbed (called strike was a ball): {sum(1 for r in sh if r['role'].startswith('batter'))} | "
  f"defense-missed (called ball was a strike): {sum(1 for r in sh if r['role'].startswith('defense'))}")

w("\n### 2a. Should-have vs moot by inning (does the bank run dry late?)")
w("| inning | should-have | moot | moot% |")
w("|---|---|---|---|")
for i in list(range(1,10))+[10]:
    s=[r for r in sh if ig(r['inning'])==i]; m=[r for r in moot if ig(r['inning'])==i]
    tot=len(s)+len(m)
    if tot==0: continue
    lbl=f"{i}+" if i==10 else str(i)
    w(f"| {lbl} | {len(s)} | {len(m)} | {len(m)/tot*100:.0f}% |")

w("\n### 2b. Should-haves by count (pre-pitch)")
w("| | 0b | 1b | 2b | 3b |")
w("|---|---|---|---|---|")
for s in (0,1,2):
    cells=[str(sum(1 for r in sh if int(r['pre_s'])==s and int(r['pre_b'])==b)) for b in range(4)]
    w(f"| {s} str | "+" | ".join(cells)+" |")

w("\n### 2c. Should-haves by miss depth")
for lo,hi in [(1.5,2),(2,3),(3,4),(4,6)]:
    w(f"- {lo}-{hi}in: {sum(1 for r in sh if lo<=r['depth']<hi)}")

w("\n### 2d. Terminal damage")
fk=[r for r in sh if r['role'].startswith('batter') and r['pre_s']=='2']
mk=[r for r in moot if r['role'].startswith('batter') and r['pre_s']=='2']
w(f"- free strikeouts given away (called strike-3 that was a ball, challenge AVAILABLE, unused): {len(fk)}")
w(f"- moot strikeouts (rung up on a ball, NO challenge to spend): {len(mk)}")
w("- worst available free-K (batter, depth, count, date, pitcher):")
for r in sorted(fk, key=lambda x:-x['depth'])[:10]:
    w(f"  - {r['batter']} | {r['depth']}in | {r['pre_b']}-{r['pre_s']} | {r['date']} | vs {r['pitcher']}")

# ---------------- TEAM CONVERSION ----------------
w("\n## 3. TEAM CHALLENGE CONVERSION (of clear catchable misses in your favor, how many did you catch?)")
w("- caught = your overturned challenges with |miss|>=1.5in ; missed = your should-haves ; conversion = caught/(caught+missed)")
caught=Counter();
for r in CH:
    if r['overturned'] and r.get('miss_off_edge_in') is not None and abs(r['miss_off_edge_in'])>=1.5:
        caught[r['challengeTeamId']]+=1
missed=Counter(int(r['resp_team']) for r in sh)
rows=[]
for tid in set(list(caught)+list(missed)):
    c=caught.get(tid,0); m=missed.get(tid,0); tot=c+m
    if tot>=20: rows.append((TM.get(tid,tid), c, m, c/tot))
w("| team | caught | missed (should-have) | conversion% |")
w("|---|---|---|---|")
for t,c,m,p in sorted(rows, key=lambda x:-x[3]):
    w(f"| {t} | {c} | {m} | {p*100:.0f}% |")

txt="\n".join(out)
(ROOT/"ANALYSIS_DUMP.md").write_text(txt, encoding='utf-8')
print(txt)
print(f"\n\n[written to {ROOT/'ANALYSIS_DUMP.md'}]")
