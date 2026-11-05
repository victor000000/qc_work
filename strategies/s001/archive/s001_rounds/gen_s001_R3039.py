"""R3039 — Diversify to untouched qstate parents (Z, N) + rare combos.

R3036 ALL specs at NOOP=3.33598 — DP narrow shallow + sector compounds = FLAT.

R3039 explores untouched qstate parents:
 - Block A: W × Z × DP × narrow (qzero on DP)
 - Block B: W × Z × HUP3 × narrow (qzero on HUP3)
 - Block C: W × Q × narrow (_qneg parent untouched)
 - Block D: W × P × HUP3 × HUP5 (intersect compound)
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
    R = Round(rid=3039, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × Z × DP × .017<d<.020 (qzero+DP untested) (4 specs) ───
    cohort_z_dp = f'_qzero and {DPANIC} and decline > 0.017 and decline < 0.020'
    add('W_Z_DP_D17T20_DEMO_A', 'wt_tilt', cohort_z_dp, '',
        (0.92, 0.94), fresh=('w_z_dp_a',))
    add('W_Z_DP_D17T20_DEMO_B', 'wt_tilt', cohort_z_dp, '',
        (0.96, 0.97), fresh=('w_z_dp_b',))

    # ─── Block B: W × Z × HUP3 × .014<d<.020 (qzero+H3 untested) (4 specs) ───
    cohort_z_h3 = f'_qzero and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_Z_H3_D14T20_DEMO_A', 'wt_tilt', cohort_z_h3, '',
        (0.92, 0.94), fresh=('w_z_h3_a',))
    add('W_Z_H3_D14T20_DEMO_B', 'wt_tilt', cohort_z_h3, '',
        (0.96, 0.97), fresh=('w_z_h3_b',))

    # ─── Block C: W × Q (qneg) × DPANIC narrow (untouched) (4 specs) ───
    cohort_qn_dp = f'_qneg and {DPANIC} and decline > 0.020 and decline < 0.030'
    add('W_QN_DP_D20T30_DEMO_A', 'wt_tilt', cohort_qn_dp, '',
        (0.92, 0.94), fresh=('w_qn_dp_a',))
    add('W_QN_DP_D20T30_DEMO_B', 'wt_tilt', cohort_qn_dp, '',
        (0.96, 0.97), fresh=('w_qn_dp_b',))

    # ─── Block D: W × P × HUP3 × HUP5 intersect (both rally regimes) (4 specs) ───
    cohort_p_h3_h5 = f'_qpos and {HUP3} and {HUP5} and decline > 0.014 and decline < 0.020'
    add('W_P_H3H5_D14T20_DEMO', 'wt_tilt', cohort_p_h3_h5, '',
        (0.92, 0.94), fresh=('w_p_h3h5_a',))
    add('W_P_H3H5_D14T20_BOOST', 'wt_tilt', cohort_p_h3_h5, '',
        (1.05, 1.07), fresh=('w_p_h3h5_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
