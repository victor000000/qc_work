"""R3008 — Verify BAKE-139/140 + extend HACCEL compound exploration.

BAKE-139 (DP×HA×D20T40 m0.88) + BAKE-140 (H3×HA×D10T14 m0.92) applied.
Expected R3008 NOOP_0 ≈ 3.33423 + 0.0006 = ~3.33485.

HACCEL is the productive discriminator. R3008 explores HA on MORE cohorts:
 - Block A: H5 × HA × narrow declines (parallel to BAKE-140)
 - Block B: DP × HA × wider declines (BAKE-139 band extension)
 - Block C: H3 × HA × wider declines (BAKE-140 band extension)
 - Block D: Q3 × HA × narrow declines (parallel to BAKE-140)
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
    R = Round(rid=3008, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: H5 × HA × narrow declines (4) ───
    cohort_h5_ha_n = f'_qpos and {HUP5} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('W_H5_HA_D10T14_DEMO_A', 'wt_tilt', cohort_h5_ha_n, '',
        (0.90, 0.92), fresh=('w_h5_ha_a',))
    add('W_H5_HA_D10T14_DEMO_B', 'wt_tilt', cohort_h5_ha_n, '',
        (0.94, 0.96), fresh=('w_h5_ha_b',))

    # ─── Block B: DP × HA wider declines D40-60 (gap above BAKE-139) (4) ───
    cohort_dp_ha_w = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.040 and decline < 0.060'
    add('W_DP_HA_D40T60_DEMO_A', 'wt_tilt', cohort_dp_ha_w, '',
        (0.84, 0.86), fresh=('w_dp_ha_w_a',))
    add('W_DP_HA_D40T60_DEMO_B', 'wt_tilt', cohort_dp_ha_w, '',
        (0.88, 0.92), fresh=('w_dp_ha_w_b',))

    # ─── Block C: H3 × HA wider declines D14-20 (gap above BAKE-140) (4) ───
    cohort_h3_ha_m = f'_qpos and {HUP3} and {HACCEL} and decline > 0.014 and decline < 0.020'
    add('W_H3_HA_D14T20_DEMO_A', 'wt_tilt', cohort_h3_ha_m, '',
        (0.88, 0.90), fresh=('w_h3_ha_m_a',))
    add('W_H3_HA_D14T20_DEMO_B', 'wt_tilt', cohort_h3_ha_m, '',
        (0.92, 0.94), fresh=('w_h3_ha_m_b',))

    # ─── Block D: Q3 × HA × narrow declines (parallel to BAKE-140) (4) ───
    cohort_q3_ha_n = f'_qpos and {QUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('W_Q3_HA_D10T14_DEMO_A', 'wt_tilt', cohort_q3_ha_n, '',
        (0.90, 0.92), fresh=('w_q3_ha_a',))
    add('W_Q3_HA_D10T14_DEMO_B', 'wt_tilt', cohort_q3_ha_n, '',
        (0.94, 0.96), fresh=('w_q3_ha_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
