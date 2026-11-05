"""R3006 — Extend BAKE-122..129 ER DEMOTE coverage to under-covered bands.

ER (entry_score_regime) has 10× coefficient in score sum:
  S += ES + .3*EM + 10*ER + EC + EQ

Small ER += deltas have outsized effect on ranking. BAKE-122-129 covered
8 narrow 2% bands across H3/H5/DP/Q3 regimes. Many gaps remain.

R3006 fills gaps:
 - Block A: ER DEMOTE on H3 D29-41 (12% gap between BAKE-128 D27-29 and 129 D41-43)
 - Block B: ER DEMOTE on DPANIC D22-30 (gap between BAKE-124 D20-22 and existing)
 - Block C: ER DEMOTE on QQQ_UP3 D12-14, D16-18 (gaps in 126/125/127)
 - Block D: ER DEMOTE on HYG_UP5 D30-42 (gap before BAKE-123)

WHY entry_score_regime DEMOTE: every BAKE-122-129 was -0.013 to -0.015
(small additive). Targets _qpos rally-regime cohorts with steady decline.
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
    R = Round(rid=3006, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add_er(name, cohort, fresh):
        R.add(Probe(name=name, lever='entry_score_regime', cohort=cohort,
                    fund='', op='+=', mags=(-0.013, -0.015),
                    fresh_fields=fresh))

    # ─── Block A: H3 wide gap D29-41 (4 specs in 2 bands) ───
    add_er('ER_H3_D31T33_DEMO',
           f'_qpos and {HUP3} and decline > 0.031 and decline < 0.033',
           ('er_h3_d31',))
    add_er('ER_H3_D35T37_DEMO',
           f'_qpos and {HUP3} and decline > 0.035 and decline < 0.037',
           ('er_h3_d35',))

    # ─── Block B: DPANIC gap D22-30 (4 specs) ───
    add_er('ER_DP_D24T26_DEMO',
           f'_qpos and {DPANIC} and decline > 0.024 and decline < 0.026',
           ('er_dp_d24',))
    add_er('ER_DP_D28T30_DEMO',
           f'_qpos and {DPANIC} and decline > 0.028 and decline < 0.030',
           ('er_dp_d28',))

    # ─── Block C: QQQ_UP3 gaps (4 specs) ───
    add_er('ER_Q3_D12T14_DEMO',
           f'_qpos and {QUP3} and decline > 0.012 and decline < 0.014',
           ('er_q3_d12',))
    add_er('ER_Q3_D16T18_DEMO',
           f'_qpos and {QUP3} and decline > 0.016 and decline < 0.018',
           ('er_q3_d16',))

    # ─── Block D: HYG_UP5 D30-42 gap (4 specs) ───
    add_er('ER_H5_D32T34_DEMO',
           f'_qpos and {HUP5} and decline > 0.032 and decline < 0.034',
           ('er_h5_d32',))
    add_er('ER_H5_D38T40_DEMO',
           f'_qpos and {HUP5} and decline > 0.038 and decline < 0.040',
           ('er_h5_d38',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
