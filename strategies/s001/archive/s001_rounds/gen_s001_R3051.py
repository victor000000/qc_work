"""R3051 — Narrow sub-band refinement within BAKE-152 + deeper VF + DP-HA new band.

Pipeline state:
  - BAKE-152 just applied (W × P × H3 × D020-D025 m=0.94)
  - R3045 done: W_H3_D25T30 m0.94/m0.96 +0.00010 × 2 (sub-threshold, watching)
  - R3046+ running/queued (88 specs in flight)
  - Heavy backlog — keep specs orthogonal to in-flight ones

R3051 (16 specs):
 - Block A: W × P × H3 × D020T022 narrow (within BAKE-152, lower half)
 - Block B: W × P × H3 × D022T025 narrow (within BAKE-152, upper half)
 - Block C: W × P × VF × D04T06 (deeper VF — R3046 tests D02-D04)
 - Block D: W × P × DP × HA × D015T020 (untested HA narrow band)
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
    R = Round(rid=3051, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    VXF = 'self._reg_vxx_falling3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × H3 × D020T022 narrow (BAKE-152 lower half) (4 specs) ───
    cohort_a = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.022'
    add('W_P_H3_D20T22_NARROW_A', 'wt_tilt', cohort_a, '',
        (0.90, 0.92), fresh=('w_h3_d20t22_a',))
    add('W_P_H3_D20T22_NARROW_B', 'wt_tilt', cohort_a, '',
        (0.94, 0.96), fresh=('w_h3_d20t22_b',))

    # ─── Block B: W × P × H3 × D022T025 narrow (BAKE-152 upper half) (4 specs) ───
    cohort_b = f'_qpos and {HUP3} and decline > 0.022 and decline < 0.025'
    add('W_P_H3_D22T25_NARROW_A', 'wt_tilt', cohort_b, '',
        (0.90, 0.92), fresh=('w_h3_d22t25_a',))
    add('W_P_H3_D22T25_NARROW_B', 'wt_tilt', cohort_b, '',
        (0.94, 0.96), fresh=('w_h3_d22t25_b',))

    # ─── Block C: W × P × VF × D04T06 (deeper VF) (4 specs) ───
    cohort_c = f'_qpos and {VXF} and decline > 0.04 and decline < 0.06'
    add('W_P_VF_D04T06_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.90, 0.92), fresh=('w_vf_d04_a',))
    add('W_P_VF_D04T06_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.94, 0.96), fresh=('w_vf_d04_b',))

    # ─── Block D: W × P × Q3 × D022T025 (parallel of BAKE-152 narrow on Q3) (4 specs) ───
    cohort_d = (f'_qpos and self._reg_qqq_up3'
                f' and decline > 0.022 and decline < 0.025')
    add('W_P_Q3_D22T25_DEMO_A', 'wt_tilt', cohort_d, '',
        (0.92, 0.94), fresh=('w_q3_d22t25_a',))
    add('W_P_Q3_D22T25_DEMO_B', 'wt_tilt', cohort_d, '',
        (0.96, 0.97), fresh=('w_q3_d22t25_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
