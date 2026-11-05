# s001 Performance Improvement Suggestions

After 45 rounds, +0.00958 cumulative bake lift (NOOP 3.21808 vs 3.20850 pre-bakes).
0.3% improvement is decent but plateauing. Concrete next-step options:

## RANKED BY EXPECTED INFO-PER-COMPUTE

### 1. Re-test FE/FC2 at SMALLER mags only (TOP PICK)
**Status**: BAKE-FE-R1660 and BAKE-FC-R1660 were reverted because their
a40 mag was catastrophic (-0.011). But ISO_FE_a20=+0.00298 in isolation
on the current base. **Their a20 mag was real lift; only a40 was destructive.**

Test: Apply `score += 0.020 if cohort × gross_profit_5y_growth > 0.05` (FE@a20)
and `score += 0.020 if cohort × common_equity_to_assets > 0.30` (FC2@a20)
WITHOUT the a40 multiplier. Check if NOOP shifts +0.003-0.006.

Risk: LOW. We know a20 was OK in isolation; only stacking 4+ at a40 was bad.
Cost: 1 round to verify NOOP shift.
Potential lift: +0.002-0.005 if both work.

### 2. Lower bake threshold to +0.0007 with multi-mag confirmation gate
**Rationale**: We've been conservative — only baking ≥+0.001. Many close-misses
at +0.00096 (JBCB, JBIC, JD4) sit just below threshold. If multi-mag confirmed
(both a20 AND a40 positive, monotonic), variance argument is weaker.

Modify auto_apply_bake to accept thr=+0.0007 if BOTH mags are positive.
Risk: MEDIUM. Variance memory says ±0.012 possible; +0.0007 lifts likely real
only with multi-mag confirmation.

### 3. Quality-META probe (combine 3+ high-quality gates)
**Hypothesis**: Each existing bake gate (operation_margin, net_income_growth,
deferred_revenue, preferred_stock_equity) catches a SLICE of high-quality
stocks. A probe with all 4 gates ANDed might find the SUPER-QUALITY subset
where score+= produces compounding lift.

Test: `_qpos × decline ∈ (0.020, 0.050) × ALL 4 quality gates`. If this
narrow cohort responds to score += 0.060 (sum of bake mags), that's a
6th bake unlocking compounded effect. If sub-additive (per cohort
saturation memory ~20% summed), still useful diagnostic.

### 4. Test sub-threshold close-misses as a BATCH
**Approach**: Apply 5-10 sub-threshold (+0.0007 to +0.0009) bakes
simultaneously. If individual variance washes out, the BATCH may
produce +0.003-0.005 cumulative.

Risk: HIGH (per memory destructive stacking). Would need careful
multi-cohort selection (avoid same parent).

### 5. Time-dimension probes (untested cleanly)
- **Month-of-year** seasonality: probe Jan/Feb/Mar/.../Dec cohorts
- **Quarter-end** effects: test trades 5 days before/after quarter-end
- **Year-end** tax-loss harvesting: Dec entries
- These are CHEAP to test (4-12 specs) and orthogonal to existing dimensions.

### 6. Regime-conditional MIN_WT
Currently MIN_WT=0.02 globally. Probe rounds where MIN_WT changes by regime:
e.g., raise to 0.04 in stable VXX-low regimes (concentrate winners), drop
to 0.015 in panic regimes (more diversification).

Requires base mod (NEW lever). Higher complexity but unexplored.

### 7. Reverse-engineer existing bakes' common pattern
All 5 bakes share: `_qpos × decline ∈ (0.015-0.050) × <quality fund>`. The
common thread is **high-quality stocks during shallow declines**. Maybe a
SINGLE compound bake replacing 5 individual ones produces cleaner total
lift (less stacking overhead per cohort-saturation).

Test: temporarily disable all 5 bakes, apply ONE composite:
`_qpos × decline ∈ (0.015, 0.050) × (margin>0.20 OR growth>0.05 OR
deferred_rev>0 OR preferred_eq>0)` × score += 0.040.
If this single bake gives ≥+0.005, simpler base + same lift.

### 8. Continue domain-diversified rotation (current path)
Per playbook, this systematically widens coverage. ~95% efficient. Slow but
sustainable. Expected 1 bake per 5-10 rounds based on current yield.

## What to AVOID

- More structural base changes (catastrophic memory)
- Theme expansion after a bake (post-bake saturation memory)
- Compound/refine/sector blocks (net -EV memory)
- score+= MEDIUM cohort, wt_tilt outside bake (never_fires memory)
- Combined 4+ score+= bakes on same cohort (destructive_stacking memory)

## Recommendation

**Start with #1 (FE/FC2 at a20 only)**. Lowest risk, ~5 minutes work, could add
+0.002-0.005. If it lands, total session lift jumps to +0.012+.

**Then #3 (Quality-META compound)**. Tests whether existing 5 bakes are independent
or have hidden interactions worth exploiting.

If both null, accept that +0.00958 is near-optimal for this base + pivot to
s002 strategy or the diagnostic-only mode (small variance-measurement rounds).
