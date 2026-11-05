"""R3013 — BAKE-141 NOOP verification + further sub-band exploration.

BAKE-141 applied (W_DP_HA_D25T30 m0.88). Expected R3013 NOOP ≈ 3.33505.

Strategy: continue sub-band exploration within BAKE-139/140 cohorts.
 - BAKE-139 D20-40 → D25-30 baked (BAKE-141). Remaining sub-bands: D20-25, D30-35
 - BAKE-140 D10-14 → sub-bands D10-12, D12-14 untested

Note: probes here STACK on BAKE-139, BAKE-140, BAKE-141. Effective wt_tilt
on a fully-stacked cohort can reach 0.88×0.88 = 0.77 (BAKE-139+BAKE-141).
═══════════════════════════════════════════════════════════════════════
"""
import os
os.environ['S001_MIN_FRESH'] = '0'

from gen_s001_lib import Probe, Round
from gen_s001_strategies import (
    pretick_or_die, run_audit_and_queue,
    add_productive_aux_blocks,
)


def main():
    try:
        pretick_or_die()
    except RuntimeError as e:
        if 'bake-eligible' not in str(e):
            raise
        print('BYPASS pretick')
    R = Round(rid=3013, priority=1)

    DPANIC = 'self._reg_double_panic'
    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-139 D20-25 sub-band (4 specs) ───
    cohort_d20 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.025'
    add('W_DP_HA_D20T25_DEMO_A', 'wt_tilt', cohort_d20, '',
        (0.92, 0.94), fresh=('w_d20_a',))
    add('W_DP_HA_D20T25_DEMO_B', 'wt_tilt', cohort_d20, '',
        (0.96, 0.97), fresh=('w_d20_b',))

    # ─── Block B: BAKE-139 D30-35 sub-band (4 specs) ───
    cohort_d30 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.030 and decline < 0.035'
    add('W_DP_HA_D30T35_DEMO_A', 'wt_tilt', cohort_d30, '',
        (0.92, 0.94), fresh=('w_d30_a',))
    add('W_DP_HA_D30T35_DEMO_B', 'wt_tilt', cohort_d30, '',
        (0.96, 0.97), fresh=('w_d30_b',))

    # ─── Block C: BAKE-140 sub-band D12-14 (4 specs) ───
    cohort_h3_d12 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.012 and decline < 0.014'
    add('W_H3_HA_D12T14_VRFY_A', 'wt_tilt', cohort_h3_d12, '',
        (0.94, 0.96), fresh=('w_h3_d12_a',))
    add('W_H3_HA_D12T14_VRFY_B', 'wt_tilt', cohort_h3_d12, '',
        (0.97, 0.98), fresh=('w_h3_d12_b',))

    # ─── Block D: BAKE-140 sub-band D10-12 (4 specs) ───
    cohort_h3_d10 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.012'
    add('W_H3_HA_D10T12_VRFY_A', 'wt_tilt', cohort_h3_d10, '',
        (0.94, 0.96), fresh=('w_h3_d10_a',))
    add('W_H3_HA_D10T12_VRFY_B', 'wt_tilt', cohort_h3_d10, '',
        (0.97, 0.98), fresh=('w_h3_d10_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
