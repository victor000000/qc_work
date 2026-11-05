# s001 Break-Stuck Suggestions — Structural Review

After 32 rounds with +0.00808 plateau, the probe-based exploration has saturated.
Below are concrete structural experiments ranked by expected info-per-risk.

## Plateau Diagnosis

- **4 bakes applied**: WH +0.00287, FC +0.00128, FG +0.00297, JBC +0.00096
- **6 rounds since last bake** (R1672-R1677): zero new candidates
- **R1674 EXIT-fund-gated experiment**: 1/80 non-zero — null
- All probe families converged to ~+0.00298 saturation ceiling

## Choke Points in Base

| Choke | Line | Current | Locked? |
|-------|------|---------|---------|
| `WT_CAP` | 28 | 0.07 | YES (memory) |
| `WT_PER_CONV` | 29 | 0.08 | NO |
| `WT_TILT_CAP` | 1612 | 2.0 | NO (local var) |
| `MIN_WT` | 30 | 0.02 | NO |
| `MIN_PRICE` | 31 | 32 | NO |
| `MIN_VOLUME` | 32 | 810000 | NO |
| `MTF_WEEKDAYS` | 33 | {0,2,4} | NO |
| Entry weekday | 247 | Monday only | NO |
| `vol_climax` ratio | 463 | 2.5× | NO |
| `_qpos` accel band | 434 | (0.01, 0.05) | partially (memory says cohort gates locked) |

## Ranked Experiments

### A. Raise `WT_TILT_CAP` 2.0 → 3.0 (TOP PICK)
**Hypothesis**: BAKE-WH does `wt_tilt *= 1.60` on small-decline trades. After it fires,
subsequent same-cohort tilt boosts hit the 2.0 cap. Raising to 3.0 lets compound boosts
(e.g., narrow-band probes within BAKE-WH zone) actually shift weights.

**Mechanics**: `_tilt = max(0.1, min(WT_TILT_CAP, wt_tilt))` at line 1623. Capping at
3.0 unlocks 50% more tilt headroom for stocks matching multiple boost rules.

**Risk**: LOW. Only affects already-elevated trades. WT_CAP=0.07 still binds final w.

**Test cost**: 1 line change + 1 round (rebake-equivalent).

### B. Add MAX_HOLD_DAYS exit (NEW LEVER)
**Hypothesis**: Trades that don't reach petgt within N days are dead capital. Force-exit
after 30/60/90 days. Frees budget for fresh entries.

**Mechanics**: Track entry date per position; in `_scan_exits`, append to `pending_exits`
if `(self.time - entry_date).days > MAX_HOLD_DAYS`.

**Risk**: MEDIUM. Could exit recovering positions. Need to bake threshold carefully.

**Test cost**: Modest base mod + 1-2 rounds to find optimal N.

### C. Trailing stop based on running high
**Hypothesis**: Current stop is fixed-percentage from entry. Trailing stop locks in gains
as position moves up.

**Mechanics**: Track `pos_max_price` per holding. Exit if `current_close < pos_max * (1 - trail_pct)`.

**Risk**: MEDIUM. Could trigger on temporary dips.

**Test cost**: Larger base mod + multiple rounds.

### D. Allow Tue/Wed/Thu/Fri entries (currently Mon-only)
**Hypothesis**: Strategy enters only on Mondays (line 247). 5x more entry opportunities
if all weekdays allowed.

**Risk**: HIGH. Could 5x trade count → over-trading, costs explode. Likely needs
adjustments to gross_target / per-trade weight.

**Test cost**: HIGH. Major behavioral change requiring extensive verification.

### E. Adjust `MIN_PRICE` (32 → 25 or 40)
**Hypothesis**: Different price-range universe gives different mean-reversion behavior.
Lower threshold = more small-cap exposure.

**Risk**: MEDIUM. Changes selection — bakes need re-verify.

### F. Adjust `vol_climax` threshold (2.5× → 2.0× or 3.0×)
**Hypothesis**: Volume-climax skip rule tunable. Tighter (2.0×) skips more entries;
looser (3.0×) keeps marginal climax trades.

**Risk**: LOW-MEDIUM. Single line change.

### G. Add momentum-based entry filter
**Hypothesis**: Skip entries where stock is up 5%+ in last 5 days (already-recovered).
R1677 tests this as probe; could embed in base if probe finds productive cohort.

**Risk**: MEDIUM. Memory says skip rules at moderate gates can hurt.

## Recommendation

**Start with A (`WT_TILT_CAP` 2.0 → 3.0)**. Lowest risk, highest information. If positive
lift, we know cap-binding was holding back the WH bake. If null, we've confirmed
WT_TILT_CAP isn't the bottleneck and can move to B/C.

After A, **F (`vol_climax`)** is next-cheapest — single-line change, high info content
(tells us if the volume-climax rule is over- or under-tuned).

C (trailing stop) is the most likely SOURCE of new lift but requires more code changes.
