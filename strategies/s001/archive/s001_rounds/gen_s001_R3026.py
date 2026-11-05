"""R3026 — Post-BAKE-146/147 revert verification + careful new candidates.

R3025 (with BAKE-146/147 still active) showed:
  W_H3_HA_D14T17_PEAK m1.14/m1.15/m1.17 = 3.33577 (TRIPLE-MAG +0.00051)
  W_DP_D17T20 m0.96 = 3.33557 (single +0.00031)

But these were in BAKE-146/147 stacked state. R3026 tests in clean state.

R3026 (post-revert, BAKE-143/144 only):
 - Block A: W × H3 × HA × D14-17 raw VRFY m1.10/1.12 (direct mag, no over-stack)
 - Block B: W × DP × D14-17 m0.94 (BAKE-146 retry in clean state)
 - Block C: W × DP × D17-20 m0.96 (single-mag candidate VRFY)
 - Block D: NEW cohort — W × P × DP × HA × D14-15 (compound, untested)
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
    R = Round(rid=3026, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × H3 × HA × D14-17 direct VRFY post-revert (4 specs) ───
    cohort_h3_ha_d14_17 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.017'
    add('W_H3_HA_D14T17_RAW_A', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.10, 1.12), fresh=('w_h3_d14_17_raw_a',))
    add('W_H3_HA_D14T17_RAW_B', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.15, 1.18), fresh=('w_h3_d14_17_raw_b',))

    # ─── Block B: W × DP × D14-17 m0.94 (BAKE-146 retry in clean state) (4 specs) ───
    cohort_dp_d14_17 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.017'
    add('W_DP_D14T17_RAW_A', 'wt_tilt', cohort_dp_d14_17, '',
        (0.92, 0.94), fresh=('w_dp_d14_17_raw_a',))
    add('W_DP_D14T17_RAW_B', 'wt_tilt', cohort_dp_d14_17, '',
        (0.96, 0.97), fresh=('w_dp_d14_17_raw_b',))

    # ─── Block C: W × DP × D17-20 single-mag candidate VRFY (4 specs) ───
    cohort_dp_d17_20 = f'_qpos and {DPANIC} and decline > 0.017 and decline < 0.020'
    add('W_DP_D17T20_RAW_A', 'wt_tilt', cohort_dp_d17_20, '',
        (0.92, 0.94), fresh=('w_dp_d17_20_raw_a',))
    add('W_DP_D17T20_RAW_B', 'wt_tilt', cohort_dp_d17_20, '',
        (0.96, 0.97), fresh=('w_dp_d17_20_raw_b',))

    # ─── Block D: W × DP × HA × D14-15 narrow compound (4 specs) ───
    cohort_dp_ha_d14_15 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.014 and decline < 0.015'
    add('W_DP_HA_D14T15_A', 'wt_tilt', cohort_dp_ha_d14_15, '',
        (0.92, 0.94), fresh=('w_dp_ha_d14_15_a',))
    add('W_DP_HA_D14T15_B', 'wt_tilt', cohort_dp_ha_d14_15, '',
        (0.96, 0.97), fresh=('w_dp_ha_d14_15_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
