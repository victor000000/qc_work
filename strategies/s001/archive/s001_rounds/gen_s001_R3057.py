"""R3057 — D25T30 orthogonal cross-validation + adjacent untouched bands.

Pipeline state (30m deep review):
  - BAKE-152 confirmed +0.00031 (NOOP 3.33629)
  - BAKE-153 LIFT UNVERIFIED: R3052 D15T18 m0.92 = 3.33629 (same as R3050 NOOP)
    suggests BAKE-153 may have ~0 lift (probe-vs-bake divergence concern)
  - D25T30 m0.88 = +0.00041 single-mag (ambiguous: +0.00021 if post-BAKE-153)
  - Rule 45 added: blocks W*= sub-range compounding-DEMOTE waste

R3057 strategy: ORTHOGONAL D25T30 validation + new untouched
  - Different cohort (Q3, D14) parallel of D25T30 hypothesis
  - Adjacent decline band (D030-D035) to test continuation

R3057 (16 specs):
 - Block A: W × P × H3 × D030T035 (just above D25T30, untouched)
 - Block B: W × P × D14 × D025T030 (parallel D25T30 on HYGDN14)
 - Block C: W × P × DP × D025T030 (parallel D25T30 on DP no-HA)
 - Block D: W × P × H3 × D025T030 × _AOI3K fund-gate (refinement)
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
    R = Round(rid=3057, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HDN14 = 'self._reg_hyg_dn14'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × H3 × D030T035 (just above D25T30 untouched) (4 specs) ───
    cohort_a = f'_qpos and {HUP3} and decline > 0.030 and decline < 0.035'
    add('W_P_H3_D30T35_DEMO_A', 'wt_tilt', cohort_a, '',
        (0.88, 0.90), fresh=('w_h3_d30t35_a',))
    add('W_P_H3_D30T35_DEMO_B', 'wt_tilt', cohort_a, '',
        (0.92, 0.94), fresh=('w_h3_d30t35_b',))

    # ─── Block B: W × P × D14 × D025T030 (HYGDN14 parallel D25T30) (4 specs) ───
    cohort_b = f'_qpos and {HDN14} and decline > 0.025 and decline < 0.030'
    add('W_P_D14_D25T30_DEMO_A', 'wt_tilt', cohort_b, '',
        (0.88, 0.90), fresh=('w_d14_d25_a',))
    add('W_P_D14_D25T30_DEMO_B', 'wt_tilt', cohort_b, '',
        (0.92, 0.94), fresh=('w_d14_d25_b',))

    # ─── Block C: W × P × DP × D025T030 (DP no-HA parallel D25T30) (4 specs) ───
    cohort_c = (f'_qpos and {DPANIC} and not (HA and HA>0)'
                f' and decline > 0.025 and decline < 0.030')
    add('W_P_DP_NOHA_D25T30_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.88, 0.90), fresh=('w_dp_d25_pa',))
    add('W_P_DP_NOHA_D25T30_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_dp_d25_pb',))

    # ─── Block D: W × P × H3 × D025T030 × _AOI3K (fund-stratification) (4 specs) ───
    cohort_d = f'_qpos and {HUP3} and decline > 0.025 and decline < 0.030 and _AOI3K'
    add('W_P_H3_D25T30_AOI_A', 'wt_tilt', cohort_d, '',
        (0.86, 0.88), fresh=('w_h3_d25_ag_a',))
    add('W_P_H3_D25T30_AOI_B', 'wt_tilt', cohort_d, '',
        (0.90, 0.92), fresh=('w_h3_d25_ag_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
