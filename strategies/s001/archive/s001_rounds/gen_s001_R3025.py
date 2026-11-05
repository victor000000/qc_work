"""R3025 — BAKE-147/148 candidate VRFY + post-revert exploration.

R3024 first results (NOOP pending, expected 3.33567):
  W_H3_HA_D14T17 m1.14 = m1.18 = 3.33577 (multi-mag, +0.00010)
  W_H3_HA_D14T17 m1.12 = m1.20 = 3.33567 (FLAT)

Plateau peaks at effective 1.5+ from BAKE-136*144*147*probe.

R3025:
 - Block A: W_H3_HA_D14T17 m1.13/m1.15/m1.16 — narrow peak verification
 - Block B: BAKE-146 cohort × deeper W probes (parallel to BAKE-147 deep)
 - Block C: New cohort — H3 × HA × D11-12 fine sub-band
 - Block D: BAKE-143 D14-17 stacked deeper mag
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
    R = Round(rid=3025, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W_H3_HA_D14T17 peak verification m1.13-1.16 (4 specs) ───
    cohort_h3_ha_d14_17 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.017'
    add('W_H3_HA_D14T17_PEAK_A', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.13, 1.15), fresh=('w_h3_d14_17_pk_a',))
    add('W_H3_HA_D14T17_PEAK_B', 'wt_tilt', cohort_h3_ha_d14_17, '',
        (1.16, 1.17), fresh=('w_h3_d14_17_pk_b',))

    # ─── Block B: BAKE-146 cohort deeper W stacked (4 specs) ───
    cohort_dp_d14_17 = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.017'
    add('W_DP_D14T17_STACK_A', 'wt_tilt', cohort_dp_d14_17, '',
        (0.88, 0.90), fresh=('w_dp_d14_17_st_a',))
    add('W_DP_D14T17_STACK_B', 'wt_tilt', cohort_dp_d14_17, '',
        (0.92, 0.94), fresh=('w_dp_d14_17_st_b',))

    # ─── Block C: BAKE-143 D17-20 sub-band (untested half) (4 specs) ───
    cohort_dp_d17_20 = f'_qpos and {DPANIC} and decline > 0.017 and decline < 0.020'
    add('W_DP_D17T20_DEMO_A', 'wt_tilt', cohort_dp_d17_20, '',
        (0.92, 0.94), fresh=('w_dp_d17_20_aa',))
    add('W_DP_D17T20_DEMO_B', 'wt_tilt', cohort_dp_d17_20, '',
        (0.96, 0.97), fresh=('w_dp_d17_20_bb',))

    # ─── Block D: BAKE-144 D17-20 sub-band (untested half) (4 specs) ───
    cohort_h3_ha_d17_20 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.017 and decline < 0.020'
    add('W_H3_HA_D17T20_DEEP_A', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.12, 1.14), fresh=('w_h3_ha_d17_20_aa',))
    add('W_H3_HA_D17T20_DEEP_B', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.16, 1.18), fresh=('w_h3_ha_d17_20_bb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
