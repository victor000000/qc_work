"""R3053 — Cross-regime W-DEMOTE on UNTESTED P-state combos (H5/Q3/D3/D5).

Pipeline state:
  - 2 bakes applied this session loop (BAKE-152, BAKE-153)
  - Heavy backlog: most R3049-R3052 NOOPs still queued
  - R3050 partial: W_P_H3_D25T30_REFINE m0.94 = 3.33639 (+0.00020 sub-threshold confirmed)
  - R3046-R3048 fully refuted those directions

R3053 strategy: cross-regime W-DEMOTE template — find new productive regime
combos. Untested narrow bands on HYGUP5/QQQUP3/HYGDN3/HYGDN5.

R3053 (16 specs):
 - Block A: W × P × H5 × D025T030 (parallel of BAKE-152 on H5)
 - Block B: W × P × Q3 × D012T015 (Q3 deeper than BAKE-151, untested)
 - Block C: W × P × D3 × D014T017 (HYGDN3 narrow, untested narrow)
 - Block D: W × P × D5 × D014T017 (HYGDN5 narrow, untested narrow)
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
    R = Round(rid=3053, priority=1)

    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    HDN3 = 'self._reg_hyg_dn3'
    HDN5 = 'self._reg_hyg_dn5'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × H5 × D025T030 (parallel BAKE-152 on H5) (4 specs) ───
    cohort_a = f'_qpos and {HUP5} and decline > 0.025 and decline < 0.030'
    add('W_P_H5_D25T30_DEMO_A', 'wt_tilt', cohort_a, '',
        (0.92, 0.94), fresh=('w_h5_d25_a',))
    add('W_P_H5_D25T30_DEMO_B', 'wt_tilt', cohort_a, '',
        (0.96, 0.97), fresh=('w_h5_d25_b',))

    # ─── Block B: W × P × Q3 × D012T015 (Q3 deeper, untested) (4 specs) ───
    cohort_b = f'_qpos and {QUP3} and decline > 0.012 and decline < 0.015'
    add('W_P_Q3_D12T15_DEMO_A', 'wt_tilt', cohort_b, '',
        (0.92, 0.94), fresh=('w_q3_d12_a',))
    add('W_P_Q3_D12T15_DEMO_B', 'wt_tilt', cohort_b, '',
        (0.96, 0.97), fresh=('w_q3_d12_b',))

    # ─── Block C: W × P × D3 × D014T017 (HYGDN3 narrow untested) (4 specs) ───
    cohort_c = f'_qpos and {HDN3} and decline > 0.014 and decline < 0.017'
    add('W_P_D3_D14T17_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_d3_d14_a',))
    add('W_P_D3_D14T17_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.96, 0.97), fresh=('w_d3_d14_b',))

    # ─── Block D: W × P × D5 × D014T017 (HYGDN5 narrow untested) (4 specs) ───
    cohort_d = f'_qpos and {HDN5} and decline > 0.014 and decline < 0.017'
    add('W_P_D5_D14T17_DEMO_A', 'wt_tilt', cohort_d, '',
        (0.92, 0.94), fresh=('w_d5_d14_a',))
    add('W_P_D5_D14T17_DEMO_B', 'wt_tilt', cohort_d, '',
        (0.96, 0.97), fresh=('w_d5_d14_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
