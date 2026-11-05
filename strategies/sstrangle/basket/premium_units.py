"""Explicit, bounded QC LO premium-unit repair; never alter strikes or multipliers.

Cloud evidence: scale probe7cae79677e2f7cd693748515310c6aee and
cross-strike parity survey48e5d787db7b768703c7d77720c55a0c. Intraday
boundaries are independently checked before publishing a corrected baseline.
"""
from datetime import date

CL_CENTS_START=date(2015,12,21)
CL_CENTS_END=date(2015,12,24)


def premium_factor(option_root,underlying_root,source_session):
    if option_root=='LO' and underlying_root=='CL' and CL_CENTS_START<=source_session<=CL_CENTS_END:
        return .01
    return 1.
