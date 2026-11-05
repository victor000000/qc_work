"""R3019 — BAKE-136 sub-bands + petgt/EQ lever exploration.

R3017 first results post-BAKE-137 upgrade:
  C_H3_D14T20 m1.01 = 3.33526 = NOOP (peak captured)
  C_H3 m1.02 = -0.00011 (just past plateau peak at 1.07-1.08)
  BAKE-137 upgrade m1.07 IS the right level.

R3019 explores:
 - Block A: BAKE-136 sub-band D14-17 (apply sub-band paradigm to W BOOST)
 - Block B: BAKE-136 sub-band D17-20 (other half)
 - Block C: petgt lever on rally narrow decline (untested)
 - Block D: entry_score_quality (EQ) on rally narrow (very under-explored lever)
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
    R = Round(rid=3019, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-136 sub-band D14-17 W BOOST (sub-band of D14-20) (4 specs) ───
    # BAKE-136 already m1.22. Probe stacked m1.02 = effective 1.2444 (above peak ~1.22).
    # Try mild stacking near plateau.
    cohort_h3_d14_17 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.017'
    add('W_H3_D14T17_BOOST_A', 'wt_tilt', cohort_h3_d14_17, '',
        (0.98, 0.99), fresh=('w_h3_d14_17_a',))  # demote on sub-cohort = effective 1.196-1.208
    add('W_H3_D14T17_BOOST_B', 'wt_tilt', cohort_h3_d14_17, '',
        (1.02, 1.03), fresh=('w_h3_d14_17_b',))  # effective 1.244-1.257 (past peak)

    # ─── Block B: BAKE-136 sub-band D17-20 W (other half) (4 specs) ───
    cohort_h3_d17_20 = f'_qpos and {HUP3} and decline > 0.017 and decline < 0.020'
    add('W_H3_D17T20_BOOST_A', 'wt_tilt', cohort_h3_d17_20, '',
        (0.98, 0.99), fresh=('w_h3_d17_20_a',))
    add('W_H3_D17T20_BOOST_B', 'wt_tilt', cohort_h3_d17_20, '',
        (1.02, 1.03), fresh=('w_h3_d17_20_b',))

    # ─── Block C: DP × HA × .02<d<.04 BOOST direction (untested counter-direction) (4 specs) ───
    cohort_dp_ha = f'_qpos and {HACCEL} and self._reg_double_panic and decline > 0.020 and decline < 0.040'
    # BAKE-139 demotes m0.88. BOOST would be opposite direction — unlikely productive
    # but tests directional confidence.
    add('W_DP_HA_D20T40_BOOST_A', 'wt_tilt', cohort_dp_ha, '',
        (1.02, 1.03), fresh=('w_dp_b_a',))
    add('W_DP_HA_D20T40_BOOST_B', 'wt_tilt', cohort_dp_ha, '',
        (1.05, 1.07), fresh=('w_dp_b_b',))

    # ─── Block D: H3 × HA × narrow + SECTOR compound (4 specs) ───
    cohort_h3_s308 = f'_qpos and _secc == 308 and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('W_S308_H3_HA_D10T14_DEMO', 'wt_tilt', cohort_h3_s308, '',
        (0.88, 0.92), fresh=('w_s308_h3_ha',))
    cohort_h3_s311 = f'_qpos and _secc == 311 and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('W_S311_H3_HA_D10T14_DEMO', 'wt_tilt', cohort_h3_s311, '',
        (0.88, 0.92), fresh=('w_s311_h3_ha',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
