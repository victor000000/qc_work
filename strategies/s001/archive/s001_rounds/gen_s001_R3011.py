"""R3011 — BAKE-137/138 upgrade probes + sector-HA + VR regime exploration.

R3009 (post-bake NOOP=3.33485):
  C_DP_D20T40 PRE-bake +0.00031 → POST-bake FLAT (BAKE-139 absorbed lift)
  Sub-bands extending HA-compound: all NEG/cat (Rule 43 added)

R3011 fresh directions:
 - Block A: BAKE-138 (H5 W m1.05) stacked-mag upgrade probes
 - Block B: BAKE-137 (H3 C m1.05) stacked-mag upgrade probes
 - Block C: SECTOR × HA compound (S308, S102 with HACCEL)
 - Block D: VR (vxx_rising3) regime exploration — completely untouched
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
    R = Round(rid=3011, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    VR = 'self._reg_vxx_rising3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: BAKE-138 upgrade probes — H5 W stacked (4 specs) ───
    cohort_h5 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.020'
    add('W_H5_D14T20_UPGRADE_A', 'wt_tilt', cohort_h5, '',
        (1.04, 1.06), fresh=('w_h5_up_a',))
    add('W_H5_D14T20_UPGRADE_B', 'wt_tilt', cohort_h5, '',
        (1.07, 1.09), fresh=('w_h5_up_b',))

    # ─── Block B: BAKE-137 upgrade probes — H3 C stacked (4 specs) ───
    cohort_h3 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'
    # BAKE-137 mag=1.05. Probe stacked m1.03 = effective 1.082, m1.06 = 1.113
    add('C_H3_D14T20_UPGRADE_A', 'conv', cohort_h3, '',
        (1.03, 1.04), fresh=('c_h3_up_a',))
    add('C_H3_D14T20_UPGRADE_B', 'conv', cohort_h3, '',
        (1.06, 1.08), fresh=('c_h3_up_b',))

    # ─── Block C: SECTOR × rally compound NO HA (4 specs) ───
    cohort_s308_h3 = f'_qpos and _secc == 308 and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_S308_H3_D14T20_DEMO', 'wt_tilt', cohort_s308_h3, '',
        (0.88, 0.92), fresh=('w_s308_h3',))
    cohort_s311_h3 = f'_qpos and _secc == 311 and {HUP3} and decline > 0.010 and decline < 0.014'
    add('W_S311_H3_D10T14_DEMO', 'wt_tilt', cohort_s311_h3, '',
        (0.88, 0.92), fresh=('w_s311_h3',))

    # ─── Block D: Additional sector × rally compounds (4 specs) ───
    cohort_s102_h3 = f'_qpos and _secc == 102 and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_S102_H3_D14T20_DEMO', 'wt_tilt', cohort_s102_h3, '',
        (0.88, 0.92), fresh=('w_s102_h3',))
    cohort_s206_h3 = f'_qpos and _secc == 206 and {HUP3} and decline > 0.014 and decline < 0.020'
    add('W_S206_H3_D14T20_DEMO', 'wt_tilt', cohort_s206_h3, '',
        (0.88, 0.92), fresh=('w_s206_h3',))

    # ─── Block E: H3 narrow band (no HA) — explore .013<d<.015 cohort (4 specs) ───
    cohort_h3_narrow = f'_qpos and {HUP3} and decline > 0.013 and decline < 0.015'
    add('W_H3_D13T15_DEMO', 'wt_tilt', cohort_h3_narrow, '',
        (0.92, 0.95), fresh=('w_h3_n_d',))
    add('W_H3_D13T15_BOOST', 'wt_tilt', cohort_h3_narrow, '',
        (1.05, 1.08), fresh=('w_h3_n_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
