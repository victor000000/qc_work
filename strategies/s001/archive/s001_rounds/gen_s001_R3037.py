"""R3037 — Cautious exploration pending R3035 NOOP verification.

R3035 first 2 done show NEG/cliff. NOOP_0 pending — will reveal if BAKE-151
worked or needs revert.

R3037 explores diverse NEW directions (no compositional risk):
 - Block A: W × P × HUP3 × D14-15 narrow shallow (untouched narrow)
 - Block B: W × P × HUP5 × D10-12 (parallel to BAKE-142 H3)
 - Block C: W × P × Q3 × D14-16 (BAKE-125 ER territory but W lever)
 - Block D: W × P × DPANIC × D17-20 (untested DP narrow)
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
    R = Round(rid=3037, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × H3 × D13-14 ultra narrow (4 specs) ───
    cohort_h3_d13_14 = f'_qpos and {HUP3} and decline > 0.013 and decline < 0.014'
    add('W_H3_D13T14_DEMO', 'wt_tilt', cohort_h3_d13_14, '',
        (0.94, 0.96), fresh=('w_h3_d13_14_a',))
    add('W_H3_D13T14_BOOST', 'wt_tilt', cohort_h3_d13_14, '',
        (1.05, 1.07), fresh=('w_h3_d13_14_b',))

    # ─── Block B: W × H5 × D10-12 (parallel to BAKE-142 H3) (4 specs) ───
    cohort_h5_d10_12 = f'_qpos and {HUP5} and decline > 0.010 and decline < 0.012'
    add('W_H5_D10T12_DEMO_A', 'wt_tilt', cohort_h5_d10_12, '',
        (0.92, 0.94), fresh=('w_h5_d10_12_a',))
    add('W_H5_D10T12_DEMO_B', 'wt_tilt', cohort_h5_d10_12, '',
        (0.96, 0.97), fresh=('w_h5_d10_12_b',))

    # ─── Block C: W × Q3 × D14-16 (BAKE-125 ER territory, W lever) (4 specs) ───
    cohort_q3_d14_16 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.016'
    add('W_Q3_D14T16_DEMO_A', 'wt_tilt', cohort_q3_d14_16, '',
        (0.95, 0.97), fresh=('w_q3_d14_16_a',))
    add('W_Q3_D14T16_DEMO_B', 'wt_tilt', cohort_q3_d14_16, '',
        (0.98,), fresh=('w_q3_d14_16_b',))

    # ─── Block D: W × DPANIC × D17-20 (untested DP narrow) (4 specs) ───
    cohort_dp_d17_20 = f'_qpos and {DPANIC} and decline > 0.017 and decline < 0.020'
    add('W_DP_D17T20_DEMO_A', 'wt_tilt', cohort_dp_d17_20, '',
        (0.92, 0.94), fresh=('w_dp_d17_20_aa',))
    add('W_DP_D17T20_DEMO_B', 'wt_tilt', cohort_dp_d17_20, '',
        (0.96, 0.97), fresh=('w_dp_d17_20_bb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
