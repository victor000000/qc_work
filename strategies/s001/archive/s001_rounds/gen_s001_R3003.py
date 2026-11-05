"""R3003 — Pivot to untested directions after H3 plateau confirmed.

Evidence summary post-R3001:
 - H3 D14T20 W BOOST plateau: effective wt_tilt 1.20-1.24 = +0.00062 std=0 (DONE, baked m1.22)
 - H5 D14T20 W BOOST m1.12 = -0.00052 (NEG; H5 BOOST does not generalize from H3)
 - Q3 D14T20 W/C BOOST m1.05/1.07 = -0.00083 (NEG)
 - C_H5 m1.04-m1.08 = ~3.3334 (NEG-flat)

Decision: explore untested lever × cohort combinations.

Strategy:
 - Block A: SCORE lever on H3 D14T20 (untested 3rd lever on baked cohort)
 - Block B: H3 D20T25 BOOST (parallel decline band — untouched)
 - Block C: VF (vxx_falling3) D14T20 — untested regime
 - Block D: H3 D14T20 BOOST with NIM7 fund-gate (compound)
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
    R = Round(rid=3003, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    VF = 'self._reg_vxx_falling3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    cohort_h3_d14 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'

    # ─── Block A: SCORE BOOST + DEMOTE on H3 D14T20 (untested 3rd lever) (4) ───
    add('S_H3_D14T20_DEMOTE', 'score', cohort_h3_d14, '',
        (0.92, 0.95), fresh=('s_h3_d_demo',))
    add('S_H3_D14T20_BOOST', 'score', cohort_h3_d14, '',
        (1.05, 1.08), fresh=('s_h3_d_boost',))

    # ─── Block B: H3 D20T25 BOOST (parallel decline band, no prior bake) (4) ───
    cohort_h3_d20 = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.025'
    add('W_H3_D20T25_BOOST_LO', 'wt_tilt', cohort_h3_d20, '',
        (1.05, 1.08), fresh=('w_h3_d20_lo',))
    add('W_H3_D20T25_BOOST_HI', 'wt_tilt', cohort_h3_d20, '',
        (1.12, 1.15), fresh=('w_h3_d20_hi',))

    # ─── Block C: VF (vxx_falling3) D14T20 — untouched regime (4) ───
    cohort_vf = f'_qpos and {VF} and decline > 0.014 and decline < 0.020'
    add('W_VF_D14T20_BOOST', 'wt_tilt', cohort_vf, '',
        (1.05, 1.10), fresh=('w_vf_b',))
    add('C_VF_D14T20_BOOST', 'conv', cohort_vf, '',
        (1.05, 1.08), fresh=('c_vf_b',))

    # ─── Block D: H3 D14T20 fund-gated DEMOTE (NIM7) — orthogonal to BAKE-136 (4) ───
    add('W_H3_D14T20_NIM7_DEMOTE', 'wt_tilt',
        cohort_h3_d14 + ' and _NIM7', '',
        (0.92, 0.95), fresh=('w_h3_nim_d',))
    add('C_H3_D14T20_NIM7_DEMOTE', 'conv',
        cohort_h3_d14 + ' and _NIM7', '',
        (0.93, 0.96), fresh=('c_h3_nim_d',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
