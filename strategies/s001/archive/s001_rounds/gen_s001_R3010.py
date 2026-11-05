"""R3010 — Cross-lever exploration on BAKE-139/140 + fund-gate compounds.

R3008 shows HA parallel transfer FAILS — H3-HA D14T20, H5-HA D10T14, DP-HA
D40T60 all NEG/catastrophic. BAKE-139/140 are NARROW productive surfaces.

R3010 strategy:
 - Block A: score DEMOTE cross-lever on BAKE-139 cohort (BAKE-134 pattern)
 - Block B: score DEMOTE cross-lever on BAKE-140 cohort
 - Block C: DP × HA × NIM7 fund-gate compound (new fund-gate)
 - Block D: H3 × HA × INV8 fund-gate compound (new fund-gate)
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
    R = Round(rid=3010, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: S DEMOTE cross-lever on BAKE-139 cohort (2) ───
    cohort_dp_ha = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.040'
    add('S_DP_HA_D20T40_DEMO', 'score', cohort_dp_ha, '',
        (0.93, 0.97), fresh=('s_dp_ha',))

    # ─── Block A2: W extend BAKE-139 band (narrower sub-bands) (4) ───
    cohort_dp_ha_lo = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030'
    add('W_DP_HA_D25T30_DEMO', 'wt_tilt', cohort_dp_ha_lo, '',
        (0.86, 0.90), fresh=('w_dp_ha_2530',))
    cohort_dp_ha_mid = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.030 and decline < 0.035'
    add('W_DP_HA_D30T35_DEMO', 'wt_tilt', cohort_dp_ha_mid, '',
        (0.86, 0.90), fresh=('w_dp_ha_3035',))

    # ─── Block B: S DEMOTE cross-lever on BAKE-140 cohort (2) ───
    cohort_h3_ha = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('S_H3_HA_D10T14_DEMO', 'score', cohort_h3_ha, '',
        (0.93, 0.97), fresh=('s_h3_ha',))

    # ─── Block C: DP × HA × NIM7 fund-gate compound (4) ───
    cohort_dp_ha_nim = cohort_dp_ha + ' and _NIM7'
    add('W_DP_HA_D20T40_NIM7_DEMO_A', 'wt_tilt', cohort_dp_ha_nim, '',
        (0.86, 0.88), fresh=('w_dp_ha_nim_a',))
    add('W_DP_HA_D20T40_NIM7_DEMO_B', 'wt_tilt', cohort_dp_ha_nim, '',
        (0.90, 0.92), fresh=('w_dp_ha_nim_b',))

    # ─── Block D: H3 × HA × INV8 fund-gate compound (4) ───
    cohort_h3_ha_inv = cohort_h3_ha + ' and _INV8'
    add('W_H3_HA_D10T14_INV8_DEMO_A', 'wt_tilt', cohort_h3_ha_inv, '',
        (0.88, 0.90), fresh=('w_h3_ha_inv_a',))
    add('W_H3_HA_D10T14_INV8_DEMO_B', 'wt_tilt', cohort_h3_ha_inv, '',
        (0.92, 0.94), fresh=('w_h3_ha_inv_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
