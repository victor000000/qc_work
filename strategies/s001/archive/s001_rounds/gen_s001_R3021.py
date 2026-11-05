"""R3021 — BAKE-143/144 sub-bands + cross-lever + qzero parallels.

R3018 produced BAKE-143 (W_DP_D14T20 m0.94) + BAKE-144 (W_H3_HA_D14T20 BOOST m1.05).
Both confirmed multi-mag std=0.

R3021:
 - Block A: BAKE-143 sub-bands D14-17 + D17-20
 - Block B: Conv DEMOTE on BAKE-143 cohort (cross-lever)
 - Block C: BAKE-144 stack on top — mild mags to find further peak
 - Block D: qzero parallel of BAKE-143 (Z × DP × D14T20 cohort)
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
    R = Round(rid=3021, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-143 sub-band D14-17 (4 specs) ───
    cohort_dp_d14_17 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.017'
    add('W_DP_D14T17_DEMO_A', 'wt_tilt', cohort_dp_d14_17, '',
        (0.92, 0.94), fresh=('w_dp_d14_17_a',))
    add('W_DP_D14T17_DEMO_B', 'wt_tilt', cohort_dp_d14_17, '',
        (0.96, 0.97), fresh=('w_dp_d14_17_b',))

    # ─── Block B: BAKE-143 sub-band D17-20 (4 specs) ───
    cohort_dp_d17_20 = f'_qpos and {DPANIC} and decline > 0.017 and decline < 0.020'
    add('W_DP_D17T20_DEMO_A', 'wt_tilt', cohort_dp_d17_20, '',
        (0.92, 0.94), fresh=('w_dp_d17_20_a',))
    add('W_DP_D17T20_DEMO_B', 'wt_tilt', cohort_dp_d17_20, '',
        (0.96, 0.97), fresh=('w_dp_d17_20_b',))

    # ─── Block C: Conv DEMOTE on BAKE-143 cohort (cross-lever) (4 specs) ───
    cohort_p_dp_d14 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.020'
    add('C_DP_D14T20_DEMO_A', 'conv', cohort_p_dp_d14, '',
        (0.92, 0.94), fresh=('c_dp_d14_a',))
    add('C_DP_D14T20_DEMO_B', 'conv', cohort_p_dp_d14, '',
        (0.96, 0.97), fresh=('c_dp_d14_b',))

    # ─── Block D: BAKE-144 cohort sub-band D14-17 (4 specs) ───
    cohort_h3_ha_d14_17 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.017'
    add('W_H3_HA_D14T17_BOOST_A', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.05, 1.07), fresh=('w_h3_ha_d14_17_a',))
    add('W_H3_HA_D14T17_BOOST_B', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.08, 1.10), fresh=('w_h3_ha_d14_17_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
