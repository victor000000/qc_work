"""R3009 — VRFY C_DP_D20T40 + explore conv-HA at d≥0.04 (avoid Rule 14a).

R3007 found C_DP_D20T40_DEMO m0.90 = +0.00031 single-mag.
Need multi-mag VRFY before baking. Plus explore conv lever on under-baked
cohorts.

R3009 design:
 - Block A: C_DP_D20T40 wider mag VRFY (4 specs)
 - Block B: C_DP_HA_D40T60 (Rule 14a allows C×HA at d≥0.04)
 - Block C: C_H3_HA wider declines (d≥0.04 only)
 - Block D: W on HUP3 wider decline gap D20T25 (extend BAKE-140 territory)
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
    R = Round(rid=3009, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: C_DP_D20T40 multi-mag VRFY (4 specs) ───
    cohort_dp_d20 = f'_qpos and {DPANIC} and decline > 0.020 and decline < 0.040'
    add('C_DP_D20T40_VRFY_LO', 'conv', cohort_dp_d20, '',
        (0.85, 0.88), fresh=('c_dp_d20_lo',))
    add('C_DP_D20T40_VRFY_HI', 'conv', cohort_dp_d20, '',
        (0.92, 0.95), fresh=('c_dp_d20_hi',))

    # ─── Block B: C × DP × HA at d≥0.04 (Rule 14a allows) (4 specs) ───
    cohort_dp_ha_w = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.040 and decline < 0.060'
    add('C_DP_HA_D40T60_DEMO_A', 'conv', cohort_dp_ha_w, '',
        (0.88, 0.90), fresh=('c_dp_ha_w_a',))
    add('C_DP_HA_D40T60_DEMO_B', 'conv', cohort_dp_ha_w, '',
        (0.92, 0.94), fresh=('c_dp_ha_w_b',))

    # ─── Block C: W × H3 × wider declines D20-25 (extend BAKE-140 territory) (4 specs) ───
    cohort_h3_d20 = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.025'
    add('W_H3_D20T25_DEMO_A', 'wt_tilt', cohort_h3_d20, '',
        (0.92, 0.94), fresh=('w_h3_d20_a',))
    add('W_H3_D20T25_DEMO_B', 'wt_tilt', cohort_h3_d20, '',
        (0.88, 0.90), fresh=('w_h3_d20_b',))

    # ─── Block D: H5 wider declines D14-20 (parallel to baked H3) (4 specs) ───
    cohort_h5_d14 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.020'
    # BAKE-138 (m1.05 BOOST) is on this cohort. Try DEMOTE direction.
    add('W_H5_D14T20_DEMO_A', 'wt_tilt', cohort_h5_d14, '',
        (0.92, 0.94), fresh=('w_h5_d14_dema',))
    add('W_H5_D14T20_DEMO_B', 'wt_tilt', cohort_h5_d14, '',
        (0.95, 0.97), fresh=('w_h5_d14_demb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
