"""R3041 — qzero × fund-gate compounds + narrow band exploration.

Session plateau at NOOP=3.33598 verified. R3037-R3039 all 0 productive.

R3041 (18 specs) explores untouched fund-gate × qzero combos:
 - Block A: W × Z × DP × .020<d<.025 × FCF7 (untested compound)
 - Block B: W × Z × HUP3 × .014<d<.020 × NIM7
 - Block C: W × Z × Q3 × .014<d<.020 × INV8
 - Block D: W × P × HUP3 × narrow × _AOI3K (fund-gate variant)
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
    R = Round(rid=3041, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × Z × DP × .020<d<.025 × FCF7 (4 specs) ───
    cohort_z_dp_fcf = f'_qzero and {DPANIC} and decline > 0.020 and decline < 0.025 and _FCF7'
    add('W_Z_DP_FCF7_DEMO_A', 'wt_tilt', cohort_z_dp_fcf, '',
        (0.92, 0.94), fresh=('w_z_dp_fcf_a',))
    add('W_Z_DP_FCF7_DEMO_B', 'wt_tilt', cohort_z_dp_fcf, '',
        (0.96, 0.97), fresh=('w_z_dp_fcf_b',))

    # ─── Block B: W × Z × HUP3 × narrow × NIM7 (4 specs) ───
    cohort_z_h3_nim = f'_qzero and {HUP3} and decline > 0.014 and decline < 0.020 and _NIM7'
    add('W_Z_H3_NIM7_DEMO_A', 'wt_tilt', cohort_z_h3_nim, '',
        (0.92, 0.94), fresh=('w_z_h3_nim_a',))
    add('W_Z_H3_NIM7_DEMO_B', 'wt_tilt', cohort_z_h3_nim, '',
        (0.96, 0.97), fresh=('w_z_h3_nim_b',))

    # ─── Block C: W × Z × Q3 × narrow × INV8 (4 specs) ───
    cohort_z_q3_inv = f'_qzero and {QUP3} and decline > 0.014 and decline < 0.020 and _INV8'
    add('W_Z_Q3_INV8_DEMO_A', 'wt_tilt', cohort_z_q3_inv, '',
        (0.92, 0.94), fresh=('w_z_q3_inv_a',))
    add('W_Z_Q3_INV8_DEMO_B', 'wt_tilt', cohort_z_q3_inv, '',
        (0.96, 0.97), fresh=('w_z_q3_inv_b',))

    # ─── Block D: W × P × HUP3 × narrow × _AOI3K (4 specs) ───
    cohort_p_h3_aoi = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020 and _AOI3K'
    add('W_P_H3_AOI3K_DEMO_A', 'wt_tilt', cohort_p_h3_aoi, '',
        (0.92, 0.94), fresh=('w_p_h3_aoi_a',))
    add('W_P_H3_AOI3K_DEMO_B', 'wt_tilt', cohort_p_h3_aoi, '',
        (0.96, 0.97), fresh=('w_p_h3_aoi_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
