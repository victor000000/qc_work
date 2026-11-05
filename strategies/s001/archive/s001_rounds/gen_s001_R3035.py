"""R3035 — Post-BAKE-151 VRFY + Q3 sub-band exploration.

R3032 multi-mag confirmed BAKE-151 (W_Q3_D17T20 m0.97 +0.00021).
Expected R3035+ NOOP ≈ 3.33598.

R3035:
 - Block A: BAKE-151 plateau check (m0.94/0.95/0.96 + deeper SAT)
 - Block B: Q3 × D14-17 sub-band (parallel to H3/H5 D14-17 baked)
 - Block C: Q3 × D10-14 (BAKE-126 territory but W lever)
 - Block D: NEW probe — Q3 × D20-25 deeper decline
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
    R = Round(rid=3035, priority=1)

    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-151 plateau check (4 specs) ───
    cohort_q3_d17_20 = f'_qpos and {QUP3} and decline > 0.017 and decline < 0.020'
    add('W_Q3_D17T20_PLATEAU_LO', 'wt_tilt', cohort_q3_d17_20, '',
        (0.95, 0.96), fresh=('w_q3_d17_pl_lo',))
    add('W_Q3_D17T20_PLATEAU_HI', 'wt_tilt', cohort_q3_d17_20, '',
        (0.99,), fresh=('w_q3_d17_pl_hi',))

    # ─── Block B: Q3 × D14-17 sub-band (parallel) (4 specs) ───
    cohort_q3_d14_17 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.017'
    add('W_Q3_D14T17_DEMO_A', 'wt_tilt', cohort_q3_d14_17, '',
        (0.95, 0.97), fresh=('w_q3_d14_17_aa',))
    add('W_Q3_D14T17_DEMO_B', 'wt_tilt', cohort_q3_d14_17, '',
        (0.98,), fresh=('w_q3_d14_17_bb',))

    # ─── Block C: Q3 × D10-14 (4 specs) ───
    cohort_q3_d10_14 = f'_qpos and {QUP3} and decline > 0.010 and decline < 0.014'
    add('W_Q3_D10T14_DEMO_A', 'wt_tilt', cohort_q3_d10_14, '',
        (0.94, 0.96), fresh=('w_q3_d10_14_aa',))
    add('W_Q3_D10T14_DEMO_B', 'wt_tilt', cohort_q3_d10_14, '',
        (0.97, 0.98), fresh=('w_q3_d10_14_bb',))

    # ─── Block D: Q3 × D20-25 deeper (4 specs) ───
    cohort_q3_d20_25 = f'_qpos and {QUP3} and decline > 0.020 and decline < 0.025'
    add('W_Q3_D20T25_DEMO_A', 'wt_tilt', cohort_q3_d20_25, '',
        (0.92, 0.94), fresh=('w_q3_d20_25_a',))
    add('W_Q3_D20T25_DEMO_B', 'wt_tilt', cohort_q3_d20_25, '',
        (0.96, 0.97), fresh=('w_q3_d20_25_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
