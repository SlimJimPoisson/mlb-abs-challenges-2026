# MLB ABS Challenge System — 2026 First-Half Analysis

Reproducible data and code behind **"The ABS Challenge System Runs Out of Challenges Before It Runs Out of Bad Calls."**
Full writeup with interactive charts: **[CANONICAL_URL]**

Every 2026 first-half ABS challenge (6,053) and every taken pitch (212,221) reconstructed from MLB's public StatsAPI game feeds (Hawk-Eye), **March 25 – July 12, 2026**.

---

## Headline findings

- **The ninth-inning double-whammy.** As games get late, challenge success *falls* (59% early → **40%** in the 9th) while the share of clearly-blown calls that can't be challenged — the team is out of challenges — *rises* (≈0% → **36%**). The system is least accurate and least available in the same inning. It survives a difficulty-composition control and a leverage control (the availability collapse is leverage-invariant), and it carries into the postseason.
- **By role:** catchers are the best challengers (58.4%), batters middling (47.7%), pitchers poor (34%). League overturn rate **53.0%**.
- **Symmetric desperation.** Batters degrade as strikes mount; catchers as balls mount — a mirror pitch-difficulty can't produce. Hitters challenging **strike three are wrong 61.5%** of the time (572 self-confirmed strikeouts).
- **Umpires are good.** League ball/strike accuracy **92.6%**; a coin flip right at the zone edge, near-perfect a couple inches out.

## A data finding worth its own line

MLB's StatsAPI game feed records at-bat-**ending** challenges (created/confirmed third strike, fourth ball) in a **play-level** `reviewDetails` field, *not* the pitch-level one. Extracting challenges off the pitch record — the natural approach — silently drops **~25% of all challenges** (all terminal) and yields an inflated ~55% overturn rate instead of the true **53.0%**. This repo takes the union of both fields. The corrected total reconciles to **Baseball Savant's official count within 1%** (6,053 vs 6,040), role splits near-identical, pitcher count exact.

## Data sources

- **Primary:** MLB StatsAPI v1.1 game feeds (`statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live`) — per-pitch Hawk-Eye coordinates, calls, counts, game state, home-plate umpire, and challenge records.
- **Validation:** Baseball Savant ABS leaderboard (official challenge totals); abstap.com (independent umpire tallies); Umpire Scorecards (accuracy-range cross-check).

## Method & calibration

The per-pitch ABS verdict is **reconstructed** from coordinates, not read from an official field (MLB does not publish it). The calibrated zone: plate half-width 8.5″ + 1.45″ ball radius (a strike if the ball clips the zone); vertical bounds 27%–55% of listed batter height ± ball radius. It matches actual ABS verdicts on **~87%** of (all-borderline) challenges — near the ceiling given tracking noise.

**Interpretation guidance:** rankings and distribution *shapes* are robust; absolute percentages within ~1″ of the zone edge are estimates.

## Known limitations

- **Reconstructed zone (~87% on borderline).** Reliable in aggregate and for rankings; not for single-pitch or fine individual claims near the edge.
- **"Missed call" threshold.** Un-challenged umpire misses are counted only at ≥1.5″ past the edge (beats model + tracking noise) and ≤6″ (excludes tracking glitches).
- **Half-season sample.** Enough for league/role trends; thin for individual-player claims — treat player call-outs as illustrative.
- **Reconstructed game state.** Base/out/score entering each at-bat is rebuilt forward from post-play fields.

## On individual umpires

This project **does not rank individual umpires.** A reconstructed zone is precise enough to grade the league in aggregate — the check that validates everything above — but not to fairly separate one umpire from another at a half-season sample. Individual accuracy is [Umpire Scorecards](https://umpscorecards.com)' domain, not this one.

## Data model

`abs.sqlite` holds two tables:
- **`challenges`** — one row per challenge (6,053): who challenged, pre-pitch count, leverage (outs/runners/score), handedness, pitch type, the ABS verdict, coordinates, and calibrated miss distances.
- **`pitches`** — one row per taken pitch (212,221): the umpire's original call, the ABS verdict, `correct`, and distance from the zone edge — the foundation for umpire accuracy and the "should-have-been-challenged" analysis.

CSV exports of the key tables are included so results can be inspected without running anything.

## Reproduce

Requires Python 3 (standard library only). Game feeds are fetched from StatsAPI on first run and cached to `feeds/` (~1 GB, not included; set `SEASON_START`/`SEASON_END` in `abs_pull.py`).

```
python abs_pull.py         # -> challenges table + challenges.csv
python build_pitches.py    # -> pitches table (all taken pitches)
python missed_calls.py     # -> missed_calls.csv (should-haves)
python ump_grades.py       # -> ump_grades.csv (aggregate umpire accuracy)
python expected_grades.py  # -> difficulty-adjusted accuracy
python dump_report.py      # -> ANALYSIS_DUMP.md (raw cross-tabs)
```

## Files

| File | What |
|---|---|
| `abs.sqlite` | Both tables, queryable |
| `challenges.csv` / `missed_calls.csv` / `ump_grades.csv` / `batter_discipline.csv` | Derived data |
| `ANALYSIS_DUMP.md` | Raw cross-tabs (inning vector, should-haves, team conversion) |
| `canonical.html` | The writeup page (self-contained) |
| `*.py` | The pipeline |

## License

Data derived from MLB's public feeds. Code released for inspection and reproduction; please credit if you build on it.
