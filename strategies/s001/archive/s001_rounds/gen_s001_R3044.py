"""R3044 — VRFY R3042 candidates with multi-mag.

R3042 produced 2 single-mag candidates above NOOP=3.33598:
  S_Q3_D17T20_BOOST m1.03 = 3.33639 (+0.00041)
  W_H3_D20T25_DEMO m0.94 = 3.33629 (+0.00031)

CRITICAL: Need multi-mag confirmation before baking (probe-vs-bake risk).

R3044:
 - Block A: S × Q3 × D17-20 BOOST m1.02/1.04/1.05 (verify plateau)
 - Block B: W × H3 × D20-25 DEMOTE m0.92/0.95/0.96 (verify plateau)
 - Block C: Parallel cohorts — S × Q3 × D14-17 BOOST (less productive parallel)
 - Block D: Parallel — W × H3 × D17-20 (BAKE-136 territory adjacent)
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
    R = Round(rid=3044, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: S × Q3 × D17-20 BOOST multi-mag VRFY (4 specs) ───
    cohort_q3_d17 = f'_qpos and {QUP3} and decline > 0.017 and decline < 0.020'
    add('S_Q3_D17T20_BOOST_VRFY_LO', 'score', cohort_q3_d17, '',
        (1.02, 1.025), fresh=('s_q3_d17_v_lo',))
    add('S_Q3_D17T20_BOOST_VRFY_HI', 'score', cohort_q3_d17, '',
        (1.04, 1.05), fresh=('s_q3_d17_v_hi',))

    # ─── Block B: W × H3 × D20-25 DEMOTE multi-mag VRFY (4 specs) ───
    cohort_h3_d20 = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.025'
    add('W_H3_D20T25_VRFY_LO', 'wt_tilt', cohort_h3_d20, '',
        (0.92, 0.93), fresh=('w_h3_d20_v_lo',))
    add('W_H3_D20T25_VRFY_HI', 'wt_tilt', cohort_h3_d20, '',
        (0.95, 0.96), fresh=('w_h3_d20_v_hi',))

    # ─── Block C: S × Q3 × D14-17 BOOST (parallel cohort) (4 specs) ───
    cohort_q3_d14 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.017'
    add('S_Q3_D14T17_BOOST_VRFY_LO', 'score', cohort_q3_d14, '',
        (1.02, 1.03), fresh=('s_q3_d14_v_lo',))
    add('S_Q3_D14T17_BOOST_VRFY_HI', 'score', cohort_q3_d14, '',
        (1.04, 1.05), fresh=('s_q3_d14_v_hi',))

    # ─── Block D: W × H3 × D17-20 DEMOTE (BAKE-136 adjacent) (4 specs) ───
    cohort_h3_d17 = f'_qpos and {HUP3} and decline > 0.017 and decline < 0.020'
    add('W_H3_D17T20_DEMO_A', 'wt_tilt', cohort_h3_d17, '',
        (0.92, 0.94), fresh=('w_h3_d17_xa',))
    add('W_H3_D17T20_DEMO_B', 'wt_tilt', cohort_h3_d17, '',
        (0.96, 0.97), fresh=('w_h3_d17_xb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
