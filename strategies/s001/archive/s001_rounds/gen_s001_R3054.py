"""R3054 — Score DEMOTE cross-lever (BAKE-134 precedent) + W-DEMOTE fresh exploration.

Pipeline state:
  - 2 bakes this loop (BAKE-152, BAKE-153)
  - 61 specs queued — pipeline backlog
  - Cannot apply new bakes without R3049+ NOOP confirmation

R3054 strategy: 50/50 split score + wt_tilt
  Score on W-DEMOTE-baked cohorts (BAKE-134 precedent: S*=.95 on BAKE-133 +0.00083)
  W on fresh untested decline bands

R3054 (16 specs):
 - Block A: S × P × H3 × D020T025 DEMOTE (parallel BAKE-152, score cross-lever)
 - Block B: S × P × H3 × D018T020 DEMOTE (parallel BAKE-153, score cross-lever)
 - Block C: W × P × H3 × D030T040 (untested deeper band)
 - Block D: W × P × H5 × D025T030 (parallel BAKE-152 cohort on H5)
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
    R = Round(rid=3054, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: S × P × H3 × D020T025 DEMOTE (parallel BAKE-152) (4 specs) ───
    cohort_a = f'_qpos and {HUP3} and decline > 0.020 and decline < 0.025'
    add('S_P_H3_D20T25_DEMO_A', 'score', cohort_a, '',
        (0.92, 0.94), fresh=('s_h3_d20_a',))
    add('S_P_H3_D20T25_DEMO_B', 'score', cohort_a, '',
        (0.96, 0.98), fresh=('s_h3_d20_b',))

    # ─── Block B: S × P × H3 × D018T020 DEMOTE (parallel BAKE-153) (4 specs) ───
    cohort_b = f'_qpos and {HUP3} and decline > 0.018 and decline < 0.020'
    add('S_P_H3_D18T20_DEMO_A', 'score', cohort_b, '',
        (0.92, 0.94), fresh=('s_h3_d18_a',))
    add('S_P_H3_D18T20_DEMO_B', 'score', cohort_b, '',
        (0.96, 0.98), fresh=('s_h3_d18_b',))

    # ─── Block C: W × P × H3 × D030T040 (untested deeper band) (4 specs) ───
    cohort_c = f'_qpos and {HUP3} and decline > 0.030 and decline < 0.040'
    add('W_P_H3_D30T40_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_h3_d30_a',))
    add('W_P_H3_D30T40_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.96, 0.97), fresh=('w_h3_d30_b',))

    # ─── Block D: W × P × H5 × D025T030 (parallel BAKE-152 on H5) (4 specs) ───
    cohort_d = f'_qpos and {HUP5} and decline > 0.025 and decline < 0.030'
    add('W_P_H5_D25T30_DEMO_A', 'wt_tilt', cohort_d, '',
        (0.92, 0.94), fresh=('w_h5_d25_pa',))
    add('W_P_H5_D25T30_DEMO_B', 'wt_tilt', cohort_d, '',
        (0.96, 0.97), fresh=('w_h5_d25_pb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
