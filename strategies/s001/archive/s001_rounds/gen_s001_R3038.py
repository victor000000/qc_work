"""R3038 — DP × fund-gate compounds exploration.

R3035 NOOP=3.33598 verified BAKE-151 worked (+0.00021). Session at +0.01670.

R3038 explores DP × different fund-gates (untested combinations):
 - Block A: W × DP × .02<d<.05 × _NIM7 (net income margin)
 - Block B: W × DP × .02<d<.05 × _FCF7 (free cash flow)
 - Block C: W × DP × .02<d<.05 × _OCF6 (operating cash flow)
 - Block D: W × DP × .02<d<.05 × _AOI3K (asset/operating index)
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
    R = Round(rid=3038, priority=1)

    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × DP × .02<d<.05 × NIM7 (4 specs) ───
    cohort_dp_nim = f'_qpos and {DPANIC} and decline > 0.020 and decline < 0.050 and _NIM7'
    add('W_DP_NIM7_DEMO_A', 'wt_tilt', cohort_dp_nim, '',
        (0.90, 0.92), fresh=('w_dp_nim_a',))
    add('W_DP_NIM7_DEMO_B', 'wt_tilt', cohort_dp_nim, '',
        (0.94, 0.96), fresh=('w_dp_nim_b',))

    # ─── Block B: W × DP × .02<d<.05 × FCF7 (4 specs) ───
    cohort_dp_fcf = f'_qpos and {DPANIC} and decline > 0.020 and decline < 0.050 and _FCF7'
    add('W_DP_FCF7_DEMO_A', 'wt_tilt', cohort_dp_fcf, '',
        (0.90, 0.92), fresh=('w_dp_fcf_a',))
    add('W_DP_FCF7_DEMO_B', 'wt_tilt', cohort_dp_fcf, '',
        (0.94, 0.96), fresh=('w_dp_fcf_b',))

    # ─── Block C: W × DP × .02<d<.05 × OCF6 (4 specs) ───
    cohort_dp_ocf = f'_qpos and {DPANIC} and decline > 0.020 and decline < 0.050 and _OCF6'
    add('W_DP_OCF6_DEMO_A', 'wt_tilt', cohort_dp_ocf, '',
        (0.90, 0.92), fresh=('w_dp_ocf_a',))
    add('W_DP_OCF6_DEMO_B', 'wt_tilt', cohort_dp_ocf, '',
        (0.94, 0.96), fresh=('w_dp_ocf_b',))

    # ─── Block D: W × DP × .02<d<.05 × AOI3K (4 specs) ───
    cohort_dp_aoi = f'_qpos and {DPANIC} and decline > 0.020 and decline < 0.050 and _AOI3K'
    add('W_DP_AOI3K_DEMO_A', 'wt_tilt', cohort_dp_aoi, '',
        (0.90, 0.92), fresh=('w_dp_aoi_a',))
    add('W_DP_AOI3K_DEMO_B', 'wt_tilt', cohort_dp_aoi, '',
        (0.94, 0.96), fresh=('w_dp_aoi_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
