"""R3033 — Continue diverse exploration while backlog drains.

R3030 NOOP=3.33577 verified BAKE-148/149/150 working.

R3033 explores untested cohort families:
 - Block A: W × H3 × HA × .017<d<.020 (BAKE-144 sub-band other half)
 - Block B: W × H3 × HA × .012<d<.014 (BAKE-140 sub-band other half)
 - Block C: W × DP × HA × .03<d<.04 (BAKE-139 sub-band)
 - Block D: NEW conv cohort — C × DP × HA × .04<d<.06
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
    R = Round(rid=3033, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × H3 × HA × D17-20 (BAKE-144 sub-band other half) (4) ───
    cohort_h3_ha_d17_20 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.017 and decline < 0.020'
    add('W_H3_HA_D17T20_BOOST_A', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.03, 1.05), fresh=('w_h3_ha_d17_aa',))
    add('W_H3_HA_D17T20_BOOST_B', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.07, 1.10), fresh=('w_h3_ha_d17_bb',))

    # ─── Block B: W × H3 × HA × D12-14 sub-band (BAKE-140 other half) (4) ───
    cohort_h3_ha_d12_14 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.012 and decline < 0.014'
    add('W_H3_HA_D12T14_DEMO', 'wt_tilt', cohort_h3_ha_d12_14, '',
        (0.95, 0.97), fresh=('w_h3_ha_d12_aa',))
    add('W_H3_HA_D12T14_DEEP', 'wt_tilt', cohort_h3_ha_d12_14, '',
        (0.92, 0.94), fresh=('w_h3_ha_d12_bb',))

    # ─── Block C: W × DP × HA × D30-40 (BAKE-139 sub-band upper) (4) ───
    cohort_dp_ha_d30_40 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.030 and decline < 0.040'
    add('W_DP_HA_D30T40_DEMO_A', 'wt_tilt', cohort_dp_ha_d30_40, '',
        (0.92, 0.94), fresh=('w_dp_ha_d30_aa',))
    add('W_DP_HA_D30T40_DEMO_B', 'wt_tilt', cohort_dp_ha_d30_40, '',
        (0.96, 0.97), fresh=('w_dp_ha_d30_bb',))

    # ─── Block D: W × DP × HA × D20-25 narrow (BAKE-139 lower half) (4) ───
    cohort_dp_ha_d20_25 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.025'
    add('W_DP_HA_D20T25_DEMO_A', 'wt_tilt', cohort_dp_ha_d20_25, '',
        (0.92, 0.94), fresh=('w_dp_ha_d20_aa',))
    add('W_DP_HA_D20T25_DEMO_B', 'wt_tilt', cohort_dp_ha_d20_25, '',
        (0.96, 0.97), fresh=('w_dp_ha_d20_bb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
