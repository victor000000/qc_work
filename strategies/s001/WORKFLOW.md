> Documentation scope correction (2026-11-07): the May 10 workflow below is a dated research protocol, not standing authorization to queue new 128-spec rounds. Current workspace setup, isolated unit tests, credentials and operational boundaries are in [CI](../../docs/CI_CD.md) and [operations](../../docs/OPERATIONS.md). Historical bakes/guard thresholds require their original research state; the documentation audit does not revalidate their economics.

# S001 — 128-Spec Meaningful-Backtest Workflow (Reconstructed 2026-05-10)

User hard constraint (repeated 15+ times): **every /loop tick must queue 128 ±10 meaningful specs. No padding. No waste.**

## Single command

```bash
.venv/bin/python -m s001.next_round_s001
```

Auto-detects next RID, rotates between 2-regime / 3-regime productive compound patterns, queues 128 ±10 specs that pass all 9 audit guards.

For custom rounds, write `strategies/s001/gen_s001_RNNNN.py` using `build_128_round()`:

```python
from s001.gen_s001_strategies import (
    pretick_or_die, run_audit_and_queue, build_128_round,
    T128_WT_MAGS, T128_GATE_MAGS, T128_MTF_MAGS, T128_REGIME_MAGS, T128_SD,
)

def main():
    pretick_or_die()
    blocks = [
        # 5 wt_tilt + 1 gate + 4 score-class
        ('A_...', 'wt_tilt', '_qsneg and ...', 0, T128_WT_MAGS, '*='),
        # ...
    ]
    R = build_128_round(rid=NNNN, blocks=blocks)
    return run_audit_and_queue(R)
```

## 9 audit guards (all in `run_audit_and_queue`)

| Guard | Action | Purpose |
|---|---|---|
| cohort_var_check | drop | forbidden vars (`_qpos` etc. in EXIT scope) |
| never_fires_check | drop / mag-prune | known-silent patterns from memory |
| lever_quota | raise | ≤50% score, ≥30% non-score |
| P7 anti-padding | drop | single-mag fresh × proven-saturated cell |
| P6 cohort overlap | drop | >40% token overlap with active bake (lever-aware) |
| P5 capture-ratio | virgin lock | recent 3-round capture <60% → virgin-only |
| P10 productive-regime | drop | cohort lacks `{haccel, vxx_falling3, double_panic, qqq_up3, hyg_dn14}` |
| P9 fire-rate | drop | accessor empirical fire rate <5%@30 trials |
| AUTO-TRIM | drop | post-prune > 138 → drop main probes from end |
| P8 128-band | raise | est < 118 or > 138 |

## Productive vs virgin regimes (empirical)

| Regime | Active bakes | Use? |
|---|---|---|
| _reg_haccel | 17 | YES |
| _reg_vxx_falling3 | 5 | YES |
| _reg_double_panic | 4 | YES |
| _reg_qqq_up3 | 3 | YES |
| _reg_hyg_dn14 | 2 | YES |
| _reg_hyg_dn3, dn5, up3, up5 | 1 each | borderline |
| _reg_qqq_up5, up14, hyg_up7, hyg_up14, vxx_low | 0 | **NO** (R1894/R1895 = 0% yield empirical) |

## Patterns ranked by yield (R1894-R1911 measured)

| Pattern | Yield | Top Δ | Bakes |
|---|---|---|---|
| **🎯 Sector × _qpos × productive × NO decline** | **27%** | **+0.0048** | **R1909 verified** |
| **_hi_vol/_hi_cape × _qpos × productive × NO decline** | **78%** | +0.0011 | (sub-threshold) |
| 2-regime productive × _qzero × small_dec | 46% | +0.0023 | R1897 verified |
| 2-regime productive (different pairs) | 38% | +0.0030 | invalidated |
| 3-regime productive × _qsneg/_qzero | 27% | +0.0004 | variance |
| Sector × productive × _qsneg × small_dec | 2-10% | 0 | variance |
| Mixed-virgin × _qzero/qsneg × small_dec | 11% | +0.0001 | none |
| Virgin regimes × _qpos × small_dec | 0% | 0 | none |

**Key finding (2026-05-11):** Removing the decline filter is the productive frontier. Active bakes share `dec_lo + dec_hi` tokens; no-decline cohorts drop those, opening the cohort space.

**Verified bakes — new workflow (2026-05-11):**
| RID | Lift | Cohort key |
|-----|------|-----------|
| R1897 | +0.0024 ✓ | _qzero × VF×Q3 × small_dec × investing |
| R1909 | +0.0047 ✓ | _qpos × S311 × DP × no_dec × investing |
| R1912 | +0.0063 ✓ | _qpos × S311 × Q3 × no_dec × investing |
| R1916 | +0.0043 ✓ | _qzero × S311 × VF × no_dec × investing |
| R1917 | +0.0010 ✓ | _qzero × S311 × DP × no_dec × investing |
| R1918 | +0.0034 ✓ | _qzero × S311 × Q3 × no_dec × investing |
| R1919 | +0.0015 ✓ | _qpos × S311 × HD14 × no_dec × investing |
| R1920 | +0.0007 | _qpos × S310 × HA × no_dec × investing |

**Cumulative VERIFIED: +0.0244 (+7.3% strategy lift, 8 DEMOTE bakes).**

**🎯 BOOST direction breakthrough (R1928-R1931):** Bidirectional productivity confirmed. 3 BOOST bakes:
  - R1928: _qzero × S311 × HA × +0.0022 ✓ verified
  - R1930: _qzero × S311 × HD14 × +0.0030 (under-delivered: +0.0008 actual, cohort_saturation)
  - R1931: _qpos × S311 × VF × +0.0012 (pending verify)

**Verified cumulative: +0.0348 (+10.42%).** 19 bakes applied. Lineages:
  - wt_tilt DEMOTE (8 bakes)
  - wt_tilt BOOST (5 bakes)
  - score *= BOOST (1)
  - wt_tilt 2-regime BOOST (1)
  - Minor regimes HD3/HD5 (3 bakes — R1939, R1940, R1942)
  - **entry_score_quality (1 bake — R1944) ← score-class lever pivot**

R1944 had 12 candidates from non-wt_tilt levers — P6 lever-aware unlocked score-class on saturated cohort cells.

**Diminishing returns confirmed (2026-05-11):** Last 2 verified bakes (R1931, R1932) delivered ~33% of predicted lift (cohort_saturation from same-cell stacking). 14 bakes is approaching the strategy's near-term productive ceiling.

**FINAL STATE (2026-05-11 R1936 deep review):** 15 bakes / +0.0297 verified / +0.0391 predicted (76% delivery). Workflow at hard saturation:
  - R1936 (score lever × deep decline 0.10-0.20): 11% yield, 0 bakes — deep decline is also null
  - Yield collapsing 60% (R1934) → 31% (R1935) → 11% (R1936)
  - All productive lever × direction × cohort combinations tested
  - Further rounds will produce 0-1 bake at <+0.001 delta (variance noise)

**Recommendation:** Accept the 15-bake / +8.36% lift as the new-workflow ceiling. Future improvements require base-structural changes (different score function, decline-window logic, lever math) which carry catastrophic-regression risk per memory.

**Score lever sub-threshold (R1929):** score += on productive cells gave +0.0019 top delta but propose_bakes returned 0 candidates — multi-mag inconsistent. score lever doesn't reliably translate productive cohort signal to bake. wt_tilt remains the primary productive lever.

Productive concentration: S311 = 6 bakes, S310 = 1 bake, S{all-others} = 0 bakes. Investing-theme accessors (`*investing*`, `*gain*`, `*sale_of_security*`, `*ppe*`, `*equity_interest*`) consistently productive on S311 × productive_regime × no_decline cells.

## Bypass (diagnostic rounds only)

```bash
S001_BYPASS_128_GUARD=1 S001_BYPASS_REGIME_GUARD=1 S001_BYPASS_FIRE_GUARD=1 \
    python3 data/gen_s001_R1833.py
```

## Validated bakes from new workflow

- **BAKE-H_WZ_VFQ3-R1897**: `_qzero × small_dec × vxx_falling3 × qqq_up3 × wt_tilt *= 0.60` = **+0.00234 lift**
