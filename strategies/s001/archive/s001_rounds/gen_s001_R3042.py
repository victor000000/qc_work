"""R3042 — Score lever exploration on cohorts WITHOUT heavy W bake.

Plateau at NOOP=3.33598 for 5+ rounds. Try score lever (rare in session).

R3042 (16 specs) explores SCORE *= cohorts where Rule 41 doesn't apply:
 - Block A: S × Q3 × .017<d<.020 (no heavy W bake on Q3 cohort)
 - Block B: S × Q3 × .014<d<.017 (parallel)
 - Block C: S × Z × HUP3 × .014<d<.020 (qzero on H3, different from W cohort)
 - Block D: S × DPANIC × .03<d<.04 (BAKE-134 territory expansion)
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
    R = Round(rid=3042, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: S × Q3 × .017<d<.020 (4 specs) ───
    cohort_q3_d17 = f'_qpos and {QUP3} and decline > 0.017 and decline < 0.020'
    add('S_Q3_D17T20_DEMO', 'score', cohort_q3_d17, '',
        (0.96, 0.97), fresh=('s_q3_d17_d',))
    add('S_Q3_D17T20_BOOST', 'score', cohort_q3_d17, '',
        (1.03, 1.05), fresh=('s_q3_d17_b',))

    # ─── Block B: S × Q3 × .014<d<.017 (4 specs) ───
    cohort_q3_d14 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.017'
    add('S_Q3_D14T17_DEMO', 'score', cohort_q3_d14, '',
        (0.96, 0.97), fresh=('s_q3_d14_d',))
    add('S_Q3_D14T17_BOOST', 'score', cohort_q3_d14, '',
        (1.03, 1.05), fresh=('s_q3_d14_b',))

    # ─── Block C: W × DPANIC × .03<d<.04 NO-HA NEW (4 specs) ───
    cohort_dp_d30 = f'_qpos and {DPANIC} and decline > 0.030 and decline < 0.040'
    add('W_DP_D30T40_DEMO_A', 'wt_tilt', cohort_dp_d30, '',
        (0.92, 0.94), fresh=('w_dp_d30_xa',))
    add('W_DP_D30T40_DEMO_B', 'wt_tilt', cohort_dp_d30, '',
        (0.96, 0.97), fresh=('w_dp_d30_xb',))

    # ─── Block D: W × HUP3 × .020<d<.025 (BAKE-136 D14-20 adjacent) (4 specs) ───
    cohort_h3_d20 = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.025'
    add('W_H3_D20T25_DEMO', 'wt_tilt', cohort_h3_d20, '',
        (0.92, 0.94), fresh=('w_h3_d20_xa',))
    add('W_H3_D20T25_BOOST', 'wt_tilt', cohort_h3_d20, '',
        (1.05, 1.07), fresh=('w_h3_d20_xb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
