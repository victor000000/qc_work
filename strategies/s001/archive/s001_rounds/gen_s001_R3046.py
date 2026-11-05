"""R3046 — Fresh-cohort W-DEMOTE template extension on UNTOUCHED regime×band combos.

R3042/R3043/R3044 verdicts:
  - S_Q3_D17T20_BOOST m1.03 was VARIANCE: m1.04/m1.05 BOTH = 3.33474 (-0.00124). DO NOT BAKE.
  - C × H5/Q3/DP cross-lever DEMOTE on baked cohorts (R3043) all NEG or NOOP.
  - W_H3_D20T25_DEMO m0.94 still pending (R3044 LO + R3045 deep/shallow in flight).
  - W_DP_D30T40 silent (NOOP).

R3046 strategy: extend productive W-DEMOTE template to UNTOUCHED regime/band combos.
Avoid: S_Q3, C×baked-cohorts, W_DP_D30T40, S_Q3_D14T17, W_H3 wide BOOST.

R3046 (16 specs):
 - Block A: W × VF × D02T04 (vxx_falling regime — totally UNTESTED for W lever)
 - Block B: W × Q3 × D14T17 (parallel of BAKE-151 D17-20)
 - Block C: W × H5 × D03T05 deep (BAKE-149/150 only at D14-20, deeper untested)
 - Block D: W × DP × no-HA × D025T030 (DP without HA gate, gap between BAKE-141/147 HA bakes)
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
    R = Round(rid=3046, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'
    VXF = 'self._reg_vxx_falling3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × VF × D02T04 (VF regime untouched for W) (4 specs) ───
    cohort_vf = f'_qpos and {VXF} and decline > 0.02 and decline < 0.04'
    add('W_VF_D02T04_DEMO_A', 'wt_tilt', cohort_vf, '',
        (0.92, 0.94), fresh=('w_vf_d02_a',))
    add('W_VF_D02T04_DEMO_B', 'wt_tilt', cohort_vf, '',
        (0.96, 0.97), fresh=('w_vf_d02_b',))

    # ─── Block B: W × Q3 × D14T17 (parallel of BAKE-151) (4 specs) ───
    cohort_q3_d14 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.017'
    add('W_Q3_D14T17_DEMO_A', 'wt_tilt', cohort_q3_d14, '',
        (0.92, 0.94), fresh=('w_q3_d14_a',))
    add('W_Q3_D14T17_DEMO_B', 'wt_tilt', cohort_q3_d14, '',
        (0.96, 0.97), fresh=('w_q3_d14_b',))

    # ─── Block C: W × H5 × D03T05 (deeper H5 band) (4 specs) ───
    cohort_h5_d30 = f'_qpos and {HUP5} and decline > 0.03 and decline < 0.05'
    add('W_H5_D03T05_DEMO_A', 'wt_tilt', cohort_h5_d30, '',
        (0.90, 0.92), fresh=('w_h5_d30_a',))
    add('W_H5_D03T05_DEMO_B', 'wt_tilt', cohort_h5_d30, '',
        (0.94, 0.96), fresh=('w_h5_d30_b',))

    # ─── Block D: W × DP × no-HA × D025T030 (DP gap) (4 specs) ───
    cohort_dp_noha = (f'_qpos and {DPANIC} and not (HA and HA>0)'
                      f' and decline > 0.025 and decline < 0.030')
    add('W_DP_NOHA_D25T30_DEMO_A', 'wt_tilt', cohort_dp_noha, '',
        (0.92, 0.94), fresh=('w_dp_noha_a',))
    add('W_DP_NOHA_D25T30_DEMO_B', 'wt_tilt', cohort_dp_noha, '',
        (0.96, 0.97), fresh=('w_dp_noha_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
