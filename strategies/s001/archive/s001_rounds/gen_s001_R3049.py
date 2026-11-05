"""R3049 — Post-BAKE-152 verification + adjacent sub-band exploration.

BAKE-152 just applied: if P and H3 and .02<d<.025:W*=.94
  Predicted lift +0.00021 (4-mag positive plateau m0.93-m0.96)
  Expected R3049 NOOP_0 ≈ 3.33619

R3049 strategy: VERIFY BAKE-152 lift + explore ADJACENT decline sub-bands
to find sibling cohorts (sub-band paradigm: BAKE-141, 142 precedent).

R3049 (16 specs):
 - Block A: W × P × H3 × D025T030 sub-bands (just above BAKE-152)
 - Block B: W × P × H3 × D018T020 sub-band (just below BAKE-152 / above BAKE-136)
 - Block C: W × P × Q3 × D020T025 (parallel of BAKE-152 on Q3)
 - Block D: W × P × DP (no HA) × D020T025 (parallel of BAKE-152 on DP-no-HA)
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
    R = Round(rid=3049, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × H3 × D025T030 sub-bands (4 specs) ───
    cohort_a = f'_qpos and {HUP3} and decline > 0.025 and decline < 0.030'
    add('W_P_H3_D25T30_NARROW_A', 'wt_tilt', cohort_a, '',
        (0.92, 0.94), fresh=('w_h3_d25_a',))
    add('W_P_H3_D25T30_NARROW_B', 'wt_tilt', cohort_a, '',
        (0.96, 0.97), fresh=('w_h3_d25_b',))

    # ─── Block B: W × P × H3 × D018T020 (gap before BAKE-152, after BAKE-136) (4 specs) ───
    cohort_b = f'_qpos and {HUP3} and decline > 0.018 and decline < 0.020'
    add('W_P_H3_D18T20_DEMO_A', 'wt_tilt', cohort_b, '',
        (0.92, 0.94), fresh=('w_h3_d18_a',))
    add('W_P_H3_D18T20_DEMO_B', 'wt_tilt', cohort_b, '',
        (0.96, 0.97), fresh=('w_h3_d18_b',))

    # ─── Block C: W × P × Q3 × D020T025 (Q3 parallel of BAKE-152) (4 specs) ───
    cohort_c = f'_qpos and {QUP3} and decline > 0.020 and decline < 0.025'
    add('W_P_Q3_D20T25_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_q3_d20_a',))
    add('W_P_Q3_D20T25_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.96, 0.97), fresh=('w_q3_d20_b',))

    # ─── Block D: W × P × DP-no-HA × D020T025 (parallel of BAKE-152 on DP) (4 specs) ───
    cohort_d = (f'_qpos and {DPANIC} and not (HA and HA>0)'
                f' and decline > 0.020 and decline < 0.025')
    add('W_P_DP_NOHA_D20T25_A', 'wt_tilt', cohort_d, '',
        (0.92, 0.94), fresh=('w_dp_d20_a',))
    add('W_P_DP_NOHA_D20T25_B', 'wt_tilt', cohort_d, '',
        (0.96, 0.97), fresh=('w_dp_d20_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
