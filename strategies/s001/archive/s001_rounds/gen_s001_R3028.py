"""R3028 — First post-BAKE-148 round + diverse explorations.

R3027 NOOP=3.33546 (BAKE-148 not in spec). R3028 reveals BAKE-148 effect.

R3028:
 - Block A: W × P × HUP3 × D9-10 narrow (untouched sub-band)
 - Block B: W × P × HUP5 × D14-17 (parallel to BAKE-147 baked H3, but H5)
 - Block C: SECTOR S308 × P × HUP3 × D14-20 (sector+rally compound)
 - Block D: SECTOR S206 × P × HUP3 × D14-20 (parallel sector)
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
    R = Round(rid=3028, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × HUP3 × D9-10 narrow (untouched) (4 specs) ───
    cohort_h3_d9_10 = f'_qpos and {HUP3} and decline > 0.009 and decline < 0.010'
    add('W_H3_D9T10_DEMO', 'wt_tilt', cohort_h3_d9_10, '',
        (0.92, 0.94), fresh=('w_h3_d9_10_a',))
    add('W_H3_D9T10_BOOST', 'wt_tilt', cohort_h3_d9_10, '',
        (1.05, 1.07), fresh=('w_h3_d9_10_b',))

    # ─── Block B: W × P × HUP5 × D14-17 (4 specs) ───
    cohort_h5_d14_17 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.017'
    add('W_H5_D14T17_DEMO', 'wt_tilt', cohort_h5_d14_17, '',
        (0.92, 0.94), fresh=('w_h5_d14_17_a',))
    add('W_H5_D14T17_BOOST', 'wt_tilt', cohort_h5_d14_17, '',
        (1.06, 1.08), fresh=('w_h5_d14_17_b',))

    # ─── Block C: SECTOR S308 × P × HUP3 × D14-20 (4 specs) ───
    cohort_s308_h3 = f'_qpos and _secc == 308 and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_S308_H3_D14T20_DEMO_A', 'wt_tilt', cohort_s308_h3, '',
        (0.88, 0.90), fresh=('w_s308_h3_aa',))
    add('W_S308_H3_D14T20_DEMO_B', 'wt_tilt', cohort_s308_h3, '',
        (0.93, 0.95), fresh=('w_s308_h3_bb',))

    # ─── Block D: SECTOR S206 × P × HUP3 × D14-20 (4 specs) ───
    cohort_s206_h3 = f'_qpos and _secc == 206 and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_S206_H3_D14T20_DEMO_A', 'wt_tilt', cohort_s206_h3, '',
        (0.88, 0.90), fresh=('w_s206_h3_aa',))
    add('W_S206_H3_D14T20_DEMO_B', 'wt_tilt', cohort_s206_h3, '',
        (0.93, 0.95), fresh=('w_s206_h3_bb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
