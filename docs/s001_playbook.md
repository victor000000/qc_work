# s001 Generator Playbook (R1645-R1688 distilled)

After 44 rounds, **5 verified bakes** (+0.00958 expected lift, NOOP 3.21808).

## Active bakes (DON'T MODIFY)

| Bake | Cohort | Op | Lift |
|------|--------|----|----- |
| BAKE-WH-R1650  | `decline ∈ (0.020, 0.050)` | `wt_tilt *= 1.60` | +0.00287 |
| BAKE-FC-R1657  | `_qpos × decline ∈ (0.020, 0.050) × operation_margin > 0.20` | `score += 0.040` | +0.00128 |
| BAKE-FG-R1664  | `_qpos × decline ∈ (0.020, 0.050) × net_income_cont_ops_growth > 0.05` | `score += 0.020` | +0.00298 |
| BAKE-JBC-R1666 | `_qpos × decline ∈ (0.015, 0.020) × current_deferred_revenue > 0` | `score += 0.020` | +0.00138 |
| BAKE-J0-R1682  | `_qpos × decline ∈ (0.015, 0.020) × preferred_stock_equity > 0` | `score += 0.040` | +0.00107 |

## Round modes

### `pure_explore_round(rid, n_fresh_bz, n_fresh_jb, extra_blocks)`
Fresh-fund × score+= in BAKE-ZONE (0.020-0.050) and JUST-BELOW-BAKE (0.015-0.020).
Best for steady frontier exploration. ~95% predicted efficient.

### `domain_diversified_round(rid, n_per_domain, extra_blocks)` ⭐ RECOMMENDED
Probes 5 namespaces in parallel: `_cfs/_inc/_vr/_ers/_bs`. Forces breadth.
Use after a bake (memory: post-bake expansion saturates). 41 fresh fields.

### `bake_stability_round(rid, n_noops=8)`
Re-verify each bake's lift + extra NOOPs for variance. ~12 specs.

## DON'T

| ❌ | Reason | Memory |
|----|--------|--------|
| `bake_compound_grid` blocks | 4/74 pos, 32% neg, net -EV | `compound_refine_sector_negative_ev` |
| `refine_bake` on TUNED bakes | 35% catastrophic, stacking destroys | `refine_bake_stacking` |
| Sector × cohort compounds | 0/71 positive | `compound_refine_sector_negative_ev` |
| score+= × MEDIUM (decline 0.05-0.10) | Rank stable, doesn't shift | `never_fires_patterns` |
| wt_tilt × decline ≥ 0.05 | Cap-binding | `never_fires_patterns` |
| conv × mags ≥ 1.5 | Cap-saturation | `never_fires_patterns` |
| Multi-mag uses (a5, a10, a80+) | 0% historical hit | `never_fires_patterns` |
| Mults (m105/108/110/113) | 0/518 positive | `never_fires_patterns` |
| m=140 specifically | Repeatable poison | `never_fires_patterns` |
| Categorical fields with `is not None` gate | Fires too broadly | R1686 lesson (R1686 in commit log) |
| `> 0` numeric gates without selectivity check | Cohort destruction | R1686 lesson |
| Combined structural base changes | Catastrophic (-67%) | `structural_changes_destructive` |
| Theme expansion after a bake | Always dry, rotate domains instead | `post_bake_expansion_saturates` |

## DO

- Use `pick_fresh_fields_under_explored(n)` — biases toward `_ac/_er/_cfs/_inc` (under-tested)
- Use selective fund thresholds (1e6+ for numeric, large-company gates)
- Skip `_ac` categorical fields (style_box/financial_health_grade) entirely
- Use `ADD_VALS_PROVEN = (0.020, 0.040)` mags (a20 4.8% hit rate, a40 2.4%)
- Use `MAGS_PROVEN_BOOST = (1.25, 1.60, 1.70)` for mults
- Always run `pretick_or_die()` first (auto-bake + saturation guard)
- Always run `verify_noop_shift(label)` after bake apply
- Backup base before structural changes: `cp base.py base.py.pre_BAKE_X`

## Productive frontiers (predicted)

- `_inc` namespace: 12% covered, 161 untested fields with potential J0-style hits
- `_cfs` namespace: 13% covered, 172 untested fields
- `_er` rare-events: 12% covered, 22 untested fields (be careful with selectivity)
- Capital-structure adjacent to BAKE-J0 (preferred_stock_equity)

## Workflow per /loop tick

1. `auto_apply_bake(dry_run=True)` to check pretick
2. If candidate: review multi-mag pattern + apply if monotonic
3. Pick mode (`diversified` recommended unless specific hypothesis)
4. `pure_explore_round` or `domain_diversified_round`
5. Optional `extra(R)` callback for round-specific hypothesis (4-12 specs)
6. `run_audit_and_queue(R)`
7. `git commit` with audit summary
