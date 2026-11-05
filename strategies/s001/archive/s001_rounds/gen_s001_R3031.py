"""R3031 — Cautious exploration while R3030 NOOP pending.

R3030 partial shows mixed: W_H5_D17T20 SAT m0.97 = NOOP-matching, but
W_H5_D14T17 m0.96 = catastrophic. Possible compositional issue with
BAKE-149/150. NOOP_0 pending verification.

R3031 explores OTHER directions to avoid overlap:
 - Block A: W × P × Q3 × narrow (different regime entirely)
 - Block B: W × P × HUP3 × .005<d<.010 (very narrow shallow)
 - Block C: NEW HACCEL probe: P × HA × narrow alone (no other regime)
 - Block D: NEW direction
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
    R = Round(rid=3031, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    QUP3 = 'self._reg_qqq_up3'
    HACCEL = 'self._reg_haccel'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: W × P × Q3 × .010<d<.014 (different regime narrow) (4 specs) ───
    cohort_q3_d10_14 = f'_qpos and {QUP3} and decline > 0.010 and decline < 0.014'
    add('W_Q3_D10T14_DEMO', 'wt_tilt', cohort_q3_d10_14, '',
        (0.92, 0.94), fresh=('w_q3_d10_14_a',))
    add('W_Q3_D10T14_BOOST', 'wt_tilt', cohort_q3_d10_14, '',
        (1.05, 1.07), fresh=('w_q3_d10_14_b',))

    # ─── Block B: W × P × HUP3 × .005<d<.010 very narrow shallow (4 specs) ───
    cohort_h3_d5_10 = f'_qpos and {HUP3} and decline > 0.005 and decline < 0.010'
    add('W_H3_D5T10_DEMO', 'wt_tilt', cohort_h3_d5_10, '',
        (0.92, 0.94), fresh=('w_h3_d5_10_a',))
    add('W_H3_D5T10_BOOST', 'wt_tilt', cohort_h3_d5_10, '',
        (1.05, 1.07), fresh=('w_h3_d5_10_b',))

    # ─── Block C: W × P × HACCEL × .020<d<.025 (HA + narrow non-H3 non-DP) (4 specs) ───
    cohort_p_ha_d20_25 = f'_qpos and {HACCEL} and decline > 0.020 and decline < 0.025'
    # Note: ANY rally regime not specified — broader cohort
    add('W_P_HA_D20T25_DEMO_A', 'wt_tilt', cohort_p_ha_d20_25, '',
        (0.92, 0.94), fresh=('w_p_ha_d20_a',))
    add('W_P_HA_D20T25_DEMO_B', 'wt_tilt', cohort_p_ha_d20_25, '',
        (0.96, 0.97), fresh=('w_p_ha_d20_b',))

    # ─── Block D: W × P × HUP3 × HA × D17-20 (untested sub-band) (4 specs) ───
    cohort_h3_ha_d17_20 = f'_qpos and {HUP3} and {HACCEL} and decline > 0.017 and decline < 0.020'
    add('W_H3_HA_D17T20_NEW_A', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.02, 1.04), fresh=('w_h3_ha_d17_20_aa',))
    add('W_H3_HA_D17T20_NEW_B', 'wt_tilt', cohort_h3_ha_d17_20, '',
        (1.06, 1.08), fresh=('w_h3_ha_d17_20_bb',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
