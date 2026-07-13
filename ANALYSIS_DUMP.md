# ABS Challenge Analysis — Raw Numbers Dump (2026, 2026-03-25 to 2026-07-12)

## METHODOLOGY & CAVEATS (read before analyzing)
- Source: MLB StatsAPI v1.1 game feeds, 1,421 final regular-season games. Per-pitch coords (pX/pZ ft).
- Challenges (6,053) = UNION of pitch-level reviewDetails (AB continued) + play-level reviewDetails (AB-ending/terminal). 1,502 (25%) are terminal; extracting from the pitch level alone drops them and biases overturn high (pitch-level-only 55.4% vs union 53.0%).
- ABS zone CALIBRATED to actual verdicts: horizontal = plate half (8.5in) + ball radius (1.45in); vertical = 27%-55% of batter height + ball radius. Matches real ABS verdicts on 86.8% of (all-borderline) challenges. => RANKINGS robust; absolute % approximate, esp. within ~1in of edge.
- 'overturned' = challenge succeeded (call changed). League overturn 53.0% (reconciles to Baseball Savant's official total within 1%).
- role: batter / catcher / pitcher (defense split by whether challenger==pitcher of record).
- MISSED CALL ('should have') = a TAKEN, UN-challenged pitch whose original ump call disagrees with the ABS zone by 1.5in-6.0in (lower bound beats model+Hawkeye noise; upper bound drops tracking glitches). 212,221 taken pitches scanned.
- 'available' uses the real rule: 2 challenges/game, RETAINED on success; +1 per extra inning if empty (validated: 0 illegal challenges innings 1-9; extra-inning bonus confirmed in data). 'moot' = clear miss but bank empty.

## 1. INNING VECTOR

### 1a. Challenge volume & overturn% by inning
| inning | n | overturn% | batter n/ov | catcher n/ov | pitcher n/ov |
|---|---|---|---|---|---|
| 1 | 592 | 59.6% | 254/49.6% | 327/67.9% | 11/45.5% |
| 2 | 530 | 59.6% | 220/50.0% | 297/67.0% | 13/53.8% |
| 3 | 568 | 56.3% | 260/51.9% | 297/60.6% | 11/45.5% |
| 4 | 607 | 55.8% | 280/50.7% | 310/61.6% | 17/35.3% |
| 5 | 641 | 58.2% | 300/52.0% | 328/64.0% | 13/53.8% |
| 6 | 694 | 51.9% | 301/47.5% | 387/55.6% | 6/33.3% |
| 7 | 766 | 56.3% | 375/51.7% | 377/62.1% | 14/21.4% |
| 8 | 758 | 46.7% | 365/44.1% | 382/50.3% | 11/9.1% |
| 9 | 797 | 40.3% | 403/38.0% | 382/43.2% | 12/25.0% |
| 10+ | 100 | 42.0% | 56/37.5% | 43/48.8% | 1/0.0% |

### 1b. Desperation cells by inning bucket (overturn%, n)
| cell | 1-3 | 4-6 | 7-9 | 10+ |
|---|---|---|---|---|
| batter @2 strikes | 37.2% (261) | 42.1% (302) | 36.7% (349) | 33.3% (18) |
| catcher @3 balls | 56.0% (116) | 46.9% (147) | 33.8% (136) | 33.3% (6) |
| all challenges | 58.5% (1690) | 55.2% (1942) | 47.7% (2321) | 42.0% (100) |

## 2. SHOULD-HAVES (clear un-challenged misses)
- total clear misses: 2245 | available='should have': 1999 (~1.72/game) | moot (bank empty): 246
- direction: batter-robbed (called strike was a ball): 728 | defense-missed (called ball was a strike): 1271

### 2a. Should-have vs moot by inning (does the bank run dry late?)
| inning | should-have | moot | moot% |
|---|---|---|---|
| 1 | 261 | 0 | 0% |
| 2 | 251 | 4 | 2% |
| 3 | 223 | 10 | 4% |
| 4 | 247 | 7 | 3% |
| 5 | 257 | 11 | 4% |
| 6 | 194 | 32 | 14% |
| 7 | 194 | 35 | 15% |
| 8 | 230 | 76 | 25% |
| 9 | 119 | 68 | 36% |
| 10+ | 23 | 3 | 12% |

### 2b. Should-haves by count (pre-pitch)
| | 0b | 1b | 2b | 3b |
|---|---|---|---|---|
| 0 str | 873 | 223 | 75 | 46 |
| 1 str | 257 | 185 | 88 | 46 |
| 2 str | 58 | 69 | 52 | 27 |

### 2c. Should-haves by miss depth
- 1.5-2in: 975
- 2-3in: 805
- 3-4in: 170
- 4-6in: 49

### 2d. Terminal damage
- free strikeouts given away (called strike-3 that was a ball, challenge AVAILABLE, unused): 46
- moot strikeouts (rung up on a ball, NO challenge to spend): 10
- worst available free-K (batter, depth, count, date, pitcher):
  - Joc Pederson | 4.81in | 3-2 | 2026-06-27 | vs Dylan Cease
  - Nick Yorke | 3.73in | 2-2 | 2026-04-28 | vs Justin Bruihl
  - Colson Montgomery | 3.69in | 1-2 | 2026-06-06 | vs Chase Shugart
  - TJ Friedl | 3.24in | 0-2 | 2026-05-17 | vs Gavin Williams
  - Bryan Reynolds | 3.18in | 3-2 | 2026-03-29 | vs Nolan McLean
  - Trevor Story | 3.15in | 3-2 | 2026-03-28 | vs Brady Singer
  - Drew Millas | 2.93in | 0-2 | 2026-04-18 | vs Adrian Houser
  - Kazuma Okamoto | 2.75in | 0-2 | 2026-03-28 | vs Michael Kelly
  - Colton Cowser | 2.72in | 3-2 | 2026-05-17 | vs Miles Mikolas
  - Byron Buxton | 2.72in | 0-2 | 2026-04-22 | vs Brooks Raley

## 3. TEAM CHALLENGE CONVERSION (of clear catchable misses in your favor, how many did you catch?)
- caught = your overturned challenges with |miss|>=1.5in ; missed = your should-haves ; conversion = caught/(caught+missed)
| team | caught | missed (should-have) | conversion% |
|---|---|---|---|
| NYY | 47 | 46 | 51% |
| TB | 48 | 49 | 49% |
| SD | 45 | 46 | 49% |
| MIN | 57 | 59 | 49% |
| MIL | 54 | 57 | 49% |
| SEA | 35 | 44 | 44% |
| PHI | 45 | 59 | 43% |
| CWS | 51 | 67 | 43% |
| AZ | 44 | 59 | 43% |
| MIA | 42 | 58 | 42% |
| CHC | 43 | 60 | 42% |
| COL | 50 | 71 | 41% |
| ATL | 44 | 63 | 41% |
| LAD | 42 | 64 | 40% |
| ATH | 54 | 84 | 39% |
| HOU | 41 | 64 | 39% |
| NYM | 36 | 61 | 37% |
| LAA | 45 | 78 | 37% |
| TEX | 40 | 70 | 36% |
| CLE | 38 | 70 | 35% |
| TOR | 30 | 56 | 35% |
| STL | 40 | 78 | 34% |
| SF | 25 | 50 | 33% |
| KC | 37 | 74 | 33% |
| DET | 35 | 72 | 33% |
| BAL | 45 | 99 | 31% |
| CIN | 44 | 97 | 31% |
| BOS | 33 | 82 | 29% |
| WSH | 29 | 83 | 26% |
| PIT | 27 | 79 | 25% |