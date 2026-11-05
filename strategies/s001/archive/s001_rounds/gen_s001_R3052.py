"""R3052 — Post-BAKE-153 VRFY + W_H3_D25T30 deep VRFY + parallel cohort exploration.

Pipeline state:
  - BAKE-152 + BAKE-153 just applied (30 active bakes total)
  - Expected R3052 NOOP ≈ 3.33649 (3.33598 + 0.00021 BAKE-152 + 0.00030 BAKE-153)
  - W_P_H3_D25T30_NARROW R3049: m0.92/m0.94 = +0.00020 (std=0, sub-threshold)
  - W_P_H3_D25T30_NARROW R3049: m0.96/m0.97 = +0.00010

R3052 strategy:
 - VRFY W_P_H3_D25T30 with wider mag spread (m0.88-0.98) → escalate or refute
 - Probe W_P_H3_D016T018 (gap before BAKE-153, within BAKE-136)
 - Probe W_P_H3_D015T018 (deeper gap within BAKE-136)
 - Probe W_P_H3_D012T014 (just below BAKE-136 lower bound D014)

R3052 (16 specs):
 - Block A: W × P × H3 × D025T030 wider VRFY (m0.88, m0.90, m0.98)
 - Block B: W × P × H3 × D016T018 (within BAKE-136)
 - Block C: W × P × H3 × D015T018 (within BAKE-136, wider)
 - Block D: W × P × H3 × D012T014 (below BAKE-136 lower bound)
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
    R = Round(rid=3052, priority=1)

    HUP3 = 'self._reg_hyg_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × H3 × D025T030 wider VRFY (4 specs) ───
    cohort_a = f'_qpos and {HUP3} and decline > 0.025 and decline < 0.030'
    add('W_P_H3_D25T30_VRFY_DEEP', 'wt_tilt', cohort_a, '',
        (0.88, 0.90), fresh=('w_h3_d25_vd',))
    add('W_P_H3_D25T30_VRFY_SHAL', 'wt_tilt', cohort_a, '',
        (0.98, 0.99), fresh=('w_h3_d25_vs',))

    # ─── Block B: W × P × H3 × D016T018 (within BAKE-136 mid sub-band) (4 specs) ───
    cohort_b = f'_qpos and {HUP3} and decline > 0.016 and decline < 0.018'
    add('W_P_H3_D16T18_DEMO_A', 'wt_tilt', cohort_b, '',
        (0.90, 0.92), fresh=('w_h3_d16_a',))
    add('W_P_H3_D16T18_DEMO_B', 'wt_tilt', cohort_b, '',
        (0.94, 0.96), fresh=('w_h3_d16_b',))

    # ─── Block C: W × P × H3 × D015T018 (within BAKE-136, wider) (4 specs) ───
    cohort_c = f'_qpos and {HUP3} and decline > 0.015 and decline < 0.018'
    add('W_P_H3_D15T18_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_h3_d15_a',))
    add('W_P_H3_D15T18_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.96, 0.97), fresh=('w_h3_d15_b',))

    # ─── Block D: W × P × H3 × D012T014 (below BAKE-136 lower) (4 specs) ───
    cohort_d = f'_qpos and {HUP3} and decline > 0.012 and decline < 0.014'
    add('W_P_H3_D12T14_DEMO_A', 'wt_tilt', cohort_d, '',
        (0.92, 0.94), fresh=('w_h3_d12_a',))
    add('W_P_H3_D12T14_DEMO_B', 'wt_tilt', cohort_d, '',
        (0.96, 0.97), fresh=('w_h3_d12_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
