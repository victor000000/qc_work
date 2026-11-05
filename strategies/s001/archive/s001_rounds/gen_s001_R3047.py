"""R3047 — W-DEMOTE on UNTOUCHED qstate × regime combos.

Pending evidence (R3044 partial):
  W_H3_D20T25_DEMO m0.93 = +0.00031 (matches m0.94 exactly, std=0)
  W_H3_D20T25_DEMO m0.92 = -0.00072 (catastrophic neighbor — narrow sweet spot)
  S_Q3_D17T20_BOOST confirmed VARIANCE (m1.02 NOOP, m1.04/m1.05 -0.00124)
  S_Q3_D14T17_BOOST m1.02 = -0.00340 destructive

R3047 strategy: extend W-DEMOTE to UNTOUCHED qstate × regime combos.
  - N (qsneg) state has only 2 W bakes — H3/Q3 narrow declines UNTESTED
  - Z (qzero) on DP regime UNTESTED (Z bakes are H3/H5/Q3/D3 only)
  - P × H5 × D020-D025 gap (BAKE-149/150 at D014-D020, BAKE-131 at D04-D046)

R3047 (16 specs):
 - Block A: W × N × H3 × D014T020 (qsneg on H3 — parallel BAKE-136 cohort)
 - Block B: W × N × Q3 × D014T020 (qsneg on Q3 — parallel BAKE-151 cohort)
 - Block C: W × Z × DP × D014T020 (qzero on DP — Z×DP untested)
 - Block D: W × P × H5 × D020T025 (P×H5 gap band)
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
    R = Round(rid=3047, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × N × H3 × D014T020 (qsneg untested, parallel BAKE-136) (4 specs) ───
    cohort_n_h3 = f'_qsneg and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_N_H3_D14T20_DEMO_A', 'wt_tilt', cohort_n_h3, '',
        (0.92, 0.94), fresh=('w_n_h3_d14_a',))
    add('W_N_H3_D14T20_DEMO_B', 'wt_tilt', cohort_n_h3, '',
        (0.96, 0.97), fresh=('w_n_h3_d14_b',))

    # ─── Block B: W × N × Q3 × D014T020 (qsneg on Q3 untested) (4 specs) ───
    cohort_n_q3 = f'_qsneg and {QUP3} and decline > 0.014 and decline < 0.020'
    add('W_N_Q3_D14T20_DEMO_A', 'wt_tilt', cohort_n_q3, '',
        (0.92, 0.94), fresh=('w_n_q3_d14_a',))
    add('W_N_Q3_D14T20_DEMO_B', 'wt_tilt', cohort_n_q3, '',
        (0.96, 0.97), fresh=('w_n_q3_d14_b',))

    # ─── Block C: W × Z × DP × D014T020 (Z on DP untested) (4 specs) ───
    cohort_z_dp = f'_qzero and {DPANIC} and decline > 0.014 and decline < 0.020'
    add('W_Z_DP_D14T20_DEMO_A', 'wt_tilt', cohort_z_dp, '',
        (0.92, 0.94), fresh=('w_z_dp_d14_a',))
    add('W_Z_DP_D14T20_DEMO_B', 'wt_tilt', cohort_z_dp, '',
        (0.96, 0.97), fresh=('w_z_dp_d14_b',))

    # ─── Block D: W × P × H5 × D020T025 (gap band P×H5) (4 specs) ───
    cohort_p_h5 = f'_qpos and {HUP5} and decline > 0.020 and decline < 0.025'
    add('W_P_H5_D20T25_DEMO_A', 'wt_tilt', cohort_p_h5, '',
        (0.92, 0.94), fresh=('w_p_h5_d20_a',))
    add('W_P_H5_D20T25_DEMO_B', 'wt_tilt', cohort_p_h5, '',
        (0.96, 0.97), fresh=('w_p_h5_d20_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
