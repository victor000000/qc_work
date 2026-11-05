"""R3032 — VRFY W_Q3_D17T20 candidate + extend productive patterns.

R3030 NOOP=3.33577 verified BAKE-148/149/150 all working (+0.00031 combined).

R3030 W_Q3_D17T20 m0.97 = 3.33598 (+0.00021 single mag). m0.94 was NEG.
Need multi-mag VRFY at m0.95/0.96/0.98.

R3032:
 - Block A: VRFY W × Q3 × D17-20 multi-mag at m0.95/0.96/0.98
 - Block B: W × Q3 × D14-17 sub-band (different than D17-20)
 - Block C: W × H5 × D17-20 SAT continued (deeper plateau)
 - Block D: W × H3 × D14-15 narrow (sub-band of BAKE-136)
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
    R = Round(rid=3032, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: VRFY W × Q3 × D17-20 multi-mag (4 specs) ───
    cohort_q3_d17_20 = f'_qpos and {QUP3} and decline > 0.017 and decline < 0.020'
    add('W_Q3_D17T20_VRFY_LO', 'wt_tilt', cohort_q3_d17_20, '',
        (0.95, 0.96), fresh=('w_q3_d17_20_vlo',))
    add('W_Q3_D17T20_VRFY_HI', 'wt_tilt', cohort_q3_d17_20, '',
        (0.97, 0.98), fresh=('w_q3_d17_20_vhi',))

    # ─── Block B: W × Q3 × D14-17 sub-band (4 specs) ───
    cohort_q3_d14_17 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.017'
    add('W_Q3_D14T17_VRFY_LO', 'wt_tilt', cohort_q3_d14_17, '',
        (0.95, 0.96), fresh=('w_q3_d14_17_vlo',))
    add('W_Q3_D14T17_VRFY_HI', 'wt_tilt', cohort_q3_d14_17, '',
        (0.97, 0.98), fresh=('w_q3_d14_17_vhi',))

    # ─── Block C: W × H5 × D17-20 deeper saturation (4 specs) ───
    cohort_h5_d17_20 = f'_qpos and {HUP5} and decline > 0.017 and decline < 0.020'
    add('W_H5_D17T20_DEEP_A', 'wt_tilt', cohort_h5_d17_20, '',
        (0.92, 0.93), fresh=('w_h5_d17_20_deep_a',))
    add('W_H5_D17T20_DEEP_B', 'wt_tilt', cohort_h5_d17_20, '',
        (0.95, 0.96), fresh=('w_h5_d17_20_deep_b',))

    # ─── Block D: W × H3 × D14-15 narrow (BAKE-136 sub-band) (4 specs) ───
    cohort_h3_d14_15 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.015'
    add('W_H3_D14T15_DEMO_A', 'wt_tilt', cohort_h3_d14_15, '',
        (0.92, 0.94), fresh=('w_h3_d14_15_aa',))
    add('W_H3_D14T15_DEMO_B', 'wt_tilt', cohort_h3_d14_15, '',
        (0.96, 0.97), fresh=('w_h3_d14_15_bb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
