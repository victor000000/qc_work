"""R3030 — Post-BAKE-149/150 verification + Q3 sub-band exploration.

R3028 NOOP=3.33557 (BAKE-148 verified).
R3029 multi-mag confirmed BAKE-149 (D14-17) and BAKE-150 (D17-20).
Expected R3030+ NOOP ≈ 3.33577.

R3030:
 - Block A: VRFY post-BAKE-149/150 with deeper mag (saturation check)
 - Block B: Q3 × D14-17 sub-band (parallel to H3/H5 D14-17 baked)
 - Block C: Q3 × D17-20 sub-band (parallel to H5 D17-20 baked)
 - Block D: H3 × D14-15 narrow (BAKE-136 sub-band — never tested narrow)
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
    R = Round(rid=3030, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: H5 D14-17 + D17-20 deeper VRFY (4 specs) ───
    cohort_h5_d14_17 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.017'
    add('W_H5_D14T17_SAT', 'wt_tilt', cohort_h5_d14_17, '',
        (0.96, 0.97), fresh=('w_h5_d14_17_sat',))
    cohort_h5_d17_20 = f'_qpos and {HUP5} and decline > 0.017 and decline < 0.020'
    add('W_H5_D17T20_SAT', 'wt_tilt', cohort_h5_d17_20, '',
        (0.96, 0.97), fresh=('w_h5_d17_20_sat',))

    # ─── Block B: Q3 × D14-17 sub-band (parallel) (4 specs) ───
    cohort_q3_d14_17 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.017'
    add('W_Q3_D14T17_DEMO_A', 'wt_tilt', cohort_q3_d14_17, '',
        (0.92, 0.94), fresh=('w_q3_d14_17_a',))
    add('W_Q3_D14T17_DEMO_B', 'wt_tilt', cohort_q3_d14_17, '',
        (0.96, 0.97), fresh=('w_q3_d14_17_b',))

    # ─── Block C: Q3 × D17-20 sub-band (parallel to H5) (4 specs) ───
    cohort_q3_d17_20 = f'_qpos and {QUP3} and decline > 0.017 and decline < 0.020'
    add('W_Q3_D17T20_DEMO_A', 'wt_tilt', cohort_q3_d17_20, '',
        (0.92, 0.94), fresh=('w_q3_d17_20_a',))
    add('W_Q3_D17T20_DEMO_B', 'wt_tilt', cohort_q3_d17_20, '',
        (0.96, 0.97), fresh=('w_q3_d17_20_b',))

    # ─── Block D: H3 × D14-15 narrow (BAKE-136 sub-band) (4 specs) ───
    cohort_h3_d14_15 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.015'
    add('W_H3_D14T15_DEMO', 'wt_tilt', cohort_h3_d14_15, '',
        (0.96, 0.97), fresh=('w_h3_d14_15_a',))
    add('W_H3_D14T15_BOOST', 'wt_tilt', cohort_h3_d14_15, '',
        (1.03, 1.05), fresh=('w_h3_d14_15_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
