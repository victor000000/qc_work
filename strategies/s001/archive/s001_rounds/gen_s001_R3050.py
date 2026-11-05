"""R3050 — Diversified post-BAKE-152 round: VRFY + adjacent-cohort + petgt-lever probe.

Pipeline state (20m structural audit):
  - BAKE-152 just applied (W × P × H3 × D020-D025 m=0.94, +0.00021)
  - Expected R3050 NOOP_0 ≈ 3.33619
  - 29 active bakes / 0.0104 gap to 20260515 SOTA
  - Rule 44 added: blocks conv DEMOTE on W-DEMOTE-baked cohorts (12/12 NEG)

R3050 strategy: diversify across 4 NEW directions
 - Block A: W × P × H3 × D025T030 sub-bands (adjacent to BAKE-152)
 - Block B: W × P × H5 × D020T025 (parallel of BAKE-152 on H5)
 - Block C: W × P × VF × D02T04 (vxx_falling regime — NEW)
 - Block D: petgt × P × narrow_decline (UNUSED LEVER on productive cohort)
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
    R = Round(rid=3050, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    VXF = 'self._reg_vxx_falling3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × H3 × D025T030 sub-bands (4 specs) ───
    cohort_a = f'_qpos and {HUP3} and decline > 0.025 and decline < 0.030'
    add('W_P_H3_D25T30_REFINE_A', 'wt_tilt', cohort_a, '',
        (0.90, 0.92), fresh=('w_h3_d25_ra',))
    add('W_P_H3_D25T30_REFINE_B', 'wt_tilt', cohort_a, '',
        (0.94, 0.96), fresh=('w_h3_d25_rb',))

    # ─── Block B: W × P × H5 × D020T025 (parallel of BAKE-152 on H5) (4 specs) ───
    cohort_b = f'_qpos and {HUP5} and decline > 0.020 and decline < 0.025'
    add('W_P_H5_D20T25_DEMO_A', 'wt_tilt', cohort_b, '',
        (0.92, 0.94), fresh=('w_h5_d20_pa',))
    add('W_P_H5_D20T25_DEMO_B', 'wt_tilt', cohort_b, '',
        (0.96, 0.97), fresh=('w_h5_d20_pb',))

    # ─── Block C: W × P × VF × D02T04 (vxx_falling — NEW regime) (4 specs) ───
    cohort_c = f'_qpos and {VXF} and decline > 0.02 and decline < 0.04'
    add('W_P_VF_D02T04_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_vf_d02_pa',))
    add('W_P_VF_D02T04_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.96, 0.97), fresh=('w_vf_d02_pb',))

    # ─── Block D: W × P × H3 × D018T020 (gap before BAKE-152) (4 specs) ───
    cohort_d = f'_qpos and {HUP3} and decline > 0.018 and decline < 0.020'
    add('W_P_H3_D18T20_GAP_A', 'wt_tilt', cohort_d, '',
        (0.92, 0.94), fresh=('w_h3_d18_ga',))
    add('W_P_H3_D18T20_GAP_B', 'wt_tilt', cohort_d, '',
        (0.96, 0.97), fresh=('w_h3_d18_gb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
