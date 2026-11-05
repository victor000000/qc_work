"""R3001 — R2991 reveals BAKE-136 may be under-tuned. m1.12-m1.20 ALL give +0.00082 std=0.
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
        print(f'BYPASS pretick')
    R = Round(rid=3001, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: H3 D14T20 W BOOST extreme (m1.15-m1.25) (4 specs) ───
    cohort_h3 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_H3_D14T20_M115_M118', 'wt_tilt', cohort_h3, '',
        (1.15, 1.18), fresh=('w_h3_m115',))
    add('W_H3_D14T20_M122_M125', 'wt_tilt', cohort_h3, '',
        (1.22, 1.25), fresh=('w_h3_m122',))

    # ─── Block B: H5 D14T20 W BOOST extreme (parallel to H3) (4 specs) ───
    cohort_h5 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.020'
    add('W_H5_D14T20_M112_M115', 'wt_tilt', cohort_h5, '',
        (1.12, 1.15), fresh=('w_h5_m112',))
    add('W_H5_D14T20_M118_M120', 'wt_tilt', cohort_h5, '',
        (1.18, 1.20), fresh=('w_h5_m118',))

    # ─── Block C: Q3 D14T20 W+C BOOST extreme (parallel cohort) (4 specs) ───
    cohort_q3 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.020'
    add('W_Q3_D14T20_M112_M115', 'wt_tilt', cohort_q3, '',
        (1.12, 1.15), fresh=('w_q3_m112',))
    add('C_Q3_D14T20_M108_M112', 'conv', cohort_q3, '',
        (1.08, 1.12), fresh=('c_q3_m108',))

    # ─── Block D: H3 D14T20 C BOOST extreme (3rd lever validation) (3 specs) ───
    add('C_H3_D14T20_M112_M115', 'conv', cohort_h3, '',
        (1.12, 1.15), fresh=('c_h3_m112',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
