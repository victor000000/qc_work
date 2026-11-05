"""R3036 — Explore DP narrow declines + sector × Q3 compound.

R3032 NOOP=3.33577 verified. R3033/R3034 queued before BAKE-151 commit.
R3035 will be first post-BAKE-151 NOOP.

R3036:
 - Block A: W × DP × D10-12 (untouched DP narrow shallow)
 - Block B: W × DP × D12-14 (untouched)
 - Block C: SECTOR S308 × Q3 × D17-20 (BAKE-151 sector compound)
 - Block D: SECTOR S206 × Q3 × D17-20 (parallel sector)
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
    R = Round(rid=3036, priority=1)

    DPANIC = 'self._reg_double_panic'
    QUP3 = 'self._reg_qqq_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × DP × D10-12 (untouched narrow shallow) (4 specs) ───
    cohort_dp_d10_12 = f'_qpos and {DPANIC} and decline > 0.010 and decline < 0.012'
    add('W_DP_D10T12_DEMO_A', 'wt_tilt', cohort_dp_d10_12, '',
        (0.92, 0.94), fresh=('w_dp_d10_12_a',))
    add('W_DP_D10T12_DEMO_B', 'wt_tilt', cohort_dp_d10_12, '',
        (0.96, 0.97), fresh=('w_dp_d10_12_b',))

    # ─── Block B: W × DP × D12-14 (untouched) (4 specs) ───
    cohort_dp_d12_14 = f'_qpos and {DPANIC} and decline > 0.012 and decline < 0.014'
    add('W_DP_D12T14_DEMO_A', 'wt_tilt', cohort_dp_d12_14, '',
        (0.92, 0.94), fresh=('w_dp_d12_14_a',))
    add('W_DP_D12T14_DEMO_B', 'wt_tilt', cohort_dp_d12_14, '',
        (0.96, 0.97), fresh=('w_dp_d12_14_b',))

    # ─── Block C: SECTOR S308 × Q3 × D17-20 (BAKE-151 sector compound) (4 specs) ───
    cohort_s308_q3 = f'_qpos and _secc == 308 and {QUP3} and decline > 0.017 and decline < 0.020'
    add('W_S308_Q3_D17T20_DEMO_A', 'wt_tilt', cohort_s308_q3, '',
        (0.92, 0.94), fresh=('w_s308_q3_a',))
    add('W_S308_Q3_D17T20_DEMO_B', 'wt_tilt', cohort_s308_q3, '',
        (0.96, 0.97), fresh=('w_s308_q3_b',))

    # ─── Block D: SECTOR S206 × Q3 × D17-20 (parallel sector) (4 specs) ───
    cohort_s206_q3 = f'_qpos and _secc == 206 and {QUP3} and decline > 0.017 and decline < 0.020'
    add('W_S206_Q3_D17T20_DEMO_A', 'wt_tilt', cohort_s206_q3, '',
        (0.92, 0.94), fresh=('w_s206_q3_a',))
    add('W_S206_Q3_D17T20_DEMO_B', 'wt_tilt', cohort_s206_q3, '',
        (0.96, 0.97), fresh=('w_s206_q3_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
