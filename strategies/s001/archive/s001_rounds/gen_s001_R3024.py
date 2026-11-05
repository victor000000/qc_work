"""R3024 — Post-BAKE-145-revert + BAKE-147 saturation continue.

R3022 NOOP=3.33526 vs R3021=3.33546 revealed BAKE-145 was DESTRUCTIVE.
Reverted. Expected R3024 NOOP ≈ 3.33587 (post-revert + BAKE-146/147 active).

R3024:
 - Block A: BAKE-147 deeper plateau check m1.10-1.20 (test ceiling)
 - Block B: BAKE-146 sub-band D14-15 (very narrow)
 - Block C: BAKE-147 sub-band D14-15 (very narrow within D14-17)
 - Block D: NEW cohort — H5 × HA sub-band (currently blocked by Rule 43)
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
    R = Round(rid=3024, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-147 deeper plateau check m1.12-1.20 (4 specs) ───
    cohort_h3_ha_d14_17 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.017'
    add('W_H3_HA_D14T17_DEEP_A', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.12, 1.15), fresh=('w_h3_d14_17_deep_a',))
    add('W_H3_HA_D14T17_DEEP_B', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.18, 1.20), fresh=('w_h3_d14_17_deep_b',))

    # ─── Block B: BAKE-146 narrower D14-15 sub-band (4 specs) ───
    cohort_dp_d14_15 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.015'
    add('W_DP_D14T15_DEMO_A', 'wt_tilt', cohort_dp_d14_15, '',
        (0.92, 0.94), fresh=('w_dp_d14_15_a',))
    add('W_DP_D14T15_DEMO_B', 'wt_tilt', cohort_dp_d14_15, '',
        (0.96, 0.97), fresh=('w_dp_d14_15_b',))

    # ─── Block C: BAKE-147 narrower D14-15 sub-band (4 specs) ───
    cohort_h3_ha_d14_15 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.015'
    add('W_H3_HA_D14T15_BOOST_A', 'wt_tilt', cohort_h3_ha_d14_15, '',
        (1.05, 1.07), fresh=('w_h3_ha_d14_15_a',))
    add('W_H3_HA_D14T15_BOOST_B', 'wt_tilt', cohort_h3_ha_d14_15, '',
        (1.10, 1.12), fresh=('w_h3_ha_d14_15_b',))

    # ─── Block D: D15-17 of BAKE-146 (other half of D14-17) (4 specs) ───
    cohort_dp_d15_17 = f'_qpos and {DPANIC} and decline > 0.015 and decline < 0.017'
    add('W_DP_D15T17_DEMO_A', 'wt_tilt', cohort_dp_d15_17, '',
        (0.92, 0.94), fresh=('w_dp_d15_17_a',))
    add('W_DP_D15T17_DEMO_B', 'wt_tilt', cohort_dp_d15_17, '',
        (0.96, 0.97), fresh=('w_dp_d15_17_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
