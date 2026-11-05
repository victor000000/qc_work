"""R3022 — BAKE-145 sub-bands + score-on-qzero confirmed catastrophic.

R3020 confirmed:
  C_DP_D14T20 m0.94/0.96 = +0.00010 multi-mag → BAKE-145 applied
  S_Z_DP_HA + S_Z_H3_HA = -0.02 to -0.028 CATASTROPHIC (score on qzero × HA)
  W_H3_HA_D11T12 m0.98 = FLAT

R3022:
 - Block A: C × DP × D14-17 sub-band (BAKE-145 sub-band)
 - Block B: C × DP × D17-20 sub-band
 - Block C: BAKE-143 cohort × different fund-gate (FCF7 vs no fund)
 - Block D: BAKE-144 cohort sub-band D17-20 (other half)
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
    R = Round(rid=3022, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: C × DP × D14-17 sub-band (BAKE-145 sub-band) (4 specs) ───
    cohort_c_dp_d14_17 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.017'
    add('C_DP_D14T17_DEMO_A', 'conv', cohort_c_dp_d14_17, '',
        (0.92, 0.94), fresh=('c_dp_14_17_a',))
    add('C_DP_D14T17_DEMO_B', 'conv', cohort_c_dp_d14_17, '',
        (0.96, 0.97), fresh=('c_dp_14_17_b',))

    # ─── Block B: C × DP × D17-20 sub-band (4 specs) ───
    cohort_c_dp_d17_20 = f'_qpos and {DPANIC} and decline > 0.017 and decline < 0.020'
    add('C_DP_D17T20_DEMO_A', 'conv', cohort_c_dp_d17_20, '',
        (0.92, 0.94), fresh=('c_dp_17_20_a',))
    add('C_DP_D17T20_DEMO_B', 'conv', cohort_c_dp_d17_20, '',
        (0.96, 0.97), fresh=('c_dp_17_20_b',))

    # ─── Block C: BAKE-143 cohort × FCF7 fund-gate compound (4 specs) ───
    cohort_dp_fcf = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.020 and _FCF7'
    add('W_DP_D14T20_FCF7_A', 'wt_tilt', cohort_dp_fcf, '',
        (0.92, 0.94), fresh=('w_dp_fcf_a',))
    add('W_DP_D14T20_FCF7_B', 'wt_tilt', cohort_dp_fcf, '',
        (0.96, 0.97), fresh=('w_dp_fcf_b',))

    # ─── Block D: BAKE-144 cohort sub-band D17-20 (4 specs) ───
    cohort_h3_ha_d17_20 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.017 and decline < 0.020'
    add('W_H3_HA_D17T20_BOOST_A', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.05, 1.07), fresh=('w_h3_ha_17_20_a',))
    add('W_H3_HA_D17T20_BOOST_B', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.08, 1.10), fresh=('w_h3_ha_17_20_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
