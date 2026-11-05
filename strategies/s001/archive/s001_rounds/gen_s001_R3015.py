"""R3015 — BAKE-140 H3-HA sub-bands + BAKE-141 fund-gate variants.

R3012 PRE-BAKE-141 data showed:
  W_H3_HA_D10T12 m0.94 = +0.00020 (single mag candidate)
  W_DP_HA_D22T30 NIM7/FCF7 m0.84-0.92 = +0.00020 multi-mag

R3015 post-BAKE-141 verification + sub-band fund-gate extension:
 - Block A: H3-HA D10-12 multi-mag (extension of R3013)
 - Block B: H3-HA D12-14 multi-mag (parallel sub-band)
 - Block C: DP×HA×D25-30 × NIM7 (sub-band fund-gate, BAKE-141 cohort)
 - Block D: DP×HA×D25-30 × FCF7 (sub-band fund-gate, BAKE-141 cohort)
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
    R = Round(rid=3015, priority=1)

    DPANIC = 'self._reg_double_panic'
    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: H3-HA D10-12 multi-mag (4 specs) ───
    cohort_h3_d10 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.012'
    add('W_H3_HA_D10T12_VRFY_A', 'wt_tilt', cohort_h3_d10, '',
        (0.92, 0.94), fresh=('w_h3_d10_v_a',))
    add('W_H3_HA_D10T12_VRFY_B', 'wt_tilt', cohort_h3_d10, '',
        (0.96, 0.97), fresh=('w_h3_d10_v_b',))

    # ─── Block B: H3-HA D12-14 multi-mag (4 specs) ───
    cohort_h3_d12 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.012 and decline < 0.014'
    add('W_H3_HA_D12T14_VRFY_A', 'wt_tilt', cohort_h3_d12, '',
        (0.92, 0.94), fresh=('w_h3_d12_v_a',))
    add('W_H3_HA_D12T14_VRFY_B', 'wt_tilt', cohort_h3_d12, '',
        (0.96, 0.97), fresh=('w_h3_d12_v_b',))

    # ─── Block C: DP×HA×D25-30 × NIM7 fund-gate (4 specs) ───
    cohort_dp_nim = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030 and _NIM7'
    add('W_DP_HA_D25T30_NIM7_A', 'wt_tilt', cohort_dp_nim, '',
        (0.92, 0.94), fresh=('w_dp_nim_a',))
    add('W_DP_HA_D25T30_NIM7_B', 'wt_tilt', cohort_dp_nim, '',
        (0.96, 0.97), fresh=('w_dp_nim_b',))

    # ─── Block D: DP×HA×D25-30 × FCF7 fund-gate (4 specs) ───
    cohort_dp_fcf = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030 and _FCF7'
    add('W_DP_HA_D25T30_FCF7_A', 'wt_tilt', cohort_dp_fcf, '',
        (0.92, 0.94), fresh=('w_dp_fcf_a',))
    add('W_DP_HA_D25T30_FCF7_B', 'wt_tilt', cohort_dp_fcf, '',
        (0.96, 0.97), fresh=('w_dp_fcf_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
