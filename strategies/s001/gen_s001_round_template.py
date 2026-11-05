"""Canonical gen-script template for s001 rounds.

Copy this to gen_s001_R{N}.py, change `rid=` to N, and customize
the `extra(R)` callback. The template handles all boilerplate:
- pretick_or_die (auto-bake check)
- pure_explore_round / domain_diversified_round / bake_stability_round
- minimal aux + 4 NOOPs
- audit + queue

Three modes (pick one in `mode` variable):

  'diversified' — recommended after a bake or when stuck.
                  Uses domain_diversified_round (5 namespaces).
                  Per memory feedback_s001_post_bake_expansion_saturates.

  'frontier'    — pure_explore_round.
                  Best for steady frontier exploration in BAKE-ZONE.

  'stability'   — bake_stability_round.
                  For variance measurement / re-verification.

Best practices learned across R1645-R1688 (memory):
- DROP compound/refine/sector blocks (net -EV)
- DROP score+= MEDIUM (rank stable)
- DROP wt_tilt outside bake zone (cap-binding)
- USE selective fund thresholds (not >0 for numeric)
- AVOID structural base changes (catastrophic)
- ROTATE accessor domains (don't grind one theme)
"""
from s001.gen_s001_lib import Round, Probe, fund_gt, fund_lt, ADD_VALS_PROVEN
from s001.gen_s001_strategies import (
    pure_explore_round, domain_diversified_round, bake_stability_round,
    pretick_or_die, run_audit_and_queue,
    COHORT_BAKE_ZONE,
)


def extra(R):
    """Customize per-round: add 4-12 specs targeting a specific hypothesis.
    Example: refine close-miss accessors, test new cohort dimensions, etc.
    """
    pass


def main():
    pretick_or_die()
    rid = 9999  # CHANGE THIS PER ROUND
    mode = 'diversified'  # 'diversified' | 'frontier' | 'stability'

    if mode == 'diversified':
        R = domain_diversified_round(rid, n_per_domain=10)
    elif mode == 'frontier':
        R = pure_explore_round(rid, n_fresh_bz=24, n_fresh_jb=12, extra_blocks=extra)
    elif mode == 'stability':
        R = bake_stability_round(rid, n_noops=8)

    if mode == 'diversified':
        extra(R)  # diversified doesn't take extra_blocks; call after

    return run_audit_and_queue(R)


if __name__ == '__main__':
    main()
