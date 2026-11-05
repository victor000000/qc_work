"""R3055 — Fresh deep-band/down-regime W-DEMOTE exploration.

Pipeline state:
  - BAKE-152 confirmed: NOOP 3.33598 → 3.33629 (+0.00031 actual vs +0.00021 predicted!)
  - BAKE-153 still pending verification (R3052 NOOP will confirm)
  - W_P_H3_D25T30 = +0.00020 × 3 mags (sub-threshold, awaiting R3052 wider VRFY)
  - R3051 D20T22/D22T25 sub-bands within BAKE-152 = DESTRUCTIVE (correctly sized bake)
  - R3050 H5/VF parallel = bust

R3055 strategy: untested deep bands + down regime + Q3 deep parallel
Avoid HA-compound (Rule 43 strict) and BAKE-152/153 territory.

R3055 (16 specs):
 - Block A: W × P × Q3 × D008T012 (Q3 deep narrow — BAKE-151 is D17-20)
 - Block B: W × P × H3 × D040T050 (very deep H3, between BAKE-131 H5 and BAKE-152 D25)
 - Block C: W × P × D14 × D014T020 (HYGDN14 regime — UNTOUCHED)
 - Block D: W × P × H5 × D030T040 (H5 deep, just below BAKE-131 D040-D046)
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
    R = Round(rid=3055, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    HDN14 = 'self._reg_hyg_dn14'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × Q3 × D008T012 (Q3 deep narrow) (4 specs) ───
    cohort_a = f'_qpos and {QUP3} and decline > 0.008 and decline < 0.012'
    add('W_P_Q3_D08T12_DEMO_A', 'wt_tilt', cohort_a, '',
        (0.92, 0.94), fresh=('w_q3_d08_a',))
    add('W_P_Q3_D08T12_DEMO_B', 'wt_tilt', cohort_a, '',
        (0.96, 0.97), fresh=('w_q3_d08_b',))

    # ─── Block B: W × P × H3 × D040T050 (deep H3) (4 specs) ───
    cohort_b = f'_qpos and {HUP3} and decline > 0.040 and decline < 0.050'
    add('W_P_H3_D40T50_DEMO_A', 'wt_tilt', cohort_b, '',
        (0.92, 0.94), fresh=('w_h3_d40_a',))
    add('W_P_H3_D40T50_DEMO_B', 'wt_tilt', cohort_b, '',
        (0.96, 0.97), fresh=('w_h3_d40_b',))

    # ─── Block C: W × P × D14 × D014T020 (HYGDN14 untouched) (4 specs) ───
    cohort_c = f'_qpos and {HDN14} and decline > 0.014 and decline < 0.020'
    add('W_P_D14_D14T20_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_d14_d14_a',))
    add('W_P_D14_D14T20_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.96, 0.97), fresh=('w_d14_d14_b',))

    # ─── Block D: W × P × H5 × D030T040 (deep H5, below BAKE-131) (4 specs) ───
    cohort_d = f'_qpos and {HUP5} and decline > 0.030 and decline < 0.040'
    add('W_P_H5_D30T40_DEMO_A', 'wt_tilt', cohort_d, '',
        (0.92, 0.94), fresh=('w_h5_d30_a',))
    add('W_P_H5_D30T40_DEMO_B', 'wt_tilt', cohort_d, '',
        (0.96, 0.97), fresh=('w_h5_d30_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
