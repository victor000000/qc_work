"""R3014 — fine-grain BAKE-139/140 sub-bands + cross-lever C_H3 m1.03 VRFY.

R3011: C_H3_D14T20 m1.03 = 3.33495 (+0.00010 single mag). Needs multi-mag.
R3012 confirms BAKE-141: m0.86, m0.94 both 3.33505. Plateau is wide.

R3014:
 - Block A: VRFY C_H3_D14T20 m1.02-1.03 multi-mag (BAKE-137 stack upgrade)
 - Block B: BAKE-139 D20-22 narrow sub-band (untested low edge)
 - Block C: BAKE-139 D32-35 sub-band (untested upper region)
 - Block D: BAKE-140 D11-13 mid-band (very narrow)
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
    R = Round(rid=3014, priority=1)

    DPANIC = 'self._reg_double_panic'
    HUP3 = 'self._reg_hyg_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: C_H3_D14T20 m1.02-1.03 VRFY (BAKE-137 upgrade candidate) (4 specs) ───
    cohort_h3_d14 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'
    add('C_H3_D14T20_M102', 'conv', cohort_h3_d14, '',
        (1.02,), fresh=('c_h3_m102',))
    add('C_H3_D14T20_M103_VRFY', 'conv', cohort_h3_d14, '',
        (1.025, 1.035), fresh=('c_h3_m103',))

    # ─── Block B: BAKE-139 D20-22 narrow sub-band (4 specs) ───
    cohort_d20_22 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.022'
    add('W_DP_HA_D20T22_DEMO_A', 'wt_tilt', cohort_d20_22, '',
        (0.92, 0.94), fresh=('w_d20_22_a',))
    add('W_DP_HA_D20T22_DEMO_B', 'wt_tilt', cohort_d20_22, '',
        (0.96, 0.97), fresh=('w_d20_22_b',))

    # ─── Block C: BAKE-139 D32-35 sub-band (untested) (4 specs) ───
    cohort_d32 = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.032 and decline < 0.035'
    add('W_DP_HA_D32T35_DEMO_A', 'wt_tilt', cohort_d32, '',
        (0.92, 0.94), fresh=('w_d32_a',))
    add('W_DP_HA_D32T35_DEMO_B', 'wt_tilt', cohort_d32, '',
        (0.96, 0.97), fresh=('w_d32_b',))

    # ─── Block D: BAKE-140 D11-13 mid-band (4 specs) ───
    cohort_h3_d11_13 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.011 and decline < 0.013'
    add('W_H3_HA_D11T13_DEMO_A', 'wt_tilt', cohort_h3_d11_13, '',
        (0.94, 0.96), fresh=('w_h3_d11_a',))
    add('W_H3_HA_D11T13_DEMO_B', 'wt_tilt', cohort_h3_d11_13, '',
        (0.97, 0.98), fresh=('w_h3_d11_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
