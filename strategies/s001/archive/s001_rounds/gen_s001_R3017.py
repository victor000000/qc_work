"""R3017 — BAKE-137 post-upgrade VRFY + new cohort exploration.

BAKE-137 upgraded m1.05 → m1.07. R3017 NOOP_0 should reflect +0.00010 lift.
Expected R3017 NOOP ≈ 3.33525.

R3014 confirmed C_H3 plateau saturated; further m1.02 stacking flat.

R3017 explores NEW productive surfaces (sub-band paradigm slowing):
 - Block A: VRFY post-BAKE-137 upgrade — C_H3_D14T20 m1.01 (test below plateau)
 - Block B: BAKE-141 cohort × AOI3K fund-gate (operating margin-style fund)
 - Block C: Compound DP × HA × narrow + INV8 fund-gate
 - Block D: BAKE-142 cohort × INV8 fund-gate
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
    R = Round(rid=3017, priority=1)

    DPANIC = 'self._reg_double_panic'
    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: C_H3_D14T20 m1.01/m1.005 post-upgrade VRFY (4 specs) ───
    cohort_h3_d14 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'
    # BAKE-137 now m1.07. Probe stacked at m1.01 = effective 1.0807
    add('C_H3_D14T20_POST_M101', 'conv', cohort_h3_d14, '',
        (1.005, 1.01), fresh=('c_h3_post_m101',))
    add('C_H3_D14T20_POST_M102', 'conv', cohort_h3_d14, '',
        (1.015, 1.02), fresh=('c_h3_post_m102',))

    # ─── Block B: BAKE-141 cohort × AOI3K fund-gate (mild mags to avoid Rule 37) (4 specs) ───
    cohort_dp_aoi = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030 and _AOI3K'
    add('W_DP_HA_D25T30_AOI3K_A', 'wt_tilt', cohort_dp_aoi, '',
        (0.94, 0.96), fresh=('w_dp_aoi_a',))
    add('W_DP_HA_D25T30_AOI3K_B', 'wt_tilt', cohort_dp_aoi, '',
        (0.97, 0.98), fresh=('w_dp_aoi_b',))

    # ─── Block C: BAKE-141 cohort × INV8 fund-gate (mild mags) (4 specs) ───
    cohort_dp_inv = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030 and _INV8'
    add('W_DP_HA_D25T30_INV8_A', 'wt_tilt', cohort_dp_inv, '',
        (0.94, 0.96), fresh=('w_dp_inv_a',))
    add('W_DP_HA_D25T30_INV8_B', 'wt_tilt', cohort_dp_inv, '',
        (0.97, 0.98), fresh=('w_dp_inv_b',))

    # ─── Block D: BAKE-142 cohort × FCF7 fund-gate (4 specs) ───
    cohort_h3_fcf = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.012 and _FCF7'
    add('W_H3_HA_D10T12_FCF7_A', 'wt_tilt', cohort_h3_fcf, '',
        (0.92, 0.94), fresh=('w_h3_fcf_a',))
    add('W_H3_HA_D10T12_FCF7_B', 'wt_tilt', cohort_h3_fcf, '',
        (0.96, 0.97), fresh=('w_h3_fcf_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
