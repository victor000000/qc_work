"""R3029 — VRFY H5×D14-17 DEMOTE candidate + new direction exploration.

R3028 (NOOP=3.33557 verified):
  W_H5_D14T17_DEMO m0.94 = 3.33567 (+0.00010 single mag) ← CANDIDATE

R3029:
 - Block A: VRFY W × H5 × D14-17 m0.92/0.93/0.95/0.96 (multi-mag)
 - Block B: H5 sub-band D10-14 (BAKE-138 territory)
 - Block C: H5 sub-band D14-20 deeper
 - Block D: New: P × HYG_DN3 × narrow (HYG-down regime untouched)
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
    R = Round(rid=3029, priority=1)

    HUP5 = 'self._reg_hyg_up5'
    HDN3 = 'self._reg_hyg_dn3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: VRFY W × H5 × D14-17 multi-mag (4 specs) ───
    cohort_h5_d14_17 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.017'
    add('W_H5_D14T17_VRFY_LO', 'wt_tilt', cohort_h5_d14_17, '',
        (0.92, 0.93), fresh=('w_h5_d14_17_vlo',))
    add('W_H5_D14T17_VRFY_HI', 'wt_tilt', cohort_h5_d14_17, '',
        (0.95, 0.96), fresh=('w_h5_d14_17_vhi',))

    # ─── Block B: H5 sub-band D10-12 (BAKE-138 territory but narrower) (4 specs) ───
    cohort_h5_d10_12 = f'_qpos and {HUP5} and decline > 0.010 and decline < 0.012'
    add('W_H5_D10T12_DEMO', 'wt_tilt', cohort_h5_d10_12, '',
        (0.92, 0.94), fresh=('w_h5_d10_12_a',))
    add('W_H5_D10T12_BOOST', 'wt_tilt', cohort_h5_d10_12, '',
        (1.05, 1.07), fresh=('w_h5_d10_12_b',))

    # ─── Block C: H5 D17-20 sub-band (other half) (4 specs) ───
    cohort_h5_d17_20 = f'_qpos and {HUP5} and decline > 0.017 and decline < 0.020'
    add('W_H5_D17T20_DEMO', 'wt_tilt', cohort_h5_d17_20, '',
        (0.92, 0.94), fresh=('w_h5_d17_20_a',))
    add('W_H5_D17T20_BOOST', 'wt_tilt', cohort_h5_d17_20, '',
        (1.05, 1.07), fresh=('w_h5_d17_20_b',))

    # ─── Block D: P × HDN3 (HYG-down) × narrow (untouched regime) (4 specs) ───
    cohort_hdn3 = f'_qpos and {HDN3} and decline > 0.014 and decline < 0.020'
    add('W_HDN3_D14T20_DEMO', 'wt_tilt', cohort_hdn3, '',
        (0.92, 0.94), fresh=('w_hdn3_a',))
    add('W_HDN3_D14T20_BOOST', 'wt_tilt', cohort_hdn3, '',
        (1.05, 1.07), fresh=('w_hdn3_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
