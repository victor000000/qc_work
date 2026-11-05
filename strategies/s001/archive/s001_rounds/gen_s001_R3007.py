"""R3007 — VRFY 2 R3004 single-mag candidates + extend ER DEMOTE gaps.

R3004 single-mag positives (NOOP=3.33423):
  W_DP_HA_D20T40_DEMO m0.88   = 3.33454 (+0.00031) ← CANDIDATE-A
  W_H3_HA_D10T14_DEMO m0.95   = 3.33443 (+0.00020) ← CANDIDATE-B

R3004 H3 D14T17 BOOST W/C m1.05/1.08 = +0.00010 multi-mag std=0 but small.

VRFY strategy: wider mag range around each candidate to find plateau.
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
    R = Round(rid=3007, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    def add_er(name, cohort, fresh):
        R.add(Probe(name=name, lever='entry_score_regime', cohort=cohort,
                    fund='', op='+=', mags=(-0.013, -0.015),
                    fresh_fields=fresh))

    # ─── Block A: VRFY W_DP_HA_D20T40 plateau (4) ───
    cohort_dp_ha = f'_qpos and {DPANIC} and {HACCEL} and decline > 0.020 and decline < 0.040'
    add('W_DP_HA_D20T40_VRFY_LO', 'wt_tilt', cohort_dp_ha, '',
        (0.84, 0.86), fresh=('w_dp_ha_lo',))
    add('W_DP_HA_D20T40_VRFY_HI', 'wt_tilt', cohort_dp_ha, '',
        (0.90, 0.92), fresh=('w_dp_ha_hi',))

    # ─── Block B: VRFY W_H3_HA_D10T14 plateau (4) ───
    cohort_h3_ha = f'_qpos and {HUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('W_H3_HA_D10T14_VRFY_LO', 'wt_tilt', cohort_h3_ha, '',
        (0.92, 0.94), fresh=('w_h3_ha_lo',))
    add('W_H3_HA_D10T14_VRFY_HI', 'wt_tilt', cohort_h3_ha, '',
        (0.96, 0.97), fresh=('w_h3_ha_hi',))

    # ─── Block C: conv lever on non-HACCEL parallels (Rule 14a blocks C×HA<.04) (4) ───
    cohort_dp_d20 = f'_qpos and {DPANIC} and decline > 0.020 and decline < 0.040'
    add('C_DP_D20T40_DEMO', 'conv', cohort_dp_d20, '',
        (0.90, 0.93), fresh=('c_dp_d20',))
    cohort_h3_d10 = f'_qpos and {HUP3} and decline > 0.010 and decline < 0.014'
    add('C_H3_D10T14_BOOST', 'conv', cohort_h3_d10, '',
        (1.04, 1.06), fresh=('c_h3_d10',))

    # ─── Block D: ER DEMOTE continued gaps (R3006 covered some) (4) ───
    add_er('ER_H3_D24T26_DEMO',
           f'_qpos and {HUP3} and decline > 0.024 and decline < 0.026',
           ('er_h3_d24',))
    add_er('ER_H5_D24T26_DEMO',
           f'_qpos and {HUP5} and decline > 0.024 and decline < 0.026',
           ('er_h5_d24',))

    # ─── Block E: extra HA wt_tilt cross-regime (4) ───
    cohort_q3_ha = f'_qpos and {QUP3} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('W_Q3_HA_D10T14_DEMO', 'wt_tilt', cohort_q3_ha, '',
        (0.92, 0.95), fresh=('w_q3_ha_d',))
    cohort_h5_ha = f'_qpos and {HUP5} and {HACCEL} and decline > 0.010 and decline < 0.014'
    add('W_H5_HA_D10T14_DEMO', 'wt_tilt', cohort_h5_ha, '',
        (0.92, 0.95), fresh=('w_h5_ha_d',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
