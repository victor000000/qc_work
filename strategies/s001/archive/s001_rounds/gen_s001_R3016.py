"""R3016 — VRFY W_H3_HA_D10T12 m0.94 + narrower BAKE-141 sub-bands.

R3013 first results (NOOP=3.33505):
  W_H3_HA_D10T12 m0.94 = 3.33526 (+0.00021) ← BAKE-142 UPGRADE candidate (single mag)
  W_H3_HA_D10T12 m0.96 = 3.33515 (+0.00010) ← already baked
  W_H3_HA_D10T12 m0.98 = 3.33515 (+0.00010)
  W_H3_HA_D12T14 m0.97/0.98 = NEG (D12-14 NOT productive)

BAKE-142 currently m0.96. Need m0.92/m0.93 confirmation before upgrade.

R3016:
 - Block A: W_H3_HA_D10T12 m0.92/0.93 VRFY (BAKE-142 upgrade candidate)
 - Block B: W_DP_HA D26-28 sub-band of BAKE-141
 - Block C: W_DP_HA D28-30 sub-band of BAKE-141
 - Block D: W_H3_HA_D10T12 × NIM7 fund-gate compound
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
    R = Round(rid=3016, priority=1)

    DPANIC = 'self._reg_double_panic'
    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W_H3_HA_D10T12 m0.92-0.93 VRFY BAKE-142 upgrade (4 specs) ───
    cohort_h3_d10 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.012'
    add('W_H3_HA_D10T12_M92_VRFY', 'wt_tilt', cohort_h3_d10, '',
        (0.92, 0.93), fresh=('w_h3_d10_m92',))
    add('W_H3_HA_D10T12_M94_RECOMFIRM', 'wt_tilt', cohort_h3_d10, '',
        (0.94, 0.945), fresh=('w_h3_d10_m94_v',))

    # ─── Block B: W_DP_HA D26-28 sub-band of BAKE-141 (4 specs) ───
    cohort_dp_d26 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.026 and decline < 0.028'
    add('W_DP_HA_D26T28_DEMO_A', 'wt_tilt', cohort_dp_d26, '',
        (0.92, 0.94), fresh=('w_dp_d26_a',))
    add('W_DP_HA_D26T28_DEMO_B', 'wt_tilt', cohort_dp_d26, '',
        (0.96, 0.97), fresh=('w_dp_d26_b',))

    # ─── Block C: W_DP_HA D28-30 sub-band of BAKE-141 (4 specs) ───
    cohort_dp_d28 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.028 and decline < 0.030'
    add('W_DP_HA_D28T30_DEMO_A', 'wt_tilt', cohort_dp_d28, '',
        (0.92, 0.94), fresh=('w_dp_d28_a',))
    add('W_DP_HA_D28T30_DEMO_B', 'wt_tilt', cohort_dp_d28, '',
        (0.96, 0.97), fresh=('w_dp_d28_b',))

    # ─── Block D: W_H3_HA_D10T12 × NIM7 fund-gate compound (4 specs) ───
    cohort_h3_nim = cohort_h3_d10 + ' and _NIM7'
    add('W_H3_HA_D10T12_NIM7_A', 'wt_tilt', cohort_h3_nim, '',
        (0.90, 0.92), fresh=('w_h3_nim_a',))
    add('W_H3_HA_D10T12_NIM7_B', 'wt_tilt', cohort_h3_nim, '',
        (0.94, 0.96), fresh=('w_h3_nim_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
