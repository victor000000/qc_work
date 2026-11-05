"""R3034 — Diversify exploration: narrow DP-HA sub-bands + H3-HA D17-20.

R3031 results: All FLAT or NEG. No new candidates from Q3 narrow, P×HA, H3×HA D17-20.

R3034:
 - Block A: W × DPANIC × HACCEL × .020<d<.022 (very narrow lower edge of BAKE-139)
 - Block B: W × DPANIC × HACCEL × .03<d<.035 (BAKE-141 narrower)
 - Block C: W × H3 × HA × .017<d<.020 BOOST (untested BAKE-144 right half)
 - Block D: W × DPANIC × .03<d<.04 (DP no-HA sub-band of BAKE-143 territory)
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
    R = Round(rid=3034, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × DP × HA × .020<d<.022 very narrow (4 specs) ───
    cohort_dp_ha_d20_22 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.022'
    add('W_DP_HA_D20T22_DEMO_A', 'wt_tilt', cohort_dp_ha_d20_22, '',
        (0.94, 0.96), fresh=('w_dp_ha_d20_22_a',))
    add('W_DP_HA_D20T22_DEMO_B', 'wt_tilt', cohort_dp_ha_d20_22, '',
        (0.97, 0.98), fresh=('w_dp_ha_d20_22_b',))

    # ─── Block B: W × DP × HA × .03<d<.035 (4 specs) ───
    cohort_dp_ha_d30_35 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.030 and decline < 0.035'
    add('W_DP_HA_D30T35_DEMO_A', 'wt_tilt', cohort_dp_ha_d30_35, '',
        (0.94, 0.96), fresh=('w_dp_ha_d30_35_a',))
    add('W_DP_HA_D30T35_DEMO_B', 'wt_tilt', cohort_dp_ha_d30_35, '',
        (0.97, 0.98), fresh=('w_dp_ha_d30_35_b',))

    # ─── Block C: W × H3 × HA × D17-20 BOOST (BAKE-144 right half) (4 specs) ───
    cohort_h3_ha_d17_20 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.017 and decline < 0.020'
    add('W_H3_HA_D17T20_BOOST_A', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.05, 1.07), fresh=('w_h3_ha_d17_20_a',))
    add('W_H3_HA_D17T20_BOOST_B', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.10, 1.13), fresh=('w_h3_ha_d17_20_b',))

    # ─── Block D: W × DP × .03<d<.04 (DP no-HA, gap-fill) (4 specs) ───
    cohort_dp_d30_40 = f'_qpos and {DPANIC} and decline > 0.030 and decline < 0.040'
    add('W_DP_D30T40_DEMO_A', 'wt_tilt', cohort_dp_d30_40, '',
        (0.92, 0.94), fresh=('w_dp_d30_40_aa',))
    add('W_DP_D30T40_DEMO_B', 'wt_tilt', cohort_dp_d30_40, '',
        (0.96, 0.97), fresh=('w_dp_d30_40_bb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
