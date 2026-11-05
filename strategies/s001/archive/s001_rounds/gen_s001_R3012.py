"""R3012 — BAKE-139 sub-band fine-grained exploration + fund-gate variants.

R3010 first results (NOOP=3.33485 expected):
  W_DP_HA_D25T30 m0.90 = 3.33505 (+0.00020) ← CANDIDATE-D single-mag
  W_DP_HA_D30T35 m0.86 = 3.33485 (FLAT)
  S_H3_HA_D10T14 m0.93 = 3.31773 (CATASTROPHIC -0.017)

Strategy: fine-grain BAKE-139's D20-40 territory + try fund-gate variants.
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
    R = Round(rid=3012, priority=1)

    DPANIC = 'self._reg_double_panic'
    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-139 D25-30 multi-mag VRFY (4 specs) ───
    cohort_d25 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.025 and decline < 0.030'
    add('W_DP_HA_D25T30_VRFY_LO', 'wt_tilt', cohort_d25, '',
        (0.86, 0.88), fresh=('w_dp_d25_lo',))
    add('W_DP_HA_D25T30_VRFY_HI', 'wt_tilt', cohort_d25, '',
        (0.92, 0.94), fresh=('w_dp_d25_hi',))

    # ─── Block B: BAKE-139 D22-25 sub-band (4 specs) ───
    cohort_d22 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.022 and decline < 0.025'
    add('W_DP_HA_D22T25_DEMO_A', 'wt_tilt', cohort_d22, '',
        (0.86, 0.88), fresh=('w_dp_d22_a',))
    add('W_DP_HA_D22T25_DEMO_B', 'wt_tilt', cohort_d22, '',
        (0.90, 0.92), fresh=('w_dp_d22_b',))

    # ─── Block C: BAKE-140 sub-bands (h3 × HA narrow) (4 specs) ───
    # BAKE-140 cohort is .010<d<.014. Try .010-.012 and .012-.014 sub-bands.
    # Rule 37 may block deeper demote stacks; use mag close to 1.0
    cohort_h3_d10t12 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.012'
    add('W_H3_HA_D10T12_VRFY', 'wt_tilt', cohort_h3_d10t12, '',
        (0.94, 0.96), fresh=('w_h3_d10_12',))

    # ─── Block D: BAKE-139 cohort with NIM7 fund-gate variant (different mag) (4 specs) ───
    cohort_nim_d22 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.022 and decline < 0.030 and _NIM7'
    add('W_DP_HA_D22T30_NIM7_A', 'wt_tilt', cohort_nim_d22, '',
        (0.84, 0.86), fresh=('w_nim_a',))
    add('W_DP_HA_D22T30_NIM7_B', 'wt_tilt', cohort_nim_d22, '',
        (0.90, 0.92), fresh=('w_nim_b',))

    # ─── Block E: BAKE-139 cohort with FCF7 fund-gate (4 specs) ───
    cohort_fcf_d22 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.022 and decline < 0.030 and _FCF7'
    add('W_DP_HA_D22T30_FCF7_A', 'wt_tilt', cohort_fcf_d22, '',
        (0.84, 0.86), fresh=('w_fcf_a',))
    add('W_DP_HA_D22T30_FCF7_B', 'wt_tilt', cohort_fcf_d22, '',
        (0.90, 0.92), fresh=('w_fcf_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
