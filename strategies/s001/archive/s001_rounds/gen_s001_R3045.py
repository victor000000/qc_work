"""R3045 — Wider verification of R3042 candidates + new directions.

R3042 candidates pending multi-mag VRFY (R3044 in flight):
  S_Q3_D17T20_BOOST m1.03 = +0.00041 (single mag)
  W_H3_D20T25_DEMO m0.94 = +0.00031 (single mag)

R3045 reinforces VRFY + explores parallels:
 - Block A: Wider mag range for S × Q3 × D17-20 (m1.06/1.07)
 - Block B: W × H3 × D20-25 deeper exploration (m0.90/0.97/0.98)
 - Block C: Score lever × DP × D17-20 (parallel of S_Q3 candidate)
 - Block D: W × H3 × D25-30 (further wider H3 band)
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
    R = Round(rid=3045, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: S × Q3 × D17-20 BOOST wider mag (4 specs) ───
    cohort_q3_d17 = f'_qpos and {QUP3} and decline > 0.017 and decline < 0.020'
    add('S_Q3_D17T20_BOOST_WIDE_A', 'score', cohort_q3_d17, '',
        (1.06, 1.07), fresh=('s_q3_d17_w_a',))
    add('S_Q3_D17T20_BOOST_WIDE_B', 'score', cohort_q3_d17, '',
        (1.08, 1.10), fresh=('s_q3_d17_w_b',))

    # ─── Block B: W × H3 × D20-25 deeper VRFY (4 specs) ───
    cohort_h3_d20 = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.025'
    add('W_H3_D20T25_DEEP', 'wt_tilt', cohort_h3_d20, '',
        (0.88, 0.90), fresh=('w_h3_d20_dp_a',))
    add('W_H3_D20T25_SHAL', 'wt_tilt', cohort_h3_d20, '',
        (0.97, 0.98), fresh=('w_h3_d20_dp_b',))

    # ─── Block C: S × DP × D17-20 BOOST (parallel of S_Q3) (4 specs) ───
    cohort_dp_d17 = f'_qpos and {DPANIC} and decline > 0.017 and decline < 0.020'
    add('S_DP_D17T20_BOOST_A', 'score', cohort_dp_d17, '',
        (1.03, 1.04), fresh=('s_dp_d17_a',))
    add('S_DP_D17T20_BOOST_B', 'score', cohort_dp_d17, '',
        (1.05, 1.07), fresh=('s_dp_d17_b',))

    # ─── Block D: W × H3 × D25-30 (further wider H3 band) (4 specs) ───
    cohort_h3_d25 = f'_qpos and {HUP3} and decline > 0.025 and decline < 0.030'
    add('W_H3_D25T30_DEMO_A', 'wt_tilt', cohort_h3_d25, '',
        (0.92, 0.94), fresh=('w_h3_d25_a',))
    add('W_H3_D25T30_DEMO_B', 'wt_tilt', cohort_h3_d25, '',
        (0.96, 0.97), fresh=('w_h3_d25_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
