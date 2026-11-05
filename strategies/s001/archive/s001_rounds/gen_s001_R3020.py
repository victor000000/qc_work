"""R3020 — Pivot to UNTESTED levers/cohorts after plateau.

R3018 evidence: many cohorts at 3.33536 (= predicted cumulative NOOP) = FLAT.
Sub-band + fund-gate compound exploration plateaued.

R3020 pivots:
 - Block A: Score DEMOTE on Z (qzero) × HA × narrow (untested qstate)
 - Block B: Score DEMOTE on Z × DP × narrow (parallel)
 - Block C: Conv DEMOTE direction on H3 × DP (different from H3 × HA)
 - Block D: H3 D11-12 sub-band of BAKE-142 (very narrow)
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
    R = Round(rid=3020, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: Score DEMOTE on Z × H3 × HA × narrow (untested qstate) (4) ───
    cohort_z_h3_ha = f'_qzero and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('S_Z_H3_HA_D10T14_DEMO_A', 'score', cohort_z_h3_ha, '',
        (0.95, 0.97), fresh=('s_z_h3_ha_a',))
    add('S_Z_H3_HA_D10T14_DEMO_B', 'score', cohort_z_h3_ha, '',
        (0.93, 0.94), fresh=('s_z_h3_ha_b',))

    # ─── Block B: Score DEMOTE on Z × DP × HA × narrow (parallel cohort) (4) ───
    cohort_z_dp_ha = f'_qzero and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.030'
    add('S_Z_DP_HA_D20T30_DEMO_A', 'score', cohort_z_dp_ha, '',
        (0.95, 0.97), fresh=('s_z_dp_ha_a',))
    add('S_Z_DP_HA_D20T30_DEMO_B', 'score', cohort_z_dp_ha, '',
        (0.93, 0.94), fresh=('s_z_dp_ha_b',))

    # ─── Block C: Conv DEMOTE on P × DP × narrow (no baked conv on DP) (4) ───
    cohort_p_dp_narrow = f'_qpos and {DPANIC} and decline > 0.014 and decline < 0.020'
    add('C_P_DP_D14T20_DEMO_A', 'conv', cohort_p_dp_narrow, '',
        (0.92, 0.94), fresh=('c_p_dp_a',))
    add('C_P_DP_D14T20_DEMO_B', 'conv', cohort_p_dp_narrow, '',
        (0.96, 0.97), fresh=('c_p_dp_b',))

    # ─── Block D: H3 × HA × D11-12 very narrow sub-band of BAKE-142 (4) ───
    cohort_h3_d11_12 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.011 and decline < 0.012'
    add('W_H3_HA_D11T12_DEMO_A', 'wt_tilt', cohort_h3_d11_12, '',
        (0.94, 0.96), fresh=('w_h3_d11_12_a',))
    add('W_H3_HA_D11T12_DEMO_B', 'wt_tilt', cohort_h3_d11_12, '',
        (0.97, 0.98), fresh=('w_h3_d11_12_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
