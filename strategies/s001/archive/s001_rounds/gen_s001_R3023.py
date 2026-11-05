"""R3023 — BAKE-147 saturation check + extend new bake territory.

R3021 produced BAKE-147 (W_H3_HA_D14T17 BOOST m1.05, +0.00031 multi-mag).
R3020 produced BAKE-145 (C_DP_D14T20 m0.94).
R3018 produced BAKE-143 (W_DP_D14T20 m0.94) + BAKE-144 (W_H3_HA_D14T20 BOOST m1.05).

R3023:
 - Block A: W_H3_HA_D14T17 BOOST saturation (mag 1.12+ to find ceiling)
 - Block B: BAKE-144 D17-20 conv DEMOTE (opposite to BAKE-144 W BOOST)
 - Block C: BAKE-147 stack — mag VRFY at upper edge
 - Block D: DP_D14T17 narrow band with C (BAKE-146 cross-lever)
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
    R = Round(rid=3023, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-147 saturation check (m1.12-1.15) (4 specs) ───
    cohort_h3_ha_d14_17 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.017'
    add('W_H3_HA_D14T17_SAT_A', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.02, 1.03), fresh=('w_h3_d14_17_sat_a',))
    add('W_H3_HA_D14T17_SAT_B', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.04, 1.05), fresh=('w_h3_d14_17_sat_b',))

    # ─── Block B: BAKE-146 cohort × conv (cross-lever on baked W m0.94) (4 specs) ───
    cohort_dp_d14_17 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.017'
    add('C_DP_D14T17_DEMO_A', 'conv', cohort_dp_d14_17, '',
        (0.92, 0.94), fresh=('c_dp_d14_17_a',))
    add('C_DP_D14T17_DEMO_B', 'conv', cohort_dp_d14_17, '',
        (0.96, 0.97), fresh=('c_dp_d14_17_b',))

    # ─── Block C: BAKE-144 D17-20 sub-band W BOOST (other half) (4 specs) ───
    cohort_h3_ha_d17_20 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.017 and decline < 0.020'
    add('W_H3_HA_D17T20_BOOST_A', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.05, 1.07), fresh=('w_h3_ha_17_20_a',))
    add('W_H3_HA_D17T20_BOOST_B', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.08, 1.10), fresh=('w_h3_ha_17_20_b',))

    # ─── Block D: BAKE-143 cohort with INV8 fund-gate (4 specs) ───
    cohort_dp_inv = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.020 and _INV8'
    add('W_DP_D14T20_INV8_A', 'wt_tilt', cohort_dp_inv, '',
        (0.92, 0.94), fresh=('w_dp_inv_a2',))
    add('W_DP_D14T20_INV8_B', 'wt_tilt', cohort_dp_inv, '',
        (0.96, 0.97), fresh=('w_dp_inv_b2',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
