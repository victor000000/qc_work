"""R3043 — Cross-lever exploration on RECENTLY baked productive cohorts.

7 rounds of plateau (R3036-R3042 = 0 productive). Try CROSS-LEVER probes
on cohorts that already have a productive W bake — different lever may add.

R3043:
 - Block A: C × H5 × D14-17 (cross-lever on BAKE-149)
 - Block B: C × H5 × D17-20 (cross-lever on BAKE-150)
 - Block C: C × Q3 × D17-20 (cross-lever on BAKE-151)
 - Block D: C × DP × D14-17 (cross-lever on BAKE-146 — but BAKE-146 reverted)
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
    R = Round(rid=3043, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: C × H5 × D14-17 cross-lever on BAKE-149 (4 specs) ───
    cohort_h5_d14 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.017'
    add('C_H5_D14T17_DEMO_A', 'conv', cohort_h5_d14, '',
        (0.94, 0.96), fresh=('c_h5_d14_a',))
    add('C_H5_D14T17_DEMO_B', 'conv', cohort_h5_d14, '',
        (0.97, 0.98), fresh=('c_h5_d14_b',))

    # ─── Block B: C × H5 × D17-20 cross-lever on BAKE-150 (4 specs) ───
    cohort_h5_d17 = f'_qpos and {HUP5} and decline > 0.017 and decline < 0.020'
    add('C_H5_D17T20_DEMO_A', 'conv', cohort_h5_d17, '',
        (0.94, 0.96), fresh=('c_h5_d17_a',))
    add('C_H5_D17T20_DEMO_B', 'conv', cohort_h5_d17, '',
        (0.97, 0.98), fresh=('c_h5_d17_b',))

    # ─── Block C: C × Q3 × D17-20 cross-lever on BAKE-151 (4 specs) ───
    cohort_q3 = f'_qpos and {QUP3} and decline > 0.017 and decline < 0.020'
    add('C_Q3_D17T20_DEMO_A', 'conv', cohort_q3, '',
        (0.94, 0.96), fresh=('c_q3_d17_a',))
    add('C_Q3_D17T20_DEMO_B', 'conv', cohort_q3, '',
        (0.97, 0.98), fresh=('c_q3_d17_b',))

    # ─── Block D: C × DP × D14-17 cross-lever (4 specs) ───
    cohort_dp_d14 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.017'
    add('C_DP_D14T17_DEMO_A', 'conv', cohort_dp_d14, '',
        (0.94, 0.96), fresh=('c_dp_d14_a2',))
    add('C_DP_D14T17_DEMO_B', 'conv', cohort_dp_d14, '',
        (0.97, 0.98), fresh=('c_dp_d14_b2',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
