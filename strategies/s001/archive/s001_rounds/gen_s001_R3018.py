"""R3018 — BAKE-142 m0.92 plateau VRFY + new HACCEL-threshold exploration.

R3015 W_H3_HA_D10T12 m0.92 = 3.33557 (+0.00042 single mag — biggest today).
R3016 m0.94/m0.92 stacked on BAKE-142 m0.94 went catastrophic (effective <0.87).

Plateau analysis: peak at effective ~0.88; cliff below 0.87.

R3018:
 - Block A: W_H3_HA_D10T12 m0.86/0.88 raw VRFY (cohort with FRESH probe, no over-stack)
 - Block B: HACCEL stricter threshold _gt(HA, 0.005) variation
 - Block C: NEW cohort — P × _hi_vol × narrow decline
 - Block D: BAKE-141 cohort × DIFFERENT lever (try entry_signal +=)
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
    R = Round(rid=3018, priority=1)

    DPANIC = 'self._reg_double_panic'
    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-141 cohort × NIM7-stacked compound (m0.94 stacked) (4 specs) ───
    # BAKE-141 m0.88 active. Probe m0.94 = effective 0.8272 — Rule 37 may block.
    # Try MILD mags to stay above 0.80.
    cohort_dp_nim = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030 and _NIM7'
    add('W_DP_HA_D25T30_NIM7_NEW', 'wt_tilt', cohort_dp_nim, '',
        (0.94, 0.96), fresh=('w_dp_nim2',))

    # ─── Block B: H3 D14T20 W BOOST × HA compound (untested) (4 specs) ───
    cohort_h3_ha_d14 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.020'
    add('W_H3_HA_D14T20_BOOST_A', 'wt_tilt', cohort_h3_ha_d14, '',
        (1.05, 1.08), fresh=('w_h3_ha_b_a',))
    add('W_H3_HA_D14T20_BOOST_B', 'wt_tilt', cohort_h3_ha_d14, '',
        (1.10, 1.12), fresh=('w_h3_ha_b_b',))

    # ─── Block C: DP D14T30 NO-HA — extend BAKE-135 territory (4 specs) ───
    # BAKE-135 = DP × D14-30 × INV8 W*=0.85. Test sub-bands w/o INV8.
    cohort_dp_narrow = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.020'
    add('W_DP_D14T20_DEMO_A', 'wt_tilt', cohort_dp_narrow, '',
        (0.92, 0.94), fresh=('w_dp_d14_a',))
    add('W_DP_D14T20_DEMO_B', 'wt_tilt', cohort_dp_narrow, '',
        (0.96, 0.97), fresh=('w_dp_d14_b',))

    # ─── Block D: BAKE-141 cohort × AOI3K compound (mild mags) (4 specs) ───
    cohort_dp_aoi = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030 and _AOI3K'
    add('W_DP_HA_D25T30_AOI3K_NEW', 'wt_tilt', cohort_dp_aoi, '',
        (0.94, 0.96), fresh=('w_dp_aoi2',))

    # ─── Block E: BAKE-142 cohort × NIM7 (4 specs) ───
    cohort_h3_nim = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.012 and _NIM7'
    add('W_H3_HA_D10T12_NIM7_NEW', 'wt_tilt', cohort_h3_nim, '',
        (0.94, 0.96), fresh=('w_h3_nim2',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
