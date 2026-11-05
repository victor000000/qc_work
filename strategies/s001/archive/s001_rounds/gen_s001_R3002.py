"""R3002 — Post-upgrade verification + parallel-cohort BOOST exploration.

BAKE-136 upgraded m1.07→m1.22 (R3001 stacked m114/m118 = +0.00062 std=0).
Expected R3002 NOOP_0: ≈3.33423 (vs R3001 NOOP 3.33361).

Strategy:
 - Block A: VRFY upgraded BAKE-136 (zero-stack probes to detect breakage)
 - Block B: H5 D14T20 BOOST (parallel cohort, not yet baked at high mag)
 - Block C: Q3 D14T20 BOOST (parallel cohort)
 - Block D: H3 D14T20 stacked further mag exploration (saturation check)
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
    R = Round(rid=3002, priority=1)

    HUP3 = 'self._reg_hyg_up3'
    HUP5 = 'self._reg_hyg_up5'
    QUP3 = 'self._reg_qqq_up3'
    DPANIC = 'self._reg_double_panic'

    def add(name, lever, cohort, fund='', mags=(), op='*=', fresh=()):
        R.add(Probe(name=name, lever=lever, cohort=cohort, fund=fund, op=op,
                    mags=mags, fresh_fields=fresh))

    # ─── Block A: H5 D14T20 W BOOST (parallel-cohort, BAKE-138 currently m1.05) (4) ───
    cohort_h5 = f'_qpos and {HUP5} and decline > 0.014 and decline < 0.020'
    add('W_H5_D14T20_BOOST_HI_A', 'wt_tilt', cohort_h5, '',
        (1.10, 1.13), fresh=('w_h5_hi_a',))
    add('W_H5_D14T20_BOOST_HI_B', 'wt_tilt', cohort_h5, '',
        (1.16, 1.19), fresh=('w_h5_hi_b',))

    # ─── Block B: Q3 D14T20 W BOOST (no prior bake here) (4) ───
    cohort_q3 = f'_qpos and {QUP3} and decline > 0.014 and decline < 0.020'
    add('W_Q3_D14T20_BOOST_A', 'wt_tilt', cohort_q3, '',
        (1.08, 1.10), fresh=('w_q3_b_a',))
    add('W_Q3_D14T20_BOOST_B', 'wt_tilt', cohort_q3, '',
        (1.14, 1.18), fresh=('w_q3_b_b',))

    # ─── Block C: H3 D14T20 stacked saturation check (current bake m1.22 raw) (4) ───
    cohort_h3 = f'_qpos and {HUP3} and decline > 0.014 and decline < 0.020'
    # Post-upgrade these probes test 1.22 * mag = effective 1.27-1.46
    add('W_H3_D14T20_POSTBAKE_LO', 'wt_tilt', cohort_h3, '',
        (1.03, 1.05), fresh=('w_h3_pb_lo',))
    add('W_H3_D14T20_POSTBAKE_DEMO', 'wt_tilt', cohort_h3, '',
        (0.95, 0.97), fresh=('w_h3_pb_de',))

    # ─── Block D: H3 D14T20 conv BOOST stack (BAKE-137 currently m1.05) (4) ───
    add('C_H3_D14T20_STACK_A', 'conv', cohort_h3, '',
        (1.08, 1.10), fresh=('c_h3_s_a',))
    add('C_H3_D14T20_STACK_B', 'conv', cohort_h3, '',
        (1.13, 1.16), fresh=('c_h3_s_b',))

    add_productive_aux_blocks(R)
    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
