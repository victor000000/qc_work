"""R3027 — Pivot to UNTOUCHED DP decline bands D40+ + new cohort families.

R3026 partial showed multi-mag positive on H3×HA×D14-17 in post-revert
state. Pending NOOP_0 confirmation for BAKE-148 decision.

R3027 explores TRULY untouched directions to find new productive surfaces:
 - Block A: W × DP × .04<d<.05 (untouched decline band)
 - Block B: W × DP × .05<d<.06 (untouched)
 - Block C: C × DP × .04<d<.06 (cross-lever DP higher decline)
 - Block D: W × DPANIC × HA × .03<d<.04 (HA + DP wider, untested narrow)
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
    R = Round(rid=3027, priority=1)

    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × DP × .04<d<.05 (untouched decline band, no HA) (4 specs) ───
    cohort_dp_d40_50 = f'_qpos and {DPANIC} and decline > 0.040 and decline < 0.050'
    add('W_DP_D40T50_DEMO_A', 'wt_tilt', cohort_dp_d40_50, '',
        (0.86, 0.88), fresh=('w_dp_d40_50_a',))
    add('W_DP_D40T50_DEMO_B', 'wt_tilt', cohort_dp_d40_50, '',
        (0.92, 0.94), fresh=('w_dp_d40_50_b',))

    # ─── Block B: W × DP × .05<d<.06 (untouched) (4 specs) ───
    cohort_dp_d50_60 = f'_qpos and {DPANIC} and decline > 0.050 and decline < 0.060'
    add('W_DP_D50T60_DEMO_A', 'wt_tilt', cohort_dp_d50_60, '',
        (0.84, 0.87), fresh=('w_dp_d50_60_a',))
    add('W_DP_D50T60_DEMO_B', 'wt_tilt', cohort_dp_d50_60, '',
        (0.90, 0.92), fresh=('w_dp_d50_60_b',))

    # ─── Block C: C × DP × .04<d<.06 cross-lever wider decline (4 specs) ───
    cohort_c_dp_wide = f'_qpos and {DPANIC} and decline > 0.040 and decline < 0.060'
    add('C_DP_D40T60_DEMO_A', 'conv', cohort_c_dp_wide, '',
        (0.90, 0.92), fresh=('c_dp_d40_60_a',))
    add('C_DP_D40T60_DEMO_B', 'conv', cohort_c_dp_wide, '',
        (0.94, 0.96), fresh=('c_dp_d40_60_b',))

    # ─── Block D: W × DP × HA × .03<d<.04 (HA × DP wider sub-band) (4 specs) ───
    cohort_dp_ha_d30_40 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.030 and decline < 0.040'
    add('W_DP_HA_D30T40_DEMO_A', 'wt_tilt', cohort_dp_ha_d30_40, '',
        (0.92, 0.94), fresh=('w_dp_ha_d30_40_a',))
    add('W_DP_HA_D30T40_DEMO_B', 'wt_tilt', cohort_dp_ha_d30_40, '',
        (0.96, 0.97), fresh=('w_dp_ha_d30_40_b',))

    # ─── Block E: W × DP × .03<d<.04 NO-HA (sub-band of BAKE-139 territory but no HA gate) (4 specs) ───
    cohort_dp_d30_40 = f'_qpos and {DPANIC} and decline > 0.030 and decline < 0.040'
    add('W_DP_D30T40_DEMO_A', 'wt_tilt', cohort_dp_d30_40, '',
        (0.92, 0.94), fresh=('w_dp_d30_40_a',))
    add('W_DP_D30T40_DEMO_B', 'wt_tilt', cohort_dp_d30_40, '',
        (0.96, 0.97), fresh=('w_dp_d30_40_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
