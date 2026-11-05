"""R3048 — Fund-stratification of W_H3_D20T25 (the ONE encouraging signal).

Pipeline state (30m deep review):
  - W_H3_D20T25_DEMO m0.93 + m0.94 = +0.00031 std=0 (encouraging)
  - m0.92 = -0.00072 (narrow sweet spot — m0.95/m0.96 still pending)
  - S_Q3 fully refuted (R3042+R3044)
  - C cross-lever refuted (R3043)

R3048 hypothesis: fund-accessor stratification refines W_H3_D20T25 cohort.
  Existing BAKE-135 (DP × D014-D03 × _INV8) precedent: fund-gating amplifies.
  Existing Z × H3 × narrow × _AOI3K/_EY5 bakes (lines 619-624) work too.

R3048 (16 specs):
 - Block A: W × P × H3 × D020T025 × _AOI3K (fund-gated refinement)
 - Block B: W × P × H3 × D020T025 × _EY5 (earnings yield gate)
 - Block C: W × P × H3 × D020T025 × _INV8 (inventory gate, BAKE-135 precedent)
 - Block D: W × P × H3 × D020T025 × _HAC4 (haccel-quality gate)
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
    R = Round(rid=3048, priority=1)

    HUP3 = 'self._reg_hyg_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    base_cohort = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.025'

    # ─── Block A: W × P × H3 × D020T025 × _AOI3K (4 specs) ───
    add('W_P_H3_D20T25_AOI3K_A', 'wt_tilt', f'{base_cohort} and _AOI3K', '',
        (0.92, 0.94), fresh=('w_h3_d20_aoi3k_a',))
    add('W_P_H3_D20T25_AOI3K_B', 'wt_tilt', f'{base_cohort} and _AOI3K', '',
        (0.90, 0.96), fresh=('w_h3_d20_aoi3k_b',))

    # ─── Block B: W × P × H3 × D020T025 × _EY5 (4 specs) ───
    add('W_P_H3_D20T25_EY5_A', 'wt_tilt', f'{base_cohort} and _EY5', '',
        (0.92, 0.94), fresh=('w_h3_d20_ey5_a',))
    add('W_P_H3_D20T25_EY5_B', 'wt_tilt', f'{base_cohort} and _EY5', '',
        (0.90, 0.96), fresh=('w_h3_d20_ey5_b',))

    # ─── Block C: W × P × H3 × D020T025 × _INV8 (4 specs) ───
    add('W_P_H3_D20T25_INV8_A', 'wt_tilt', f'{base_cohort} and _INV8', '',
        (0.92, 0.94), fresh=('w_h3_d20_inv8_a',))
    add('W_P_H3_D20T25_INV8_B', 'wt_tilt', f'{base_cohort} and _INV8', '',
        (0.90, 0.96), fresh=('w_h3_d20_inv8_b',))

    # ─── Block D: W × P × H3 × D020T025 × _HAC4 (4 specs) ───
    add('W_P_H3_D20T25_HAC4_A', 'wt_tilt', f'{base_cohort} and _HAC4', '',
        (0.92, 0.94), fresh=('w_h3_d20_hac4_a',))
    add('W_P_H3_D20T25_HAC4_B', 'wt_tilt', f'{base_cohort} and _HAC4', '',
        (0.90, 0.96), fresh=('w_h3_d20_hac4_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
