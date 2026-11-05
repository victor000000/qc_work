"""R3004 — Explore untested decline-bands + cross-lever on H3 productive cohort.

Plateau confirmed: H3 D14T20 W BOOST 1.20-1.24 baked at 1.22.
H5/Q3 D14T20 BOOST = NEG (Rule 39 added).
VF D14T20 BOOST = NEG (Rule 38 added).

R3004 strategy:
 - Block A: NARROWER decline bands on H3 (D11T14, D14T17) — untouched
 - Block B: Score DEMOTE cross-lever on H3 D14T20 (BAKE-134 pattern)
 - Block C: HA compound on H3 D14T20 (haccel-conditional)
 - Block D: BAKE-137 conv stacked exploration (analogous to BAKE-136 upgrade)
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
    R = Round(rid=3004, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: H3 D11T14 (narrower band, untouched) (4) ───
    cohort_h3_d11 = f'_qpos and {HUP3} and decline > 0.011 and decline < 0.014'
    add('W_H3_D11T14_BOOST', 'wt_tilt', cohort_h3_d11, '',
        (1.07, 1.10), fresh=('w_h3_d11_b',))
    add('C_H3_D11T14_BOOST', 'conv', cohort_h3_d11, '',
        (1.05, 1.08), fresh=('c_h3_d11_b',))

    # ─── Block B: Score DEMOTE on H3 D14T20 (BAKE-134 cross-lever pattern) (4) ───
    cohort_h3_d14 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'
    add('S_H3_D14T20_DEMO_LO', 'score', cohort_h3_d14, '',
        (0.95, 0.97), fresh=('s_h3_d_lo',))
    add('S_H3_D14T20_DEMO_HI', 'score', cohort_h3_d14, '',
        (0.92, 0.94), fresh=('s_h3_d_hi',))

    # ─── Block C: HA compound on H3 D14T20 (untouched gate) (4) ───
    cohort_h3_d14_ha = cohort_h3_d14 + f' and {HACCEL}'
    add('W_H3_D14T20_HA_DEMO', 'wt_tilt', cohort_h3_d14_ha, '',
        (0.92, 0.95), fresh=('w_h3_ha_d',))
    add('C_H3_D14T20_HA_BOOST', 'conv', cohort_h3_d14_ha, '',
        (1.05, 1.08), fresh=('c_h3_ha_b',))

    # ─── Block D: H3 D14T20 score-additive (entry_score family alt) (4) ───
    add('EM_H3_D14T20_DEMO', 'entry_score_mtf', cohort_h3_d14, '',
        (-0.05, -0.10), op='+=', fresh=('em_h3_d',))
    add('ER_H3_D14T20_DEMO', 'entry_score_regime', cohort_h3_d14, '',
        (-0.05, -0.10), op='+=', fresh=('er_h3_d',))

    # ─── Block E: H3 D14T17 (even narrower band, untouched) (4) ───
    cohort_h3_d14n = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.017'
    add('W_H3_D14T17_BOOST', 'wt_tilt', cohort_h3_d14n, '',
        (1.05, 1.08), fresh=('w_h3_d14n_b',))
    add('C_H3_D14T17_BOOST', 'conv', cohort_h3_d14n, '',
        (1.05, 1.08), fresh=('c_h3_d14n_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
