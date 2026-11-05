"""R3005 — H3 D14T20 saturated. Pivot to DP/regime-pair compounds.

R3002 reveals BAKE-136 m1.22 = 3.33423 NOOP confirmed (+0.00062 from R3001).
ALL H3 D14T20 stacking attempts NEG: conv stack 1.08-1.16 = -0.00021, score
*= ANY direction = -0.01-0.02 CATASTROPHIC, NIM7 DEMOTE = NEG.

H3 D14T20 cohort is SATURATED. Pivot to:
 - Block A: P × DP × .03<d<.04 (gap between existing DP bakes) — UNTOUCHED
 - Block B: P × H3 × Q3 compound (both rally regimes simultaneous)
 - Block C: P × DP × HA (haccel compound on DP)
 - Block D: P × HUP3 × HA narrow-decline (haccel-conditional H3 sub-cohort)
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
    R = Round(rid=3005, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: P × DP × .03<d<.04 (gap between baked bands) (4) ───
    cohort_dp_d30 = f'_qpos and {DPANIC} and decline > 0.030 and decline < 0.040'
    add('W_DP_D30T40_DEMO', 'wt_tilt', cohort_dp_d30, '',
        (0.88, 0.92), fresh=('w_dp_d30_d',))
    add('C_DP_D30T40_DEMO', 'conv', cohort_dp_d30, '',
        (0.92, 0.95), fresh=('c_dp_d30_d',))

    # ─── Block B: P × H3 × Q3 compound regime-pair (4) ───
    cohort_h3q3_d14 = f'_qpos and {HUP3} and {QUP3} and decline > 0.014 and decline < 0.020'
    add('W_H3Q3_D14T20_DEMO', 'wt_tilt', cohort_h3q3_d14, '',
        (0.90, 0.93), fresh=('w_h3q3_d',))
    add('C_H3Q3_D14T20_DEMO', 'conv', cohort_h3q3_d14, '',
        (0.92, 0.95), fresh=('c_h3q3_d',))

    # ─── Block C: P × DP × HA haccel compound (4) ───
    cohort_dp_ha = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.040'
    add('W_DP_HA_D20T40_DEMO', 'wt_tilt', cohort_dp_ha, '',
        (0.88, 0.92), fresh=('w_dp_ha_d',))
    add('C_DP_HA_D20T40_DEMO', 'conv', cohort_dp_ha, '',
        (0.90, 0.93), fresh=('c_dp_ha_d',))

    # ─── Block D: P × HUP3 × HA narrow-decline (haccel-conditional H3) (4) ───
    cohort_h3_ha_narrow = (
        f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    )
    add('W_H3_HA_D10T14_DEMO', 'wt_tilt', cohort_h3_ha_narrow, '',
        (0.92, 0.95), fresh=('w_h3_ha_n',))
    add('C_H3_HA_D10T14_BOOST', 'conv', cohort_h3_ha_narrow, '',
        (1.05, 1.08), fresh=('c_h3_ha_n',))

    # ─── Block E: P × DP × INV8 wider-band (BAKE-135 extension) (4) ───
    cohort_dp_inv_wide = f'_qpos and {DPANIC} and decline > 0.030 and decline < 0.050 and _INV8'
    add('W_DP_D30T50_INV8_DEMO', 'wt_tilt', cohort_dp_inv_wide, '',
        (0.80, 0.85), fresh=('w_dp_inv_w',))
    add('C_DP_D30T50_INV8_DEMO', 'conv', cohort_dp_inv_wide, '',
        (0.88, 0.92), fresh=('c_dp_inv_w',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
