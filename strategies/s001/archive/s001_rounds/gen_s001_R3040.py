"""R3040 — Continue diverse exploration after plateau.

R3036 NOOP=3.33598 verified. Session at +0.01670 verified.

R3040 explores untouched Z (qzero) × rally compounds:
 - Block A: W × Z × Q3 × .017<d<.020 (qzero on Q3 BAKE-151 cohort)
 - Block B: W × Z × HUP5 × .014<d<.017 (qzero on H5 BAKE-149 cohort)
 - Block C: W × Z × HUP5 × .017<d<.020 (qzero on H5 BAKE-150 cohort)
 - Block D: W × Z × HUP3 × HUP5 narrow intersect
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
    R = Round(rid=3040, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × Z × Q3 × .017<d<.020 (4 specs) ───
    cohort_z_q3 = f'_qzero and {QUP3} and decline > 0.017 and decline < 0.020'
    add('W_Z_Q3_D17T20_DEMO_A', 'wt_tilt', cohort_z_q3, '',
        (0.92, 0.94), fresh=('w_z_q3_a',))
    add('W_Z_Q3_D17T20_DEMO_B', 'wt_tilt', cohort_z_q3, '',
        (0.96, 0.97), fresh=('w_z_q3_b',))

    # ─── Block B: W × Z × HUP5 × .014<d<.017 (4 specs) ───
    cohort_z_h5_d14 = f'_qzero and {HUP5} and decline > 0.014 and decline < 0.017'
    add('W_Z_H5_D14T17_DEMO_A', 'wt_tilt', cohort_z_h5_d14, '',
        (0.92, 0.94), fresh=('w_z_h5_d14_a',))
    add('W_Z_H5_D14T17_DEMO_B', 'wt_tilt', cohort_z_h5_d14, '',
        (0.96, 0.97), fresh=('w_z_h5_d14_b',))

    # ─── Block C: W × Z × HUP5 × .017<d<.020 (4 specs) ───
    cohort_z_h5_d17 = f'_qzero and {HUP5} and decline > 0.017 and decline < 0.020'
    add('W_Z_H5_D17T20_DEMO_A', 'wt_tilt', cohort_z_h5_d17, '',
        (0.92, 0.94), fresh=('w_z_h5_d17_a',))
    add('W_Z_H5_D17T20_DEMO_B', 'wt_tilt', cohort_z_h5_d17, '',
        (0.96, 0.97), fresh=('w_z_h5_d17_b',))

    # ─── Block D: W × Z × HUP3 × HUP5 intersect compound (4 specs) ───
    cohort_z_h3_h5 = f'_qzero and {HUP3} and {HUP5} and decline > 0.014 and decline < 0.020'
    add('W_Z_H3H5_D14T20_DEMO', 'wt_tilt', cohort_z_h3_h5, '',
        (0.92, 0.94), fresh=('w_z_h3h5_a',))
    add('W_Z_H3H5_D14T20_BOOST', 'wt_tilt', cohort_z_h3_h5, '',
        (1.05, 1.07), fresh=('w_z_h3h5_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
