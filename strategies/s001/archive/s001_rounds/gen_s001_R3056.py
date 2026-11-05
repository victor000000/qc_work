"""R3056 — D25T30 peak-finding + parallel cohort exploration.

Pipeline state:
  - BAKE-152 confirmed +0.00031 (R3049/R3050 NOOP=3.33629)
  - BAKE-153 verification PENDING (R3052 NOOP still queued)
  - R3052 partial: W_P_H3_D25T30_DEEP m0.88 = 3.33670 (+0.00041 or +0.00021)
                   W_P_H3_D25T30_SHAL m0.98 = 3.33649 (+0.00020 or 0)
  - Mag-space picture (vs R3050 NOOP 3.33629):
      m0.88 = +0.00041 ← BIG (single-round)
      m0.90 = +0.00020 (R3050)
      m0.92/m0.94 = +0.00010 to +0.00020 (variance)
      m0.96/m0.97 = NOOP to +0.00010
      m0.98 = +0.00020 (anomalous spike, doesn't fit monotone)

Need: deeper-mag VRFY to find peak + parallel cohort to confirm signal class.

R3056 (16 specs):
 - Block A: W × P × H3 × D025T030 deeper VRFY (find m0.88 peak boundary)
 - Block B: W × P × H3 × D025T027 narrow sub-band
 - Block C: W × P × H3 × D028T030 narrow sub-band
 - Block D: W × P × H3 × D025T030 wider mag check (m0.85)
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
    R = Round(rid=3056, priority=1)

    HUP3 = 'self._reg_hyg_up3'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × H3 × D025T030 deeper VRFY (4 specs) ───
    cohort_a = f'_qpos and {HUP3} and decline > 0.025 and decline < 0.030'
    add('W_P_H3_D25T30_PEAK_A', 'wt_tilt', cohort_a, '',
        (0.84, 0.86), fresh=('w_h3_d25_pa',))
    add('W_P_H3_D25T30_PEAK_B', 'wt_tilt', cohort_a, '',
        (0.82, 0.87), fresh=('w_h3_d25_pb',))

    # ─── Block B: W × P × H3 × D025T027 narrow sub-band (4 specs) ───
    cohort_b = f'_qpos and {HUP3} and decline > 0.025 and decline < 0.027'
    add('W_P_H3_D25T27_DEMO_A', 'wt_tilt', cohort_b, '',
        (0.88, 0.90), fresh=('w_h3_d25t27_a',))
    add('W_P_H3_D25T27_DEMO_B', 'wt_tilt', cohort_b, '',
        (0.92, 0.94), fresh=('w_h3_d25t27_b',))

    # ─── Block C: W × P × H3 × D028T030 narrow sub-band (4 specs) ───
    cohort_c = f'_qpos and {HUP3} and decline > 0.028 and decline < 0.030'
    add('W_P_H3_D28T30_DEMO_A', 'wt_tilt', cohort_c, '',
        (0.88, 0.90), fresh=('w_h3_d28t30_a',))
    add('W_P_H3_D28T30_DEMO_B', 'wt_tilt', cohort_c, '',
        (0.92, 0.94), fresh=('w_h3_d28t30_b',))

    # ─── Block D: W × P × H3 × D025T030 wider mag check (4 specs) ───
    cohort_d = cohort_a
    add('W_P_H3_D25T30_MID_A', 'wt_tilt', cohort_d, '',
        (0.85, 0.88), fresh=('w_h3_d25_ma',))
    add('W_P_H3_D25T30_MID_B', 'wt_tilt', cohort_d, '',
        (0.89, 0.91), fresh=('w_h3_d25_mb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
