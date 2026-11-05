"""R3000 — Continue. C × H5 × D14T20 multi-mag confirmed BAKE-139 candidate.
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
    R = Round(rid=3000, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: C × H5 × D14T20 VRFY narrower (BAKE-139 candidate) (4 specs) ───
    cohort_h5 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.020'
    add('C_H5_D14T20_VRFY_M104', 'conv', cohort_h5, '',
        (1.04, 1.06), fresh=('c_h5_v_m104',))
    add('C_H5_D14T20_VRFY_M107', 'conv', cohort_h5, '',
        (1.07, 1.08), fresh=('c_h5_v_m107',))

    # ─── Block B: H3 D14T20 W incremental BOOST (find optimal m107-m110) (4 specs) ───
    cohort_h3 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_H3_D14T20_M108', 'wt_tilt', cohort_h3, '',
        (1.08, 1.09), fresh=('w_h3_m108',))
    add('W_H3_D14T20_M110', 'wt_tilt', cohort_h3, '',
        (1.10, 1.12), fresh=('w_h3_m110',))

    # ─── Block C: Q3 D14T20 W+C BOOST (parallel-cohort untested) (4 specs) ───
    cohort_q3 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.020'
    add('W_Q3_D14T20_M105_BOOST', 'wt_tilt', cohort_q3, '',
        (1.05, 1.07), fresh=('w_q3_m105',))
    add('C_Q3_D14T20_M105_BOOST', 'conv', cohort_q3, '',
        (1.05, 1.07), fresh=('c_q3_m105',))

    # ─── Block D: H5 D14T20 W higher mag (3 specs) ───
    add('W_H5_D14T20_M107_M110', 'wt_tilt', cohort_h5, '',
        (1.07, 1.10), fresh=('w_h5_m107',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
