#!/usr/bin/env python3
"""Queue a single s002 round to S002.duckdb.

Usage:
  python3 strategies/s002/queue_round.py 2513
  python3 strategies/s002/queue_round.py 2513 --cold 32 --vrfy 'spdw:tp=0.0495'
  python3 strategies/s002/queue_round.py 2513 --dry-run

Each round picks an axis-set rotation deterministically from round_num.
"""
from __future__ import annotations
import argparse
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from round_lib import (  # noqa: E402
    RoundBuilder, AXIS_SETS, axis_probes, cold_probes, cold_probes_directed,
    borderline_reverify_probes,
    untouched_lever_probes, UNTOUCHED_LEVERS_CURATED,
    breadth_first_sweep_probes, short_alias_value_probes,
    db_saturated_newax_combos, db_untouched_etfs, db_inert_etfs,
    db_recent_etfs, ROOT, DB_PATH,
    # Disabled-by-default but kept for occasional use:
    compound_2key_probes_v2, baked_untested_risk_probes,
    compound_risk_mgmt_probes,
)
from probe_history import (  # noqa: E402
    collect_recent_pair_stats, dead_pairs, summary as ph_summary,
)
from cohort_productivity import (  # noqa: E402
    cohort_stats, dead_cohort_pairs, expand_cohort_to_etf_pairs,
    best_axis_per_indicator,
)

DEFAULT_BASE = f'{ROOT}/strategies/s002/s002_20260628_ls_base.py'
DEFAULT_BO = 's002_20260628_ls_base'

# Registry of session-baked ETFs (and which lever was baked on each).
# Used by Pass 10 STACK probes to test OTHER levers on already-productive ETFs.
SESSION_BAKED_LEVERS: dict[str, list[str]] = {
    'ewc':  ['tp'],                  # BAKE-155
    'rwo':  ['tp'],                  # BAKE-156
    'vo':   ['tp'],                  # BAKE-157
    'ewg':  ['tp'],                  # BAKE-158
    'spdw': ['tp'],                  # BAKE-159
    'itot': ['wt','tp'],             # BAKE-160 wt + BAKE-298 tp 0.075→0.0675 (R3055 UTNT tp_shrink_90pct +0.00151 × 3 salts × std=0)
    'eww':  ['tp'],                  # BAKE-161
    'piz':  ['tp', 'atr_sl'],        # BAKE-162/164 (tp), BAKE-166 (atr_sl)
    'qld':  ['tp'],                  # BAKE-163
    'xlu':  ['bb_width_max'],        # BAKE-165
    'ewj':  ['atr_sl','wt','sf'],    # BAKE-167 atr_sl + BAKE-274 wt 0.055→0.0578 + BAKE-303 sf 0.95→0.9975 (R3060 SFX sf_grow_105pct +0.00196 × 3 salts × std=0)
    'spxs': ['atr_sl', 'vol_max'],   # BAKE-168 atr_sl, BAKE-170 vol_max (+0.00976)
    'kxi':  ['atr_sl', 'dd_haircut'], # BAKE-169 atr_sl, BAKE-171 dd_haircut (+0.00286)
    'pjp':  ['dd_haircut'],          # BAKE-172 (+0.00143; Pass 22 untouched-priority)
    'fgd':  ['dd_haircut'],          # BAKE-173 (+0.00833 — 5th largest bake!)
    'xly':  ['dd_haircut','wt'],     # BAKE-174 dd + BAKE-284+294 wt 0.055→0.0578→0.0636 (BAKE-294 R3050 WTX wt_grow_110pct +0.00173 × 3 salts × std=0 above +0.001)
    'ewm':  ['tp'],                   # BAKE-290 tp 0.05→0.0375 (R3036+R3037 UTNT multi-mag: tp_shrink_75 +0.00087, tp_grow_120 +0.00070, tp_grow_110 +0.00044 — multi-mag confirmation)
    'ijk':  ['tp'],                   # BAKE-291 tp 0.05→0.0375 (R3037+R3038 UTNT multi-mag: tp_shrink_70/75/grow_110 all +0.00033 × 6 salts × 2 ctx)
    'eww':  ['cf'],                   # BAKE-293 cf 0.92→0.966 (R3048 CFX cf_grow_105pct +0.00262 × 3 salts × std=0 above +0.001 hard; historical zeros pre-bake-evolution)
    'jkk':  ['atr_sl'],              # BAKE-175 (+0.00286; jkk atr_sl=1.5)
    'mdyg': ['dd_haircut'],          # BAKE-176 (cumulative-evidence: 14 salts × +0.00048)
    'kbe':  ['month_mask'],          # BAKE-177 (Pass 29 SHRTAX: +0.00357, 4 salts confirmed)
    'fvd':  ['atr_sl'],              # BAKE-178 (R2572 NEWAX: +0.00095, 3 salts; lower-threshold)
    'spxl': ['tp'],                  # BAKE-179/180/227 (R2593-94 tp 0.09→0.054 +0.00500; R2814 +5% iter to 0.0567 +0.00238) 2026-05-11
    'erx':  ['tp','x'],              # BAKE-181 tp + BAKE-318 x 0.80→0.76 (R3256 NEWLEV x_shrink_95pct +0.0140 × 3 specs std=0 — MASSIVE leveraged-energy x lever bake) 2026-05-10/16
    'ewq':  ['tp'],                  # BAKE-182 (R2600 COLD tp_shrink_60pct: tp 0.09→0.054, +0.00143) 2026-05-10
    'ewd':  ['tp'],                  # BAKE-317 tp 0.20→0.24 (R3255 UTNT tp_grow_120pct +0.00405 × 7 specs std=0 — biggest single-round signal in many rounds, validated UTNT 2-ETF cap finding cold-ETF gems) 2026-05-16
    'igf':  ['dd_haircut'],          # BAKE-319 dd_haircut ADD=0.3 (R3263+R3264 BFSW +0.00071 × 7 specs std=0 — global financial sector responsive to drawdown haircut) 2026-05-16
    'rsph':  ['e'],                   # BAKE-321 e 20→21 (R3263+R3265 NEWLEV e_grow_105pct + VRFY +0.00071 × 5 specs std=0 — equal-weight healthcare e lever) 2026-05-16
    'qqew': ['dd_haircut'],          # BAKE-322 dd_haircut ADD=0.4 (R3267-R3270 BFSW + VRFY: 5/15 lifts × +0.0295 each = avg +0.00738 across 12 specs / 3 rounds — probabilistic-lift signal captured via cross_round_cumulative pathway) 2026-05-16
    'vtv':  ['tp'],                  # BAKE-183 (R2602 DIV tp_shrink_60pct: tp 0.18→0.108, +0.00071) 2026-05-10
    'rpv':  ['tp'],                  # BAKE-184 (R2604 DV2 tp_grow_120pct: tp 0.075→0.09, +0.01976 — biggest!) 2026-05-10
    'kie':  ['tp'],                  # BAKE-185 (R2605 BORD tp_grow_120pct: tp 0.03→0.036, +0.00167) 2026-05-10
    'dba':  ['dd_haircut'],          # BAKE-186 (R2604 NEWAX dd_haircut=0.4: +0.00143) 2026-05-10
    # 'dfj': ['tp'],                # BAKE-187 REVERTED 2026-05-10 — caused R2608 NOOP drop 9.7274→9.5028
    'vox':  ['dd_haircut','wt'],     # BAKE-188 dd + BAKE-282 wt 0.055→0.0522 + BAKE-305 wt 0.0522→0.0548 (R3060 WTX wt_grow_105pct +0.00173 × 3 salts × std=0)
    'sds':  ['tp', 'wt'],            # BAKE-189 tp 0.12→0.18 (+0.00595) + BAKE-195 wt 0.035→0.0455 (WTGS +0.00571) 2026-05-10
    'iws':  ['tp'],                  # BAKE-190 (R2629 DV2 tp_grow_120pct: tp 0.033→0.0396, +0.00238) 2026-05-10
    'rspg':  ['tp'],                  # BAKE-191 (R2634 DIV tp_grow_150pct: tp 0.12→0.18, +0.01095) 2026-05-10
    'rgi':  ['tp'],                  # BAKE-192 tp 0.02→0.024 + BAKE-315 tp 0.024→0.0228 (R3219+R3220-R3222 +0.00024 × 12 specs std=0) 2026-05-10/16
    'rsps':  ['tp'],                  # BAKE-194 (R2639 DIV tp_grow_150pct: tp 0.05→0.075, +0.00095) 2026-05-10
    'fxr':  ['tp'],                  # BAKE-196 (R2669 DV2 tp_grow_120pct: tp 0.12→0.144, +0.00190) 2026-05-10
    # --- Session bakes BAKE-197+ (added 2026-05-10 to fix UTNT-misfire) ---
    'eem':  ['tp'],                  # BAKE iter (R2628 DIV tp_grow_120pct + iters)
    'xhb':  ['tp'],                  # BAKE (R2645 DV2)
    'ddm':  ['tp'],                  # BAKE (R2654)
    'ixp':  ['tp'],                  # BAKE (R2660)
    'don':  ['tp'],                  # BAKE-208/210 (R2725 BORD tp_shrink_70pct)
    'gsg':  ['tp','x'],              # BAKE-207 tp + BAKE-316 x 80→84.0 + BAKE-320 tp 0.0975→0.1024 (R3264 BTI tp_grow_105pct +0.00095 × 3 std=0 — cross-lever stacking on x-baked) 2026-05-10/16
    'igv':  ['tp','wt','wt2'],       # BAKE-212 tp + BAKE-288 wt → BAKE-307 wt 0.06→0.063 (R3074 +0.00246 × 3 + R3076 VRFY +0.00071 × 4 salts std=0) 2026-05-15
    'pey':  ['tp'],                  # BAKE-213 (R2730 UTNT tp_grow_120pct)
    'fxz':  ['tp'],                  # BAKE-214 (R2731 UTNT tp_grow_120pct)
    'ppa':  ['tp'],                  # BAKE-216 (R2750 FILL tp_grow_120pct: tp 0.03→0.036, +0.00286 × 5 salts) 2026-05-10
    'iwb':  ['tp'],                  # BAKE-217 (R2754-R2756 PROD tp_grow_180pct: tp 0.09→0.162, +0.00214 × 6 salts) 2026-05-10
    'ewg':  ['tp'],                  # BAKE-218 (R2763 BTI tp_grow_105pct: tp 0.135→0.142, +0.00071 × 3 salts) 2026-05-10
    'dfj':  ['tp'],                  # BAKE-219 (R2764-R2765 BTI tp_grow_105pct: tp 0.018→0.0189, +0.00286 × 4 salts) 2026-05-11
    'vis':  ['tp'],                  # BAKE-223 (R2808 UTNT tp_shrink_75pct: tp 0.072→0.054, +0.00357 × 3 salts) 2026-05-11
    'ech':  ['dd_haircut','sl'],     # BAKE-224 dd + BAKE-299 sl 0.025→0.0275 (R3056 STX sl_grow_110pct +0.00175 × 3 salts × std=0)
    'iwm':  ['tp'],                  # BAKE-225 (R2812 UTNT tp_grow_120pct: tp 0.12→0.144, +0.00833 × 3 salts) 2026-05-11
    'iwn':  ['tp'],                  # BAKE-338 tp 0.03→0.018 (R3688 UTNT tp_shrink_60pct +0.00095 × 3 + R3689 VRFY +0.00095 × 4 = 7 specs std=0 — small-cap value Russell 2000 deterministic lift) 2026-05-18
    'aok':  ['rg'],                  # BAKE-339 rg 55→57.75 (R3710 NEWLEV rg_grow_105pct +0.00238 × 2 + R3712 VRFY +0.00238 × 4 = 6 specs std=0 — Conservative Allocation, BIG +0.00238 lift on regime threshold) 2026-05-18
    'sdy':  ['tp'],                  # BAKE-340 tp 0.09→0.045 (R3744 UTNT tp_shrink_50pct +0.00095 × 3 + R3745 VRFY +0.00095 × 4 = 7 specs std=0 — SPDR S&P Dividend ETF, sharp tp halving productive) 2026-05-18
    'sphq': ['tp2'],                 # BAKE-341 tp 0.0375→0.034 (R3770 BTI tp_shrink_90pct +0.00167 × 3 + R3772 VRFY +0.00167 × 4 = 7 specs std=0 — Invesco S&P 500 Quality, BTI post-bake iter productive on BAKE-236 baked-tp) 2026-05-19
    # 'itot' tp2 — BAKE-342 tp 0.0709→0.064 (R3717+R3718 BTI tp_shrink_90pct +0.00048 × 5 + R3774 VRFY +0.00048 × 4 = 9 specs std=0 — iShares Core S&P Total US, 3rd tp iteration on baked-tp) 2026-05-19
    'tur':  ['tp'],                  # BAKE-226 (R2814 UTNT tp_grow_150pct: tp 0.12→0.18, +0.00762 × 3 salts) 2026-05-11
    'ijr':  ['month_mask'],          # BAKE-228 (R2816+R2817 BFSW month_mask=3583: +0.00071 × 6 salts × 2 rounds, cumulative-evidence) 2026-05-11
    'ezu':  ['tp'],                  # BAKE-229 (R2818 UTNT tp_grow_120pct: tp 0.12→0.144, +0.01238 × 3 salts — 2nd-largest historical) 2026-05-11
    'pnqi': ['tp'],                  # BAKE-230 (R2819 UTNT tp_grow_120pct: tp 0.15→0.18, +0.00381 × 6 salts) 2026-05-11
    'nlr':  ['month_mask'],          # BAKE-231 (R2821 BFSW month_mask=3583: +0.00262 × 3 salts) 2026-05-11
    'dsi':  ['atr_sl'],              # BAKE-232 (R2822 BFSW atr_sl=1.5: asl 4.0→1.5, +0.00143 × 3 salts) 2026-05-11
    'xme':  ['tp'],                  # BAKE-233 (R2823 UTNT tp_shrink_75pct: tp 0.09→0.0675, +0.00881 × 3 salts) 2026-05-11
    'ihf':  ['tp'],                  # BAKE-234 (R2824 UTNT tp_grow_120pct: tp 0.18→0.216, +0.00119 × 3 salts) 2026-05-11
    'vpl':  ['month_mask'],          # BAKE-235 (R2825 BFSW month_mask=2767: +0.00310 × 3 salts, first 2767-axis bake) 2026-05-11
    'sphq': ['tp'],                  # BAKE-236 (R2825 UTNT tp_shrink_75pct: tp 0.05→0.0375, +0.00143 × 3 salts) 2026-05-11
    'mdy':  ['tp'],                  # BAKE-237 (R2831 UTNT tp_shrink_75pct: tp 0.05→0.0375, +0.00239 × 3 salts) 2026-05-11
    'dth':  ['tp'],                  # BAKE-238 (R2831 UTNT tp_shrink_75pct: tp 0.04→0.030, +0.00096 × 3 salts zero-variance) 2026-05-11
    'dem':  ['tp'],                  # BAKE-239 (R2833+R2834 UTNT tp_shrink_75pct: tp 0.45→0.3375, +0.00095 × 6 salts × 2 rounds) 2026-05-11
    'vt':   ['tp','x'],              # BAKE-240 tp + BAKE-323 x 100→105 (R3272 VRFY x_grow_105pct +0.00143 × 4 specs std=0 — total world stock ETF) 2026-05-11/16
    'biv':  ['x'],                   # BAKE-324 x 40→42 (R3290+R3291 NEWLEV+VRFY +0.00024 × 7 specs std=0 — deterministic small-lift, first bond-ETF cross-lever bake) 2026-05-16
    'sptm': ['tp'],                  # BAKE-325 tp 0.15→0.12 (R3328 VRFY tp_shrink_80pct +0.00095 × 4 std=0 — SPDR S&P 1500 Composite tp shrink) 2026-05-17
    'ive':  ['ef'],                  # BAKE-328 ef 0.95→0.9025 (R3345 VRFY ef_shrink_95pct +0.00310 × 3 std=0 — iShares S&P 500 Value ef cross-lever clean bake) 2026-05-17
    'bwx':  ['cm'],                  # BAKE-329 cm 2→2.1 (R3350+R3351+R3352 NEWLEV+VRFY 11 specs all +0.00024 std=0 — global treasury bond cm deterministic) 2026-05-17
    'ixn':  ['atr_sl'],              # BAKE-330 atr_sl ADD=1.5 (R3415 BFSW +0.00095 × 3 + R3416 VRFY +0.00095 × 4 = 7 specs std=0 — broke 35-round drought, iShares Global Tech) 2026-05-17
    'cwi':  ['month_mask'],          # BAKE-331 month_mask ADD=3839 (R3418 BFSW +0.00167 × 3 + R3419 VRFY +0.00167 × 3 = 6 specs std=0 — MSCI ACWI ex-US, biggest deterministic lift) 2026-05-17
    'wood': ['month_mask','sl'],     # BAKE-332 month_mask ADD=1791 + BAKE-335 sl 0.032→0.0288 (R3495+R3503 STX sl_shrink_90pct +0.00095 × 3 std=0 — cross-lever bake on month_mask-baked ETF, 6th bake of session) 2026-05-17/18
    'rgi':  ['ub'],                  # BAKE-336 ub 1.30→1.365 (R3111+R3462+R3558 NEWLEV ub_grow_105pct 5 specs all positive +0.00024-+0.00286 — Invesco S&P 500 Equal Weight, broke 54-round drought) 2026-05-18
    'dln':  ['month_mask'],          # BAKE-333 month_mask ADD=3839 (R3425 BFSW +0.00405 × 3 + R3426 VRFY +0.00405 × 4 = 7 specs std=0 — WisdomTree LargeCap Dividend, BIGGEST lift of session +0.00405) 2026-05-17
    'tecl': ['dd_haircut'],          # BAKE-334 dd_haircut ADD=0.4 (R3437 BFSW +0.00119 × 3 + R3438 VRFY +0.00119 × 4 = 7 specs std=0 — 3x leveraged tech, surprising bake on lever where atr_sl was -0.472 catastrophic) 2026-05-17
    # 'ddm' wt already in line above — BAKE-326 wt 0.066→0.0693 (R3270-R3331 WTX wt_grow_105pct +0.00048 × 19 specs std=0 — 7th iter on baked-wt) 2026-05-17
    'iat':  ['atr_sl'],              # BAKE-241 (R2843 BFSW atr_sl=1.75: asl 2.5→1.75, +0.00238 × 2 salts — NEW axis productive!) 2026-05-11
    'iwc':  ['atr_sl'],              # BAKE-242 (R2845+R2846 BFSW atr_sl=1.5 add: +0.00047 × 6 salts × 2 rounds cumulative-evidence) 2026-05-11
    'efa':  ['month_mask','sl','cf'], # BAKE-243 mm + BAKE-301 sl + BAKE-304 cf 0.88→0.924 (R3060 CFX cf_grow_105pct +0.00196 × 3 salts × std=0)
    'qid':  ['month_mask'],          # BAKE-244 (R2850 BFSW month_mask=1023: +0.00548 × 3 salts — big bake!) 2026-05-11
    'ugl':  ['month_mask'],          # BAKE-245 (R2850+R2851 BFSW month_mask=3583: +0.00119 × 6 salts × 2 rounds) 2026-05-11
    'bsv':  ['month_mask'],          # BAKE-246 (R2851 BFSW month_mask=3583: +0.00143 × 3 salts) 2026-05-11
    'aor':  ['month_mask'],          # BAKE-248 (R2852 BFSW month_mask=3583: +0.00214 × 3 salts) 2026-05-11
    'ewl':  ['month_mask','tp'],     # BAKE-249 mm + BAKE-295 tp 0.075→0.0788 (R3050 UTNT tp_grow_105pct +0.00196 × 3 salts × std=0)
    'vb':   ['dd_haircut'],          # BAKE-250 (R2856-R2858 BFSW dd_haircut=0.3: +0.00429 × 5 salts × 3 rounds — new dd axis productive!) 2026-05-11
    'vdc':  ['month_mask'],          # BAKE-251 (R2861 BFSW mm=3839 skip-Sep: +0.00690 × 7 samples — NEW mask validated!) 2026-05-11
    # BAKE-252-255 REVERTED 2026-05-11: xle/rem/psi/iyg measured against stale pre-vdc NOOP (9.90762);
    # actual NOOP was 9.91452 (post-vdc); marginal lift = 0. They were NOOP-equivalent vs post-vdc base.
    'rwl':  ['month_mask'],          # BAKE-252 (R2866 BFSW mm=3839 skip-Sep: +0.00334 × 6 salts vs CURRENT post-vdc NOOP) 2026-05-11
    'kre':  ['tp'],                  # BAKE-253 (R2867 UTNT tp_grow_115pct: tp 0.10→0.115, +0.00381 × 3 salts vs CURRENT NOOP — new 115pct axis productive!) 2026-05-11
    'rspu':  ['tp'],                  # BAKE-254 (R2883 UTNT tp_shrink_80pct: tp 0.025→0.020, +0.00143 × 3 salts vs CURRENT NOOP) 2026-05-12
    'rspt':  ['tp'],                  # BAKE-255 (R2883+R2884 UTNT tp_grow_115pct: tp 0.18→0.207, +0.01000 × 6 salts × 2 rounds — BIGGEST single bake of session) 2026-05-12
    'vpu':  ['tp'],                  # BAKE-256 (R2883-R2884 UTNT tp_grow_115pct: tp 0.09→0.1035, +0.00167 × 3 salts) 2026-05-12
    'vti':  ['tp'],                  # BAKE-257 (R2902+R2904 UTNT+VRFY tp_shrink_80pct: tp 0.12→0.096, +0.00071 × 7 salts × 2 contexts × std=0 — 9-round dry break) 2026-05-12
    'fxn':  ['tp'],                  # BAKE-258 (R2905 UTNT tp_shrink_60pct: tp 0.065→0.039, +0.00143 × 3 salts × std=0 — single-round always-bake path) 2026-05-12
    'ewy':  ['dd_haircut','tp'],     # BAKE-259 dd + BAKE-297 tp 0.02→0.019 (R3054 UTNT tp_shrink_95pct +0.00131 × 3 salts × std=0)
    'qqq':  ['month_mask','cf','tp'], # BAKE-260 mm + BAKE-292 cf + BAKE-300 tp 0.05→0.0525 (R3058 UTNT tp_grow_105pct +0.00131 × 3 salts × std=0; flagship triple-lever!)
    'xlb':  ['tp'],                  # BAKE-261 (R2935 UTNT tp_grow_105pct: tp 0.35→0.3675, +0.00286 × 3 salts × std=0 — materials sector) 2026-05-13
    'iai':  ['atr_sl'],               # BAKE-262 (R2942+R2943 BFSW atr_sl=1.75: ADD, +0.00548 × 5 salts × std=0 — broker-dealers, biggest lift in 50+ rounds) 2026-05-13
    'wip':  ['month_mask'],           # BAKE-263 (R2945+R2946 BFSW month_mask=1023: ADD, +0.00310 × 6 salts × 2 contexts — intl treasury bond) 2026-05-13
    'edv':  ['month_mask'],           # BAKE-264 R2948 mm=1023 +0.00476 → REPLACED with BAKE-265 R2949 mm=1791 +0.00286 over 1023 = total +0.00762 (extended duration treasury) 2026-05-13
    'ige':  ['tp'],                   # BAKE-266 (R2953 UTNT tp_shrink_50pct: tp 0.033→0.0165, +0.00310 × 3 salts × std=0 — natural resources; validates new 50pct magnitude) 2026-05-13
    'ilf':  ['month_mask','wt','wt2'], # BAKE-267 mm + BAKE-281 wt 0.03→0.033 + BAKE-306 wt 0.033→0.0347 (R3063-R3065 VRFY +0.00125 × 11 salts) 2026-05-14
    'pbw':  ['month_mask'],           # BAKE-268 (R2965-R2968 BFSW month_mask=3583: ADD, +0.00071 × 16 salts × 4 contexts × std=0 — clean energy; was bake-classified for 4 rounds) 2026-05-14
    'fez':  ['atr_sl'],               # BAKE-269 (R2969 BFSW atr_sl=1.5: ADD, +0.00095 × 3 salts × std=0 — Eurozone, starved candidate from BFSW rotation fix) 2026-05-14
    'ewn':  ['tp'],                   # BAKE-270 tp 0.12→0.09 + BAKE-327 tp 0.09→0.0855 (R3336+R3342 BTI tp_shrink_95pct 3/6 lifts × +0.029 = avg +0.0146 — Netherlands cross-iter on baked-tp) 2026-05-14/17
    'ihf':  ['tp'],                   # BAKE-271 (R2975 UTNT tp_grow_105pct on baked-ihf: tp 0.216→0.2268, +0.00071 × 3 salts × std=0 — healthcare facilities, stacked on BAKE-234) 2026-05-14
    'igib': ['month_mask'],           # BAKE-272 (R2992-R2999 BFSW+VRFY month_mask_1023: ADD, +0.00024 × 14 salts × 4 contexts cumulative — broke 21-round dry spell) 2026-05-14
    'vo':   ['wt','tp'],              # BAKE-273+280+285 wt + BAKE-302 tp 0.12→0.108 (R3059 UTNT tp_shrink_90pct +0.00262 × 3 salts × std=0)
    'ewj':  ['wt'],                   # BAKE-274 (R3002+R3003+R3004 WTX+VRFY wt_grow_105pct: wt 0.055→0.0578, +0.000381 × 10 salts × 3 contexts × all-positive on grow dir) 2026-05-14
    'sds':  ['wt'],                   # BAKE-276 (R3007 WTX wt_grow_105pct: wt 0.0455→0.0478, +0.00119 × 3 salts × std=0 — single-round above-threshold) 2026-05-14
    'ddm':  ['cf','wt'],              # BAKE-275 cf + wt 0.035→0.045→0.0495→0.0545→0.060→0.066 (BAKE-296 R3054 wt_grow_110pct +0.00179 × 3 salts × std=0; 6th refinement)
    'iyc':  ['atr_sl'],               # BAKE-308 (R3094 BFSW atr_sl=2.0: +0.00196 × 3 salts × std=0 — first iyc bake; cross-axis recovery: iyc was UTNT_CATASTROPHIC on tp but productive on asl) 2026-05-15
    'igv':  ['tp','wt','wt2'],        # BAKE-309 (R3103+R3110+R3133 WTX wt 0.063→0.0662: cross-round 11/14 above NOOP_max via new cross_round_strong_signal pathway) 2026-05-15
    'xph':  ['month_mask'],           # BAKE-310 (R3152+R3153 BFSW month_mask 3087→1023: 8/8 specs at +0.00167 std=0 across 2 consecutive rounds — bimodal regime confirmation) 2026-05-15
    'ewc':  ['tp','e','wt','wt2'],     # BAKE-311 + BAKE-314 + BAKE-337 (R3486+R3588+R3599+R3609 WTX/VRFY wt_grow_105pct 0.0525→0.055125 +0.00024 × 9 specs std=0 across 4 NOOP regimes — cross-round cumulative pathway, rotation discovery) 2026-05-18
    'itot': ['wt','tp'],               # BAKE-312 (R3140-R3204 BTI tp 0.0675→0.0709 +0.00024 × 16 specs across 4 rounds std=0 — small but perfectly consistent deterministic improvement) 2026-05-16
    'vv':   ['month_mask'],            # BAKE-313 (R3202+R3208 BFSW month_mask=1023 +0.00024 × 7 specs std=0 across 2 NOOP regimes — first bake via deterministic-small-lift pathway) 2026-05-16
}

# Catastrophic ETFs to permanently exclude from BFSW/UTNT fresh-ETF blocks.
# These are leveraged/inverse/commodity ETFs that consistently produce <-0.20
# lift when probed naively. Adding dd_haircut to them destabilizes calibration.
BFSW_CATASTROPHIC = {
    'tna', 'sh', 'uso', 'iau',     # R2809/R2810: dd_haircut -0.23 to -0.25 (3+ salts)
    'ijr', 'dbb', 'ieo',           # R2810 audit: dd_haircut also catastrophic
    'ixc', 'prfz', 'vaw',          # R2814/R2817: atr_sl -0.24 to -0.48
    'vnq', 'ewz', 'xlv',           # R2818/R2820: atr_sl -0.26 to -0.87
    'iwv',                         # R2817: month_mask -0.47
    'vig', 'kre', 'ihe', 'iyt',    # R2820: tf_t=0.98 catastrophic (axis since removed)
    'vbk',                         # R2824: month_mask=2767 -0.69
    'dvy',                         # R2828: month_mask=2767 -0.46
    'iyr', 'shm',                  # R2833: iyr -1.28 on ALL month_mask values; shm -0.84 atr_sl_2.0
    'xlk', 'iwo', 'rez', 'fxu',    # R2834: xlk on ALL 4 axes; iwo atr_sl_2.0; rez month_mask; fxu atr_sl_1.5
    'iyk', 'agq', 'vht',           # R2841: iyk month_mask_2047 -0.21; agq atr_sl_2.5 -0.29; vht month_mask_3071 -0.38
    'xes', 'fta',                  # R2845: catastrophic on ALL atr_sl values (xes -1.82, fta -0.46)
    # R2907-R2908 30m review 2026-05-12: recency-window unlock exposed new BFSW catastrophic
    'fas', 'spyv', 'rsp',          # R2907: atr_sl -0.018 to -0.030 across 3 values
    'xle', 'iyg',                  # R2908: month_mask/dd_haircut -0.013 to -0.018 across 4-5 values
    'slv',                         # R2909: 12 specs at -0.026 (silver ETF, high volatility)
    'ibb',                         # R2920: atr_sl_1.5 -0.092 × 3, atr_sl_1.75 -0.030 × 3 (biotech)
    'ewp',                         # R2930: BFSW -0.234 × 6 specs (Spain country ETF, high vol)
    'fxo',                         # R2930: also in BFSW (already in UTNT_CATASTROPHIC)
    'fbt',                         # R2941: BFSW atr_sl_1.75 -0.24 × 4 specs (biotech)
    'mgk',                         # R2977-R2979: UTNT+BFSW destructive -0.008 to -0.01 across 18 specs (Vanguard mega cap growth)
    # R2991 30m review 2026-05-14: BFSW month_mask catastrophic
    'gdx',                         # gold miners: -0.20126 × 3 on month_mask_3583 (MASSIVE)
    'voe',                         # mid-cap value: -0.013 to -0.022 across month_mask_1023/3583/3839 (also in UTNT_CATASTROPHIC)
    'rwr', 'icf',                  # REIT pair: -0.00857 × 6 on month_mask_3839 (also icf in UTNT_CATASTROPHIC)
    # R3249 30m review 2026-05-16: 100% destructive last 30 rounds (≥5 specs / 0 pos)
    'qtec',                        # 6/6 destructive on atr_sl_1.75
    'iwm',                         # 6/6 destructive (small-cap Russell 2000)
    'tfi',                         # 6/6 destructive on atr_sl 1.75/2.0 (muni bonds)
    'slyv',                        # 6/6 destructive (SPDR small-cap value)
    'iym',                         # 5/8 destructive (basic materials)
    'dgs',                         # 5/8 destructive (WisdomTree emerging small-cap dividend)
    # R3697 30m audit 2026-05-18: 3 different lever classes all catastrophic
    'fxi',                         # mm_3839 -0.88, dd_haircut_0.3 -0.47, atr_sl_1.5 -1.61 (China FTSE 50 — structurally fragile to any BFSW perturbation)
    # R3798 30m audit 2026-05-19: dbc dd_haircut_0_3 -0.46 × 3 RE-tested
    'dbc',                         # dd_haircut_0_3 -0.46 × 2 incidents (R3595 + R3798). catastrophic_cells parser splits multi-underscore values wrong; perma-ban via BFSW_CATASTROPHIC
    # R3806 30m audit 2026-05-19: BFSW 12.5% cata rate over 200 rounds. ETFs with multi-incident structural fragility
    'epi',                         # 2 incidents: mm_3839 -0.235 × 3 (R3650), atr_sl_1_75 -0.251 × 3 (R3776) — India ETF
    'efv',                         # 2 incidents: mm_1023 -0.238 × 3 (R3758), atr_sl_2_0 -0.054 × 3 (R3791) — MSCI EAFE value
}


def parse_change(spec: str) -> tuple[str, dict]:
    """'spdw:tp=0.0495,sl=0.025' -> ('spdw', {'tp': 0.0495, 'sl': 0.025})."""
    etf, kvs = spec.split(':', 1)
    out: dict = {}
    for kv in kvs.split(','):
        k, v = kv.split('=')
        v = v.strip()
        try:
            out[k.strip()] = float(v) if '.' in v else int(v)
        except ValueError:
            out[k.strip()] = v.strip('"\'')
    return etf.strip(), out


def _salt_index_bias_warning(R: int) -> None:
    """Flag candidates whose lifts cluster on rv1/rv2 only — salt-state
    artifacts not real signals. 30m R3377 audit: rv1=7 rv2=5 rv3=1 rv4=0
    across 13 rounds = clear rv1 bias. Auto-VRFY of these wastes budget."""
    try:
        import qc_storage as _sq, re as _re
        c = _sq.connect(DB_PATH)
        from_b = f'gen_afql3b_div{R - 8}'
        nv = {b: v for b, v in c.execute(f"SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL AND batch >= '{from_b}' GROUP BY batch").fetchall()}
        agg = {}
        for b, n_, cm in c.execute(f"SELECT batch, name, car_mdd FROM experiments WHERE batch >= '{from_b}' AND car_mdd IS NOT NULL AND name NOT LIKE '%NOOP%' AND name NOT LIKE '%VBAKE%'").fetchall():
            v = nv.get(b)
            if v is None: continue
            if cm - v < 0.015: continue
            m = _re.match(r's002_[A-Z]+_([a-z0-9]+)_([a-z0-9_]+?)(?:_rv(\d+))?_gen', n_)
            if not m: continue
            rv = int(m.group(3)) if m.group(3) else 0
            key = (m.group(1), m.group(2))
            agg.setdefault(key, set()).add(rv)
        biased = [(k, sorted(rvs)) for k, rvs in agg.items() if len(rvs) >= 2 and max(rvs) <= 2]
        if biased:
            print(f'  ⚠️ salt-bias suspects ({len(biased)}, rv≤2 only):',
                  ', '.join(f'{k[0]}/{k[1][:15]}' for k, _ in biased[:4]))
        c.close()
    except Exception:
        pass


def _deep_think_audit(R: int) -> None:
    """User-mandated pre-queue audit. Codified 2026-05-17 after user
    repeated "every round, think deep before queue new backtests" 6+ times.
    Prints (a) R{N-1} signals + drift flag, (b) cross-round survivors,
    (c) block-yield trend. No-op on errors — never blocks queue."""
    try:
        import qc_storage as _sq, re as _re
        c = _sq.connect(DB_PATH)
        prev = R - 1
        prev_b = f'gen_afql3b_div{prev}'
        nv_row = c.execute(f"SELECT AVG(car_mdd) FROM experiments WHERE batch='{prev_b}' AND name LIKE '%NOOP%'").fetchone()
        nv = nv_row[0] if nv_row else None
        nvals = [r[0] for r in c.execute(f"SELECT car_mdd FROM experiments WHERE batch='{prev_b}' AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL").fetchall()]
        # 2026-05-17 cross-round drift: with --noop=1, within-round detection
        # impossible. Compare R{N-1} NOOP vs last 3 prior NOOPs.
        prior_nvs = []
        for back in range(2, 5):
            row = c.execute(f"SELECT AVG(car_mdd) FROM experiments WHERE batch='gen_afql3b_div{R-back}' AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL").fetchone()
            if row and row[0]: prior_nvs.append(row[0])
        drift_within = (max(nvals) - min(nvals) > 0.005) if len(nvals) >= 2 else False
        drift_cross = bool(prior_nvs and nv is not None and abs(nv - sum(prior_nvs)/len(prior_nvs)) > 0.005)
        drift = drift_within or drift_cross
        print(f'\n=== DEEP-THINK pre-R{R} ===')
        if nv is None:
            print(f'  R{prev}: no NOOP yet (in-flight or missing)')
        else:
            flag = ' DRIFT' if drift else ''
            print(f'  R{prev} NOOP={nv:.4f}{flag} ({len(nvals)} samples)')
            pos = c.execute(f"SELECT COUNT(*) FROM experiments WHERE batch='{prev_b}' AND car_mdd IS NOT NULL AND name NOT LIKE '%NOOP%' AND car_mdd > {nv}+0.0005").fetchone()[0]
            neg = c.execute(f"SELECT COUNT(*) FROM experiments WHERE batch='{prev_b}' AND car_mdd IS NOT NULL AND name NOT LIKE '%NOOP%' AND car_mdd < {nv}-0.0005").fetchone()[0]
            zero = c.execute(f"SELECT COUNT(*) FROM experiments WHERE batch='{prev_b}' AND car_mdd IS NOT NULL AND name NOT LIKE '%NOOP%' AND ABS(car_mdd-{nv})<=0.0005").fetchone()[0]
            inflight = c.execute(f"SELECT COUNT(*) FROM backtest_queue WHERE batch='{prev_b}' AND status NOT IN ('done','failed')").fetchone()[0]
            print(f'  R{prev}: pos={pos} neg={neg} zero={zero} in-flight={inflight}')
        # Cross-round survivors
        from_batch = f'gen_afql3b_div{R - 8}'
        nm = {b: v for b, v in c.execute(f"SELECT batch, AVG(car_mdd) FROM experiments WHERE name LIKE '%NOOP%' AND car_mdd IS NOT NULL AND batch >= '{from_batch}' GROUP BY batch").fetchall()}
        rows = c.execute(f"SELECT batch, name, car_mdd FROM experiments WHERE batch >= '{from_batch}' AND car_mdd IS NOT NULL AND name NOT LIKE '%NOOP%' AND name NOT LIKE '%VBAKE%'").fetchall()
        agg = {}
        for b, n_, cm in rows:
            v = nm.get(b)
            if v is None: continue
            d = cm - v
            m = _re.match(r's002_[A-Z]+_([a-z0-9]+)_([a-z0-9_]+?)(?:_rv\d+)?_gen', n_)
            if not m: continue
            agg.setdefault((m.group(1), m.group(2)), []).append((b, d))
        surv = []
        for k, v in agg.items():
            rounds = len(set(b for b, _ in v))
            negs = [d for _, d in v if d < -0.0005]
            lifts = [d for _, d in v if d > 0.001]
            if negs or rounds < 2 or not lifts: continue
            t = sum(d for _, d in v)
            if t < 0.003: continue
            surv.append((k, t, len(v), rounds, len(lifts)))
        surv.sort(key=lambda x: -x[1])
        if surv:
            print(f'  survivors ({len(surv)}):', end='')
            for k, t, n_, r_, p in surv[:4]:
                print(f' {k[0]}/{k[1][:15]} +{t:.4f}({p}/{n_})', end='')
            print()
        else:
            print('  survivors: 0 (pipeline dry)')
        # Block yield last 8
        yields = []
        for prefix in ('BFSW', 'BTI', 'UTNT', 'NEWLEV', 'WTX', 'STX', 'CFX', 'SFX'):
            row = c.execute(f"""SELECT COUNT(*), SUM(CASE WHEN car_mdd > (SELECT AVG(car_mdd) FROM experiments x2 WHERE x2.batch=x.batch AND name LIKE '%NOOP%')+0.001 THEN 1 ELSE 0 END) FROM experiments x WHERE batch >= '{from_batch}' AND car_mdd IS NOT NULL AND name LIKE 's002_{prefix}_%'""").fetchone()
            if row[0]: yields.append((prefix, row[0], row[1] or 0, (row[1] or 0) * 100 / row[0]))
        if yields:
            print('  block yields:', ' '.join(f'{p}={r:.0f}%(n{n})' for p, n, _, r in yields))

        # 2026-05-18 BAKE-337 ewc was found manually by scanning sub-threshold
        # positives across NOOP regimes. Auto-surface similar patterns: ≥4
        # deterministic positive specs in current-regime NOOP (±0.005), excluding
        # already-baked (etf, axis_class) pairs.
        from collections import defaultdict
        baked_axes = set()
        for etf, levers in SESSION_BAKED_LEVERS.items():
            for lvr in levers:
                baked_axes.add((etf, lvr))
        cur_nv_lo = (nv or 10.007) - 0.005
        cur_nv_hi = (nv or 10.007) + 0.005
        cand_groups = defaultdict(list)
        scan_from = f'gen_afql3b_div{R - 200}'
        for n_, cm, b in c.execute(f"""SELECT name, car_mdd, batch FROM experiments
            WHERE batch >= '{scan_from}' AND car_mdd IS NOT NULL
            AND name NOT LIKE '%NOOP%'"""):
            bnv = nm.get(b) or c.execute(f"SELECT AVG(car_mdd) FROM experiments WHERE batch='{b}' AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL").fetchone()[0]
            if bnv is None or not (cur_nv_lo <= bnv <= cur_nv_hi): continue
            d = cm - bnv
            m = _re.match(r's002_[A-Z]+_([a-z0-9]+)_([a-z]+)_(?:grow|shrink)_\d+pct_rv\d', n_)
            if not m: continue
            etf, lever = m.group(1), m.group(2)
            if (etf, lever) in baked_axes: continue
            cand_groups[(etf, lever, m.group(0).split('_rv')[0].split(f'{lever}_')[-1])].append(d)
        true_cands = []
        for (etf, lever, val), lifts in cand_groups.items():
            if len(lifts) < 4: continue
            if min(lifts) <= 0.00015: continue
            if max(lifts) > 0.001: continue
            if (max(lifts) - min(lifts)) > 0.0002: continue
            true_cands.append((etf, lever, val, len(lifts), sum(lifts)/len(lifts)))
        true_cands.sort(key=lambda x: -x[4])
        if true_cands:
            print(f'  🔥 BAKE CANDIDATES (cumulative+ scan, current-regime): {len(true_cands)}')
            for etf, lvr, val, n_, avg in true_cands[:5]:
                print(f'     {etf} {lvr} {val}  n={n_}  avg=+{avg:.5f} — queue --vrfy {etf}:{lvr}=...')

        c.close()
        _salt_index_bias_warning(R)
        print('=' * 40)
    except Exception as e:
        print(f'  (deep-think audit skipped: {e})')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    ap.add_argument('round_num', type=int)
    ap.add_argument('--base', default=DEFAULT_BASE)
    ap.add_argument('--based-on', default=DEFAULT_BO)
    ap.add_argument('--target', type=int, default=16)
    ap.add_argument('--noop', type=int, default=1)  # Reduced 2026-05-17: 4→2→1. User directive. With 1 NOOP, within-round drift detection lost — fall back to cross-round NOOP comparison. Saves 1 more spec/round (15 probes vs 14).
    ap.add_argument('--force', action='store_true', help='Override idempotency guard — add specs even if R{N} already has queue entries')
    ap.add_argument('--cold', type=int, default=0,  # was 24 — 0% hit rate post-rebalance audit 2026-05-10
                    help='Number of cold-ETF probe slots (3 salts each)')
    ap.add_argument('--vrfy', action='append', default=[],
                    help='4-salt verify slot. Format: etf:k=v[,k=v]. Repeatable.')
    ap.add_argument('--axis-set', type=int, default=None,
                    help='Override AXIS_SETS index (default = round_num %% len)')
    ap.add_argument('--auto-vrfy-from', type=str, default='PREV',  # 'PREV' resolves to round_num-1
                    help='Round id (e.g. 2512) — pull sub-threshold VRFY suggestions from its audit')
    ap.add_argument('--stack-probes', type=int, default=0,
                    help='Number of STACK probes — alternate-lever probes on baked ETFs '
                         '(Pass 10). Disabled by default after R2528 evidence: '
                         '66/66 STACK probes hit zero or negative; piz+e_widen catastrophic '
                         'at -1.49. Use only for targeted compound exploration.')
    ap.add_argument('--c2-probes', type=int, default=0,
                    help='Compound 2-key probes (Pass 7). Disabled by default '
                         'after R2522/R2523/R2528 evidence: 51/51 zero or negative; '
                         'C2wttp catastrophic on 4 ETFs.')
    ap.add_argument('--levax-probes', type=int, default=0,
                    help='LEVAX (Pass 19): DISABLED. R2542 evidence: 99 specs '
                         'across 11 leveraged ETFs at 4 atr_sl values produced 0 '
                         'positive lifts; many negative (sso -0.015, tlt -0.004). '
                         'spxs +0.01690 was unique, not a class signal. '
                         'atr_sl bakes are highly ETF-specific.')
    ap.add_argument('--bakerx-probes', type=int, default=0,
                    help='BAKERX (Pass 16): DISABLED. R2536 evidence: 22/22 '
                         'BAKERX probes zero or NEGATIVE; qld atr_sl=2.5 '
                         'catastrophic at -2.04 across 3 salts; eww/ewc/itot/'
                         'rwo all -0.22 to -0.25. piz+atr_sl was the exception, '
                         'not the rule. RISK_MGMT_LEVERS taxonomy invalid.')
    ap.add_argument('--burx-probes', type=int, default=0,
                    help='BURX (Pass 25): DISABLED. After 126 specs across 6+ '
                         'rounds: 0 positive, 116 near-zero, 10 small-negative. '
                         'Untested risk_mgmt levers on baked ETFs are genuinely '
                         'unproductive — same conclusion as BAKERX, just slower '
                         'to confirm. The few 2-bake ETFs (spxs, kxi, piz) were '
                         'discovered organically, not via systematic crossing.')
    ap.add_argument('--crmx-probes', type=int, default=0,
                    help='CRMX (Pass 26): RE-DISABLED 2026-05-11 — even with month_mask+atr_sl combos, '
                         'R2830 showed 0 pos / 15 cat / 45 (33% catastrophic). Compound 2-key amplifies. '
                         'across 18 fresh ETFs; 9 catastrophic regressions '
                         '(uwm -0.663, pbw -0.353, gdx -0.340). Compound 2-key '
                         'risk_mgmt on fresh ETFs same failure as BAKERX. '
                         'Singletons stack productively only when ETF independently '
                         'responds to each lever — cannot predict from naive cross.')
    ap.add_argument('--shrtax-probes', type=int, default=0,
                    help='SHRTAX (Pass 29/32): DISABLED. R2571 evidence: '
                         'expanded SHRTAX produced 0 positive across 86 specs; '
                         'sma_p value changes catastrophic (acwx -0.72, acwi '
                         '-0.24×5+). Pass 29 found kbe (1 bake) but most other '
                         'short-alias value changes broadly toxic. Re-enable '
                         'only for targeted single-ETF tests via --vrfy.')
    ap.add_argument('--bfsw-probes', type=int, default=2,
                    help='BFSW (Pass 27): breadth-first sweep — 1 probe per '
                         'untouched ETF. Reduced 2026-05-17: 4 → 2 to fit '
                         'target=16 budget (2 probes × 3 salts = 6 specs).')
    ap.add_argument('--newax-probes', type=int, default=0,  # was 30 — 0% hit rate post-rebalance, all axes (dd_haircut/atr_sl/mom_min) confirmed dead
                    help='Number of NEWAX probes — DISABLED 2026-05-10. dd_haircut '
                         '(570 specs, 0 bakes), atr_sl/mom_min similarly dead. Set to '
                         '0 to free budget for higher-EV blocks (UTNT/BTI).')
    ap.add_argument('--no-dead-filter', action='store_true',
                    help='Disable dead-pair exclusion (probe everything)')
    ap.add_argument('--dead-filter-rounds', type=int, default=5,
                    help='How many recent rounds to scan for dead-pair detection')
    ap.add_argument('--baked-etfs', action='append', default=[],
                    help='ETFs that were just baked — exclude their stale observations')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)

    R = args.round_num
    batch = f'gen_afql3b_div{R}'

    # 2026-05-17 USER MANDATE (repeated 6+ times): "every round, think deep
    # before queue new backtests". Codified as tool-enforced pre-queue audit
    # so the deliberation always happens, regardless of caller discipline.
    _deep_think_audit(R)

    # 2026-05-17 idempotency guard: if R{N} already has specs in the queue,
    # ABORT to prevent double-queueing (which has happened 2-3 times today).
    # User can pass --force to override. Saves manual cleanup after duplicate
    # calls from cron + manual fires.
    try:
        import qc_storage as _sq
        _c = _sq.connect(DB_PATH)
        _existing = _c.execute(f"SELECT COUNT(*) FROM backtest_queue WHERE batch='{batch}'").fetchone()[0]
        _c.close()
        if _existing > 0 and not getattr(args, 'force', False):
            print(f'ABORT: R{R} already has {_existing} specs in queue. Use --force to add more.')
            return 1
    except Exception as e:
        print(f'(idempotency check skipped: {e})')

    # Dead-pair exclusion (probe-history filter) + cohort-level exclusion
    excluded_pairs: set = set()
    if not args.no_dead_filter:
        baked = set(args.baked_etfs)
        stats = collect_recent_pair_stats(DB_PATH,
                                          n_batches=args.dead_filter_rounds,
                                          recent_baked_etfs=baked)
        s = ph_summary(stats)
        excluded_pairs = set(s['excluded_set'])
        print(f'probe-history filter: scanned {s["n_pairs"]} pairs from last '
              f'{args.dead_filter_rounds} rounds → '
              f'{s["dead"]} DEAD + {s["toxic"]} TOXIC excluded; '
              f'{s["alive"]} ALIVE / {s["borderline"]} borderline')
        if baked:
            print(f'  excluding {len(baked)} just-baked ETFs from history: {sorted(baked)}')

        # Cohort-level filter: if (indicator, lever) class has 6+ observations
        # all near zero, exclude every (etf, lever) in that cohort
        cstats = cohort_stats(DB_PATH, args.base,
                              n_batches=args.dead_filter_rounds + 3,
                              baked_etfs=baked)
        dead_cohorts = dead_cohort_pairs(cstats, min_obs=6)
        if dead_cohorts:
            cohort_etf_pairs = expand_cohort_to_etf_pairs(dead_cohorts, args.base)
            new_exclusions = cohort_etf_pairs - excluded_pairs
            excluded_pairs |= cohort_etf_pairs
            print(f'cohort-level filter: {len(dead_cohorts)} dead (ind,lever) cohorts → '
                  f'{len(cohort_etf_pairs)} (etf,lever) pairs ({len(new_exclusions)} new)')
            for ind, lever in sorted(dead_cohorts)[:5]:
                print(f'  dead cohort: ({ind}, {lever})')

    rb = RoundBuilder(R, args.base, batch, args.based_on, target=args.target,
                      excluded_pairs=excluded_pairs)

    rb.add_noop(args.noop)

    # Auto-VRFY from previous round's audit (sub-threshold confirmed lifts)
    vrfy_specs = list(args.vrfy)
    if args.auto_vrfy_from:
        from audit_round import audit, changes_from_hypothesis
        if args.auto_vrfy_from == 'PREV':
            args.auto_vrfy_from = str(args.round_num - 1)
        # 2026-05-14: scan last 3 rounds (not just prev). Auto-VRFY used to miss
        # signals from rounds N-2 and N-3 (ige_wt R2997-R2999, vo_wt R3000 case).
        prev_round = args.auto_vrfy_from
        all_vrfys = []
        all_bakes = []
        prev_batch = None
        # 2026-05-16: widened look-back 3→8 rounds. Server throughput shifted
        # round-generation faster than spec-completion (R3219 cmf/gld specs
        # completed 1h AFTER R3220 was queued, so audit at R3220-time saw <3
        # salts and dropped them; R3221-R3224 audits looked at R3219 too late
        # in window, signal lost). 8-round window catches late-landing specs.
        for back in range(8):
            try:
                rd = int(prev_round) - back
            except ValueError:
                rd = args.round_num - 1 - back
            batch_n = f'gen_afql3b_div{rd}'
            if back == 0:
                prev_batch = batch_n
            try:
                _rep = audit(batch_n, threshold=0.0005, min_salts=3)
                all_vrfys.extend(_rep.get('vrfys', []))
                all_bakes.extend(_rep.get('bakes', []))
            except Exception:
                pass
        # Dedup by (etf, hyp)
        seen = set()
        rep = {'vrfys': [], 'bakes': []}
        for c in all_vrfys:
            k = (c['etf'], c['hyp'])
            if k not in seen:
                seen.add(k); rep['vrfys'].append(c)
        for c in all_bakes:
            k = (c['etf'], c['hyp'])
            if k not in seen:
                seen.add(k); rep['bakes'].append(c)
        # 2026-05-12 anti-waste: count how many times each (etf, change) has been
        # VRFY-pulled. If ≥3 prior pulls with same sub-threshold lift, stop pulling.
        import qc_storage as _sql3
        _db = _sql3.connect(DB_PATH)
        _prior_vrfy_count = {}
        for (nm,) in _db.execute(
                "SELECT name FROM experiments WHERE name LIKE 's002_VRFY_%'").fetchall():
            # Format: s002_VRFY_<etf>_<lever><val>_verify_rvN_<batch>
            import re as _re
            m = _re.match(r's002_VRFY_([a-z]{2,5})_', nm)
            if m:
                key = m.group(1)
                _prior_vrfy_count[key] = _prior_vrfy_count.get(key, 0) + 1
        # 2026-05-15 anti-stale-VRFY: skip (etf, hyp) pairs that were ALREADY
        # VRFY'd in prev round AND didn't confirm. The 3-round look-back
        # re-queues sub-thresh candidates from R{N-2}/R{N-3} even after
        # R{N-1} verified them as variance. R3113 case: rgi/dsi/ivv each
        # ran 4 VRFY salts in R3113 and dropped to ≤0 lift, but R3114
        # re-queued them → 12 wasted specs.
        _failed_vrfy_keys = set()  # set of (etf, canonical_lever_value_str)
        import re as _re
        # Walk back the SAME 8 rounds as the audit look-back (widened
        # 2026-05-16 from 3). A candidate from R{N-2} that got VRFY'd in
        # R{N-1} and failed should be skipped even though R{N-2} audit
        # still surfaces it.
        for _back in range(8):
            try:
                _bn = f'gen_afql3b_div{int(prev_round) - _back}'
            except (ValueError, TypeError):
                _bn = f'gen_afql3b_div{args.round_num - 1 - _back}'
            try:
                _noop_row = _db.execute(
                    f"SELECT AVG(car_mdd) FROM experiments WHERE batch='{_bn}' "
                    f"AND name LIKE 's002_VBAKE_NOOP%'").fetchone()
                _noop_avg = _noop_row[0] if _noop_row and _noop_row[0] else None
                if _noop_avg is None:
                    continue
                # 2026-05-17 30m audit: skip DRIFT rounds when building
                # failed_vrfy_keys. jkh was permanently blacklisted from
                # R3369 drift round. Detect via within-round NOOP range OR
                # cross-round NOOP comparison (after --noop=1 reduction).
                _nvs = [r[0] for r in _db.execute(
                    f"SELECT car_mdd FROM experiments WHERE batch='{_bn}' "
                    f"AND name LIKE 's002_VBAKE_NOOP%' AND car_mdd IS NOT NULL"
                ).fetchall()]
                _drift_w = len(_nvs) >= 2 and (max(_nvs) - min(_nvs)) > 0.005
                _drift_x = False
                if _noop_avg is not None:
                    _prior = []
                    import re as _re2
                    _m = _re2.search(r'div(\d+)', _bn)
                    if _m:
                        _r = int(_m.group(1))
                        for _b2 in range(2, 5):
                            _row2 = _db.execute(f"SELECT AVG(car_mdd) FROM experiments WHERE batch='gen_afql3b_div{_r - _b2}' AND name LIKE 's002_VBAKE_NOOP%' AND car_mdd IS NOT NULL").fetchone()
                            if _row2 and _row2[0]: _prior.append(_row2[0])
                        if _prior and abs(_noop_avg - sum(_prior)/len(_prior)) > 0.005:
                            _drift_x = True
                if _drift_w or _drift_x:
                    continue  # drift round — VRFY signals unreliable
                _vrfy_rows = _db.execute(
                    f"SELECT name, AVG(car_mdd) FROM experiments WHERE batch='{_bn}' "
                    f"AND name LIKE 's002_VRFY_%' GROUP BY substr(name,1,instr(name,'_rv')-1)"
                ).fetchall()
                for nm, avg_cm in _vrfy_rows:
                    if avg_cm is None:
                        continue
                    if (avg_cm - _noop_avg) >= 0.0002:
                        continue  # confirmed — let it through
                    m = _re.match(r's002_VRFY_([a-z0-9]{2,6})_(.+?)_verify_rv', nm)
                    if m:
                        _failed_vrfy_keys.add((m.group(1), m.group(2)))
            except Exception:
                pass
        _db.close()
        vrfy_skip_count = 0
        vrfy_failed_skip = 0
        for c in rep.get('vrfys', []):
            ch = changes_from_hypothesis(c['hyp'])
            if not ch:
                continue
            # 2026-05-16: skip if lever already baked on this ETF — VRFY against
            # post-bake base would test same value, wasting 4 specs/round.
            # (R3267 ryh:e=21 was already BAKE-321 but auto-VRFY kept queueing.)
            _lever = next(iter(ch.keys()))
            if _lever in SESSION_BAKED_LEVERS.get(c['etf'], []):
                vrfy_skip_count += 1
                continue
            # 2026-05-16: skip if entire lever class is dead — R3277 was about
            # to VRFY dem:cd=19/17 × 8 specs despite cd_grow_1/cd_shrink_1 in
            # dead_axis_values (100% NOOP across 3+ ETFs). If BOTH grow and
            # shrink directions of a lever are dead, the lever is fully inert.
            _dead_levers = {ax_pref.rsplit('_', 1)[0] if '_' in ax_pref else ax_pref
                            for ax_pref, _ in rb._dead_axis_values}
            # Build per-lever direction count
            _dead_dirs = {}  # lever -> count of dead directions
            for ax_pref, _val in rb._dead_axis_values:
                _parts = ax_pref.rsplit('_', 1)
                if len(_parts) == 2:
                    _lever_only = _parts[0]
                    _dead_dirs[_lever_only] = _dead_dirs.get(_lever_only, 0) + 1
            if _lever in _dead_dirs and _dead_dirs[_lever] >= 2:
                vrfy_skip_count += 1
                continue
            # 2026-05-15 anti-stale-VRFY: if this (etf, change) already failed
            # verification in PREV round (lift < +0.0002), skip — already verified
            # as variance. Otherwise the 3-round audit look-back re-queues
            # candidates that R{N-1} just disproved.
            _chs_label = '_'.join(f'{k}{v}' for k, v in ch.items()).replace('.', '')
            if (c['etf'], _chs_label) in _failed_vrfy_keys:
                vrfy_failed_skip += 1
                continue
            # Skip if this ETF has been VRFY'd >= 60 specs already (5 rounds × 4 salts × 3 mags)
            # 2026-05-15 exception: bypass cap only on CLEAN strong signals
            # (lift ≥ +0.001 AND std < 0.0005). Salt-confound candidates with
            # high avg but high std (xly/vug pattern) should NOT bypass — they
            # waste budget verifying salt-luck instead of real signal.
            fresh_clean = c.get('lift', 0) >= 0.001 and c.get('std', 1) < 0.0005
            if _prior_vrfy_count.get(c['etf'], 0) >= 60 and not fresh_clean:
                vrfy_skip_count += 1
                continue
            chs = ','.join(f'{k}={v}' for k, v in ch.items())
            vrfy_specs.append(f"{c['etf']}:{chs}")
        # 2026-05-12: Also carry forward BAKE candidates as VRFY for cross-round
        # confirmation (false-bake protocol per memory). +0.0005 single-round needs
        # 2nd context before being applied to base.
        # 2026-05-15: bakes_for_vrfy now also respects _failed_vrfy_keys to prevent
        # already-disproven candidates from re-cycling indefinitely (ewu R3134→R3142
        # case: 23 specs across 7 rounds despite R3134 showing -0.00065).
        bakes_for_vrfy = []
        bakes_failed_skip = 0
        for c in rep.get('bakes', []):
            ch = changes_from_hypothesis(c['hyp'])
            if not ch:
                continue
            # 2026-05-16: skip if lever already baked (same as vrfys path).
            _lever = next(iter(ch.keys()))
            if _lever in SESSION_BAKED_LEVERS.get(c['etf'], []):
                continue
            _chs_label = '_'.join(f'{k}{v}' for k, v in ch.items()).replace('.', '')
            if (c['etf'], _chs_label) in _failed_vrfy_keys:
                bakes_failed_skip += 1
                continue
            chs = ','.join(f'{k}={v}' for k, v in ch.items())
            spec = f"{c['etf']}:{chs}"
            if spec not in vrfy_specs:
                vrfy_specs.append(spec)
                bakes_for_vrfy.append(c)
        print(f'auto-VRFY from {prev_batch}: {len(rep.get("vrfys", []))} sub-thresh + '
              f'{len(bakes_for_vrfy)} bake-confirms carried forward '
              f'(skipped {vrfy_skip_count} over-verified, {vrfy_failed_skip+bakes_failed_skip} prev-failed)')

        # 2026-05-15 NEW: cross-round strong-signal candidates (≥6 specs, ≥70%
        # above NOOP_max, avg ≥+0.001). Designed to break "no-bakes" droughts
        # where single-round std<0.001 misses signals like igv wt_grow_105pct
        # (6/6 above NOOP across R3103+R3110 but std=0.00123 per round).
        try:
            from audit_round import cross_round_strong_signal
            # Two-tier:
            # Tier 1 STRONG: ≥70% above NOOP, ≥6 specs (high confidence)
            # Tier 2 BORDERLINE: ≥60% above NOOP, ≥5 specs (catches fxn-style cases)
            strong = cross_round_strong_signal(n_rounds=30, min_above_noop_rate=0.6,
                                                min_specs=5, min_avg_lift=0.001)
            n_strong_carried = 0
            for sig in strong:
                ch = changes_from_hypothesis(sig['hyp'])
                if not ch:
                    continue
                # 2026-05-16: skip if ETF already baked on that lever (the
                # cross-round signal would now produce 0 lift vs NEW baseline).
                # E.g., post-BAKE-312, itot tp=0.0709 historical +0.00024 is
                # now baked-in; re-probing wastes specs.
                lever_changed = next(iter(ch.keys()))
                if lever_changed in SESSION_BAKED_LEVERS.get(sig['etf'], []):
                    continue
                _chs_label = '_'.join(f'{k}{v}' for k, v in ch.items()).replace('.', '')
                if (sig['etf'], _chs_label) in _failed_vrfy_keys:
                    continue
                chs = ','.join(f'{k}={v}' for k, v in ch.items())
                spec_str = f"{sig['etf']}:{chs}"
                if spec_str not in vrfy_specs:
                    vrfy_specs.append(spec_str)
                    n_strong_carried += 1
            if n_strong_carried:
                print(f'cross-round strong-signal VRFY: {n_strong_carried} candidates (≥60% above NOOP, ≥5 specs, avg ≥+0.001)')
        except Exception as e:
            print(f'cross-round strong-signal: skipped ({e})')

        # 2026-05-17: Tier-3 CUMULATIVE pathway — catches probabilistic-lift
        # signals (e.g., ige WTX wt_grow_105pct at 2/6 lifts × +0.029) that
        # fall below strong-signal's 60% rate threshold but still show
        # avg ≥+0.001 with no negative salts. Capped at 2 candidates/round.
        try:
            from audit_round import cross_round_cumulative
            cum = cross_round_cumulative(n_rounds=8, cum_threshold=0.001,
                                          min_total_salts=6)
            n_cum_carried = 0
            for sig in cum:
                if n_cum_carried >= 2:
                    break
                if sig.get('avg_lift', 0) < 0.001:
                    continue
                ch = changes_from_hypothesis(sig['hyp'])
                if not ch:
                    continue
                lever_changed = next(iter(ch.keys()))
                if lever_changed in SESSION_BAKED_LEVERS.get(sig['etf'], []):
                    continue
                _chs_label = '_'.join(f'{k}{v}' for k, v in ch.items()).replace('.', '')
                if (sig['etf'], _chs_label) in _failed_vrfy_keys:
                    continue
                chs = ','.join(f'{k}={v}' for k, v in ch.items())
                spec_str = f"{sig['etf']}:{chs}"
                if spec_str not in vrfy_specs:
                    vrfy_specs.append(spec_str)
                    n_cum_carried += 1
            if n_cum_carried:
                print(f'cross-round CUMULATIVE VRFY: {n_cum_carried} probabilistic candidates (avg ≥+0.001, no neg salts)')
        except Exception as e:
            print(f'cross-round cumulative: skipped ({e})')

    # Verify slots first (priority 1, 4 salts)
    for spec in vrfy_specs:
        etf, ch = parse_change(spec)
        label = '_'.join(f'{k}{v}' for k, v in ch.items()).replace('.', '')
        rb.add_verify(etf, ch, label, prio=1)

    # COLD ETF expansion — directed by cohort productivity:
    # for each cold ETF, probe the lever its indicator-cohort has historically
    # responded to. Falls back to round-rotated axis for unknown cohorts.
    # 2026-05-09: removed sl_add/wt_lower/ef_norm — all confirmed productive-class-dead
    # (0 positive lifts at +0.0007 across ≥190 historical samples each).
    # Rotation now cycles through productive axes only.
    COLD_AXIS_ROTATION = ('tp_grow', 'tp_shrink', 'tp_pivot_low', 'tp_grow')
    fallback_axis = COLD_AXIS_ROTATION[R % len(COLD_AXIS_ROTATION)]
    if args.cold > 0:
        recent = db_recent_etfs(5)
        if not args.no_dead_filter:
            best_lever = best_axis_per_indicator(cstats, min_lift=0.0005)
            cold = cold_probes_directed(rb.base, recent, best_lever,
                                        max_probes=args.cold,
                                        fallback_axis=fallback_axis)
            print(f'COLD directed: {len(best_lever)} indicators with known '
                  f'productive lever; fallback axis: {fallback_axis}')
        else:
            cold = cold_probes(rb.base, recent, axes=(fallback_axis,),
                               max_probes=args.cold)
            print(f'COLD axis (uniform): {fallback_axis}')
        rb.add_probes(cold, salts=rb.salts[:3], prio=2, prefix='COLD',
                      max_probes=args.cold // 3)

    # LEVAX probes — Pass 19: atr_sl × un-baked leveraged ETFs.
    # spxs (3x inv S&P) + atr_sl=3.0 = +0.01690 — leveraged volatility
    # benefits disproportionately from ATR-based stops. 11 un-baked leveraged
    # ETFs in universe; this targets them with high priority.
    if args.levax_probes > 0:
        baked_etfs_set = set(SESSION_BAKED_LEVERS.keys())
        levax = leveraged_atr_sl_probes(rb.base, baked_etfs_set,
                                         max_probes=args.levax_probes,
                                         excluded_pairs=excluded_pairs)
        rb.add_probes(levax, salts=rb.salts[:3], prio=2, prefix='LEVAX',
                      max_probes=args.levax_probes)
        print(f'LEVAX probes: {len(levax)} atr_sl × leveraged ETFs')

    # SHRTAX probes — Pass 29: short-alias value changes on ETFs using them.
    # Most "dormant" levers (bb_width_max, rsi_gate, adx_min, etc.) are actually
    # active on 24-127 ETFs via short aliases (bw/rg/am). Probe value changes
    # on the existing-user ETFs.
    if args.shrtax_probes > 0:
        baked_etfs_set = set(SESSION_BAKED_LEVERS.keys())
        shrtax = short_alias_value_probes(rb.base,
                                          max_probes=args.shrtax_probes,
                                          excluded_pairs=excluded_pairs,
                                          baked_etfs=baked_etfs_set)
        rb.add_probes(shrtax, salts=rb.salts[:3], prio=2, prefix='SHRTAX',
                      max_probes=args.shrtax_probes)
        print(f'SHRTAX probes: {len(shrtax)} short-alias value changes')

    # BFSW probes — Pass 27: multi-axis breadth-first sweep.
    # Historical bake distribution: tp=34, dd_haircut=8, atr_sl=6 active.
    # Base-coverage: dd_haircut=3%, atr_sl=2%, vol_max=0% — vast probe surface.
    # Run ALL 3 axes per round (split allocation) instead of rotation —
    # dd_haircut saturating at ~12 fresh ETFs after R2812 audit.
    if args.bfsw_probes > 0:
        baked_etfs_set = set(SESSION_BAKED_LEVERS.keys())
        previously_probed = db_untouched_etfs()
        inert = db_inert_etfs() | BFSW_CATASTROPHIC
        # 2026-05-15 NOTE: "break-stuck" cross-axis experiment (commit 1d553743)
        # produced 0 productive results across ~15 cat-ETF tests but generated
        # ~15 catastrophic discoveries (shm -0.85, vde -0.29, dbb -0.26, etc.).
        # Net waste: ~45 specs over 6 rounds. Reverted to strict cat-ETF
        # exclusion. xph BAKE-310 was actually a fresh-ETF discovery, not
        # cross-axis recovery.
        from round_lib import db_recent_bfsw_etf_axes, db_bfsw_silent_axes
        recent_axes = db_recent_bfsw_etf_axes(n_batches=10)
        bfsw_silent = db_bfsw_silent_axes()  # 2026-05-15: aggressive filter
        print(f'BFSW: blocking {len(recent_axes)} recent (etf,axis) pairs '
              f'+ {len(bfsw_silent)} silent (etf,axis_class) pairs')
        # 2026-05-17 30m R3397 audit: 22 catastrophic (-0.1+) discoveries in
        # 26 rounds, cluster on atr_sl_1.75/2.0 (mln/tecl/vde) and dd_haircut_0.3
        # (dbc -0.46). Reordered priority to safer/historically-productive first.
        # 2026-05-19 R3809 30m audit: per-axis 300-round yield. ALL BFSW axes
        # 0% pos in last 300 rounds. Pruned high-waste axes:
        #   month_mask_3839: 71% waste (36 neg/6 cata over 59 specs) — REMOVED
        #   dd_haircut_0_3:  67% waste (15 cata) — REMOVED
        #   dd_haircut_0_4:  60% waste — REMOVED
        #   atr_sl_1_75:     60% waste (12 cata) — REMOVED
        #   month_mask_3583: 56% waste (15 neg/27 specs) — REMOVED
        # Kept axes have ≤46% waste; some still source of historical bakes
        # (atr_sl_1_5 BAKE-330 ixn, mm_1023 qid BAKE-244, mm_1791 alt patterns).
        BFSW_AXES = [
            ('atr_sl', 1.5),       # 46% waste, but BAKE-330 ixn productive
            ('month_mask', 1023),  # 43% waste, qid BAKE-244 productive
            ('month_mask', 1791),  # 33% waste, alt productive pattern
            ('dd_haircut', 0.5),   # 20% waste, lowest of dd_haircut family
            ('atr_sl', 2.0),       # 35% waste, mid-risk
        ]
        # REMOVED 2026-05-11:
        # - vol_max — requires partner vol_p key (R2813: 87/87 NOOP)
        # - tf_t=0.98 — R2820 net-destructive (4 catastrophic, 0 bakes)
        # - atr_sl=3.0 — R2821-R2823 dead (0/61 pos rate)
        per_axis = max(1, args.bfsw_probes // len(BFSW_AXES))
        bfsw_all: list = []
        for axis_idx, axis in enumerate(BFSW_AXES):
            # 2026-05-13: rotate fresh pool by round_num + axis_idx so all 8 axes
            # explore different ETF subsets and later-alphabetical ETFs get tested
            offset = R * 11 + axis_idx * 7
            bfsw = breadth_first_sweep_probes(rb.base, previously_probed,
                                               baked_etfs_set,
                                               lever_value=axis,
                                               max_probes=per_axis,
                                               excluded_pairs=excluded_pairs,
                                               inert_etfs=inert,
                                               round_offset=offset,
                                               noop_sigs=rb._noop_sigs,
                                               destructive_cells=rb._destructive_cells,
                                               dead_pairs=rb._dead_pairs,
                                               recent_bfsw_axes=recent_axes | bfsw_silent,
                                               inert_etf_axes=rb._inert_etf_axes,
                                               noop_etf_axes=rb._noop_etf_axes)
            bfsw_all.extend(bfsw)
            print(f'BFSW {axis[0]}={axis[1]}: {len(bfsw)} probes')
        rb.add_probes(bfsw_all, salts=rb.salts[:3], prio=2, prefix='BFSW',
                      max_probes=args.bfsw_probes, max_specs=12)
        print(f'BFSW total: {len(bfsw_all)} fresh-ETF probes across {len(BFSW_AXES)} axes')

    # CRMX probes — Pass 26: compound 2-key risk_mgmt on FRESH untouched ETFs.
    # Test if risk-layer stacking produces bigger bakes when applied to ETFs
    # that haven't responded to single-lever probes (or haven't been probed).
    if args.crmx_probes > 0:
        baked_etfs_set = set(SESSION_BAKED_LEVERS.keys())
        previously_probed = db_untouched_etfs()
        crmx = compound_risk_mgmt_probes(rb.base, previously_probed,
                                          baked_etfs_set,
                                          max_probes=args.crmx_probes,
                                          excluded_pairs=excluded_pairs,
                                          inert_etfs=db_inert_etfs() | BFSW_CATASTROPHIC)
        rb.add_probes(crmx, salts=rb.salts[:3], prio=2, prefix='CRMX',
                      max_probes=args.crmx_probes)
        print(f'CRMX probes: {len(crmx)} compound 2-key risk_mgmt × fresh ETFs')

    # BURX probes — Pass 25: TARGETED untested-risk-lever-per-baked-ETF.
    # ~50 (baked_etf × risk_mgmt_lever) combos unprobed (Pass 22 push baked
    # ETFs to end of pool). Round-robin one probe per baked ETF, conservative.
    if args.burx_probes > 0:
        baked_etfs_set = set(SESSION_BAKED_LEVERS.keys())
        # Build tested-per-etf map by scanning DB
        from collections import defaultdict
        import re as _re
        tested_per_etf: dict[str, set] = defaultdict(set)
        risk_levers_known = ['atr_sl', 'vol_max', 'dd_haircut', 'atr_p', 'mom_min']
        import qc_storage as _storage
        _db = _storage.connect(DB_PATH)
        for (n,) in _db.execute("SELECT name FROM experiments"):
            m = _re.match(r's002_(?:NEWAX|LEVAX|BAKERX|STACK|BURX)_([a-z]{2,5})_([\w_]+?)_(?:rv|verify)', n)
            if m:
                etf, rest = m.group(1), m.group(2)
                for lever in risk_levers_known:
                    if rest.startswith(lever):
                        tested_per_etf[etf].add(lever)
                        break
        _db.close()
        burx = baked_untested_risk_probes(rb.base, SESSION_BAKED_LEVERS,
                                          tested_per_etf=dict(tested_per_etf),
                                          max_probes=args.burx_probes,
                                          excluded_pairs=excluded_pairs)
        rb.add_probes(burx, salts=rb.salts[:3], prio=2, prefix='BURX',
                      max_probes=args.burx_probes)
        print(f'BURX probes: {len(burx)} baked-ETF × untested-risk-lever')

    # BAKERX probes — Pass 16: stack risk_mgmt levers on already-baked ETFs.
    # Validated: piz+atr_sl=2.5 = +0.00167. Each baked ETF gets a chance
    # at atr_sl/vol_max/dd_haircut at multiple values.
    if args.bakerx_probes > 0:
        bakerx = baked_risk_mgmt_probes(rb.base, SESSION_BAKED_LEVERS,
                                         max_probes=args.bakerx_probes)
        rb.add_probes(bakerx, salts=rb.salts[:3], prio=2, prefix='BAKERX',
                      max_probes=args.bakerx_probes)
        print(f'BAKERX probes: {len(bakerx)} risk_mgmt × baked ETFs')

    # NEWAX probes — Pass 11/13/14: ADD currently-untouched live levers.
    # Pass 14: SKIP baked ETFs entirely. R2532 evidence — adding bb_width_max
    # to already-baked itot/piz/kre caused -0.018 / -0.026 / -0.046 regressions.
    # NEW levers interact with existing tuning. Only probe NEWAX on
    # un-tuned ETFs.
    if args.newax_probes > 0:
        baked_etfs_set = set(SESSION_BAKED_LEVERS.keys())
        # Pass 18: skip (etf, lever, value) combos already tested ≥6 salts
        # with no lift. Prevents re-probing dead combos round after round.
        saturated = db_saturated_newax_combos(min_salts=6)
        # Per-lever filter: TRADE_GATE_LEVERS skip baked ETFs (avoid breaking
        # tuned configs); R2536 evidence shows RISK_MGMT_LEVERS broadly toxic
        # too — Pass 16 BAKERX killed.
        inert = db_inert_etfs()
        newax = untouched_lever_probes(rb.base, UNTOUCHED_LEVERS_CURATED,
                                        max_probes=args.newax_probes,
                                        excluded_pairs=excluded_pairs,
                                        baked_etfs=baked_etfs_set,
                                        saturated_combos=saturated,
                                        inert_etfs=inert)
        if saturated:
            print(f'NEWAX saturated-combo skip: {len(saturated)} dead combos blocked')
        if inert:
            print(f'Inert-ETF skip: {len(inert)} ETFs ({sorted(inert)[:5]}...) blocked at probe-gen')
        rb.add_probes(newax, salts=rb.salts[:3], prio=2, prefix='NEWAX',
                      max_probes=args.newax_probes)
        print(f'NEWAX probes: {len(newax)} on untouched live levers')

    # STACK probes — Pass 10: test alternate levers on already-baked ETFs.
    # Single-lever bake space is exhausted (R2521-2526 flat); compound
    # improvements may live in (baked_etf, untouched_lever) combinations.
    if args.stack_probes > 0:
        stack = bake_stack_probes(rb.base, SESSION_BAKED_LEVERS,
                                  max_probes=args.stack_probes,
                                  value_idx=R % 2)  # alternate value_idx
        rb.add_probes(stack, salts=rb.salts[:3], prio=2, prefix='STACK',
                      max_probes=args.stack_probes)
        print(f'STACK probes: {len(stack)} on {len(SESSION_BAKED_LEVERS)} baked ETFs')

    # Borderline reverification — pairs with 0.0001 ≤ POSITIVE lift < 0.001
    # FIXED 2026-05-10: was using abs(l) which re-qualified destructive
    # negative pairs (acwx -0.00048 × 15 specs, rhs -0.00095 × 30 specs).
    # Now only positive borderline lifts trigger reverify.
    # FIXED 2026-05-16: exclude already-baked (etf, lever) pairs. ewc:wt
    # qualified as borderline because BAKE-314 lift was +0.00048; BORD then
    # probed wt_lower_045 (below bake 0.0525) = guaranteed destructive
    # -0.00119 × 14 specs across R3219-R3223. Pure waste.
    if not args.no_dead_filter:
        borderline_pairs: set = set()
        for k, lifts in stats.items():
            ml = max(lifts) if lifts else 0  # was max(abs(l)) — caught negatives
            if 0.0001 <= ml < 0.001:
                etf, lever = k
                if lever in SESSION_BAKED_LEVERS.get(etf, []):
                    continue  # already-baked, opposite-direction probes destructive
                borderline_pairs.add(k)
        if borderline_pairs:
            border = borderline_reverify_probes(rb.base, borderline_pairs,
                                                max_probes=30)
            rb.add_probes(border, salts=rb.salts[:3], prio=2, prefix='BORD')

    import re as _re
    BAKED_SET = set(SESSION_BAKED_LEVERS.keys())
    inert_set = db_inert_etfs()
    from round_lib import db_utnt_inert_etfs as _db_utnt_inert, db_recent_inert_etfs as _db_recent_inert
    utnt_inert_set = _db_utnt_inert()  # 2026-05-10: 153 confirmed-dead via UTNT axes
    # 2026-05-18 R3630 30m audit: 44 always-NOOP ETFs (≥10 probes, all |lift|<0.0005
    # in last 180 rounds). Blocks UTNT/BTI/STX/WTX/CFX/SFX perturbation blocks.
    # BFSW excluded — its month_mask/atr_sl/dd_haircut mechanism can unlock these
    # (BAKE-337 ewc precedent).
    recent_inert_set = _db_recent_inert(min_probes=10, since_n_rounds=180)
    print(f'Recent-inert blocklist: {len(recent_inert_set)} ETFs (excluded from UTNT/BTI/XX)')
    universe = set(_re.findall(r"'([a-z]{2,5})':\{", rb.base))
    # Catastrophic UTNT tp_grow targets (R2810-R2818 audit, -0.05+ lifts × 3+ salts).
    # Pattern: leveraged/inverse/emerging-market/commodity ETFs destabilize at tp_grow.
    UTNT_CATASTROPHIC = {
        # Leveraged/inverse
        'uco', 'uwm', 'tna', 'sh', 'uso', 'fas',
        # Country/region single-market (high variance)
        'fxi', 'epi', 'iwf', 'ezu',  # ezu only at tp_grow_150pct catastrophic, 120pct=BAKE
        # Commodity/precious metal
        'iau', 'gld', 'dbb',
        # Biotech/sector concentration
        'fbt', 'tlh', 'ixc',
        # Factor-tilt / sector ETFs catastrophic at tp_grow_150pct (R2820)
        'fta',
        # R2824 audit: healthcare/energy/tech sector ETFs catastrophic
        'iez', 'ihi', 'igm', 'ihe',  # iez -2.5, ihi -1.4, igm -0.88, ihe -0.46
        # R2827 audit: country/sector/leveraged catastrophic
        'ilf', 'fez', 'ijs', 'agq', 'iwc', 'ieo',  # latam, eurozone, small-val, silver-2x, microcap, oil
        # R2828 audit
        'xrt', 'aoa',  # retail sector / asset-allocation aggressive
        # R2831 audit
        'mdyv', 'dln', 'mgc',  # mid-val, large-val, mega-cap
        # R2833 audit
        'xbi', 'dbc', 'xes', 'cwi', 'shm',  # biotech, commodity, energy-svc, foreign, short-muni
        # R2868-R2873 audit (post utnt_inert relaxation)
        'vym',  # high-div catastrophic on ALL tp_grow magnitudes
        'ixn',  # global-tech catastrophic on ALL 5 tp axes
        'aia',  # asia50 catastrophic
        'rez',  # real-estate catastrophic (also in BFSW_CATASTROPHIC)
        'psi', 'pwb',  # semiconductor (UTNT — different from BFSW), preferred-bank
        'iwo',  # russell 2000 growth (UTNT cat)
        # R2895/R2891 audit 2026-05-12: repeat catastrophic offenders
        'xlk',  # tech sector: 9.43-9.66 across ALL tp magnitudes (R2866+R2895, 60 wasted specs)
        'edv',  # extended-duration treasury: 9.63-9.67 across tp_grow_120 + tp_shrink (R2831+R2891)
        # R2900 audit 2026-05-12: repeat catastrophic
        'fxo',  # financial sector: -0.24 tp_grow_105 (R2900); -0.10 R2817; -0.03 R2881 (3-round pattern)
        # R2902 audit 2026-05-12: repeat catastrophic
        'voe',  # mid-cap value: -0.48 tp_grow_130 (R2902); -1.00 tp_grow_150, -0.36 tp_grow_120 (R2808)
        # R2905 audit 2026-05-12: tp_shrink_80 catastrophic in R2900+R2905 (filter blocked by stale-NOOP R2881 pos)
        'fxu',  # utility sector: tp_shrink_80 -0.235 × 2 rounds; filter 5x-rule rejected due to stale R2881 pos
        # R2913 30m review 2026-05-12: uniformly destructive across UTNT tp axes
        'ijt',  # S&P SmallCap Growth: -0.014 × 32 specs (11 mags × 3 salts) — saturated negative cell
        # R2924 30m review 2026-05-13: uniformly destructive across all 11 UTNT tp axes
        'iai',  # broker-dealer: -0.025 × 24 specs — high-vol financial sub-sector
        # R2930 30m review 2026-05-13: matches BFSW catastrophic pattern
        'ewp',  # Spain country ETF — also destructive in UTNT (-0.008 small but consistent)
        # R2932 30m review 2026-05-13: UTNT exposed
        'iyr',  # real estate (already in BFSW_CATASTROPHIC): UTNT tp_grow -0.04 to -0.05 × many
        'iyt',  # transportation: -0.05 tp_grow_130; -0.014 tp_grow_115
        'mln',  # munis-long: -0.243 tp_grow_105 catastrophic
        # R2977-R2979 30m review 2026-05-14: UTNT-wide destructive
        'mgk',  # Vanguard mega cap growth: -0.008 to -0.01 across 15+ tp magnitudes
        # R2990 30m review 2026-05-14: 100% destructive across all tp axes
        'icf',  # cohen-steers realty majors: 14/14 NEG (5 mags × ~3 salts) -0.0010
        'ivw',  # S&P 500 growth: 6 NEG -0.0052 across tp_grow_120/125/110 + 16 exact-zero
        'gwx',  # SPDR intl small cap: 5 NEG + 14 zero across 5 mags
        # R2991 30m review 2026-05-14:
        'iwd',  # Russell 1000 Value: 30 NEG + 6 zero = 36 wasted specs in single round
        'iwr',  # Russell midcap: 33/33 exact-zero across all UTNT axes — fully inert on tp
        # R2993 30m review 2026-05-14:
        'iyc',  # consumer cyclical: 32/32 exact-zero in single round (fully inert on tp)
    }
    # 2026-05-11: drop utnt_inert_set filter — base changed substantially after 27 session bakes;
    # 153 historically-inert ETFs may now respond. Catastrophic ones already in UTNT_CATASTROPHIC.
    # 2026-05-16: also exclude BFSW_CATASTROPHIC (R3259 leak: tfi was added to
    # BFSW_CAT but UTNT still picked it — different filter sets).
    untuned = sorted([e for e in universe if e not in BAKED_SET and e not in inert_set
                      and e not in UTNT_CATASTROPHIC and e not in BFSW_CATASTROPHIC
                      and e not in recent_inert_set])
    print(f'UTNT pool: {len(untuned)} live untuned ETFs (filtered {len(UTNT_CATASTROPHIC)} UTNT_CAT + {len(BFSW_CATASTROPHIC)} BFSW_CAT + {len(recent_inert_set)} recent-inert)')
    from round_lib import make_spec as _make_spec, codehash as _codehash

    # BTI block FIRST (historical 32.8% pos rate on baked-tp iteration)
    # 2026-05-17: tried adding non-tp-baked ETFs (ixn, cwi, dln, wood, tecl) to
    # BTI pool for cross-lever discovery. 2026-05-18 R3703 30m audit: ALL 10
    # BTI catastrophics in last 30 rounds were these cross-lever specs
    # (cwi/dln/ixn tp at -0.24 each). Reverted to tp-baked-only.
    # Cross-lever discovery doesn't work on tp axis when ETF baked on mm/atr_sl/dd.
    CURRENT_SESSION_NEW_BAKES = ['dfj','eem','xhb','igv','ixp']  # tp-baked only
    # BTI restored 2026-05-10 with SMALL magnitudes only — large mags
    # destroyed calibration. ±5% steps test true incremental iteration.
    # Expanded 2026-05-14: 4 magnitudes (±5%/±10%) to broaden probe surface.
    # Cross-round dedup means narrow ±5% saturates fast on long-baked ETFs.
    # 2026-05-18 30m R3602 audit: 50 rounds × 141 BTI specs, 49% tp_grow_105pct
    # + 28% tp_shrink_95pct (first 2 axes). Rotate to expose all 4 evenly.
    _BTI_AXES_POOL = [('tp_grow_105pct', 1.05), ('tp_shrink_95pct', 0.95),
                      ('tp_grow_110pct', 1.10), ('tp_shrink_90pct', 0.90)]
    _bti_off = R % len(_BTI_AXES_POOL)
    BTI_AXES = _BTI_AXES_POOL[_bti_off:] + _BTI_AXES_POOL[:_bti_off]
    # 2026-05-10: exclude ETFs with multi-spec catastrophic BTI history
    BTI_DESTRUCTIVE = {'iws', 'xhb', 'qld', 'fgd', 'rwo', 'kie', 'fxz', 'fxr', 'vis',
                        'ewg', 'ppa', 'iwb',
                        'eem',   # iter3 catastrophic R2801; saturated at iter2 0.3144
                        # R2820/R2821 audit: bakes hit -5%/+5% iter ceiling on these
                        'tur', 'piz', 'rspg', 'dfj',  # already-iterated bakes saturate at next iter
                        'vtv',  # R2841: tp_shrink_95pct -0.215 × 3 salts
                        # R2900 30m review 2026-05-12: 5 BTI repeat offenders auto-detected
                        # (each hit 3-4 rounds with destructive lifts)
                        'xme',   # tp_shrink_95pct -0.25 × 4 rounds (R2859/R2881/R2884/R2888)
                        'rpv',   # tp_grow_105pct -0.025 × 4 rounds
                        'pey',   # tp_grow_105pct -0.011 × 4 rounds
                        'spxl',  # tp_grow_105pct -0.23 × 3 rounds (R2804)
                        'ezu',   # tp_grow_105pct -0.23 × 3 rounds (R2876)
                        # R2993 30m review 2026-05-14:
                        'iwc',   # tp_shrink_95pct -0.0007 × 6 specs (Russell microcap)
                        # R3005 30m review 2026-05-14: tp_grow BTI reverses already-baked tp_shrink
                        'vti',   # tp_grow_105/110pct -0.001 to -0.003 × 6 (reverses BAKE-257 tp_shrink_80)
                        # R3016 30m review 2026-05-14:
                        'mdy',   # BTI tp_grow_110pct -0.00262 × 3 (reverses BAKE-237 tp_shrink_75)
                        # R3060 30m review 2026-05-14: post BAKE-301 sl=0.06, efa tp lever destructive
                        'efa',   # BTI tp_shrink_90/grow_105/grow_110 -0.00131 to -0.00262 × 4 (post-sl-bake reversal)
                        # R3249 30m review 2026-05-16: 100% destructive on BTI iteration
                        'ihf',   # 13/13 destructive (also ef catastrophic -0.47 on different lever)
                        'don',   # 9/9 destructive on tp± iterations
                        # R3262 12m: BTI iteration catastrophic
                        'iwm',   # BTI tp_grow_105pct -0.247 × 3 (Russell 2000 baked-tp saturated)
                        # R3735 30m audit 2026-05-18: 11 destr across 4 BTI values
                        'dth',   # BTI tp_grow_105/110 -0.0019, tp_shrink_90/95 -0.24 × 8 (BAKE-238 tp=0.030 captured optimum, iter past = catastrophic)
                        }
    # Cool-off: ETFs baked in last 3 rounds (R2818-R2820) skip BTI
    # to let new calibration settle before testing iteration
    # Cool-off applies ONLY to last-5 bakes (3-5 rounds settling); older bakes eligible for BTI re-iter
    BTI_COOL_OFF = {'vdc', 'rwl', 'kre', 'rspu', 'rspt', 'vpu'}  # BAKE-251 to BAKE-256 (current)
    # 2026-05-15 30m review: restrict BTI pool to ETFs ACTUALLY baked on tp.
    # 36 of 95 baked ETFs aren't tp-baked but were in BTI pool, producing
    # destructive specs (pbw tp_grow_105 -0.30, ilf tp_grow_105 -0.032).
    # Cross-axis tp probing on non-tp-baked ETFs belongs in BFSW/NEWLEV.
    TP_BAKED_ETFS = {e for e, lvs in SESSION_BAKED_LEVERS.items() if 'tp' in lvs}
    # 2026-05-19 R3803 30m audit: dynamic BTI-exhausted filter (≥2 distinct
    # destructive tp cells in 80 rounds). Catches ewd/gsg/igv/sptm/vo/xlb +
    # any future ETF that hits the exhaustion threshold (post-bake symmetric
    # destruction). Bypasses baked_exempt logic since the evidence is post-bake.
    from round_lib import db_bti_exhausted_etfs
    bti_exhausted = db_bti_exhausted_etfs()
    bti_pool = [e for e in (list(TP_BAKED_ETFS) + CURRENT_SESSION_NEW_BAKES)
                if e not in BTI_DESTRUCTIVE and e not in BTI_COOL_OFF
                and e not in recent_inert_set and e not in bti_exhausted]
    if bti_exhausted:
        print(f'BTI-exhausted (auto-detected): {sorted(bti_exhausted)} ({len(bti_exhausted)} ETFs)')
    bti_start = (R * 6) % max(1, len(bti_pool))
    # Restored 2026-05-11: expansion to 20-ETF rotation didn't unlock specs
    # (cross-round dedup catches all ±5% iterations). Keep [:4] standard rotation.
    bti_slice = (bti_pool[bti_start:] + bti_pool[:bti_start])[:4]
    bti_max_specs = 7  # 2026-05-19 R3801: bumped 5→7 to honor 16-meaningful invariant. BTI baked-tp pool is reliable source after sphq+itot post-bake-iter productive precedent.
    bti_added = 0
    bti_destructive_skips = 0
    bti_noop_sig_skips = 0
    bti_dead_pair_skips = 0
    for etf in bti_slice:
        if rb.remaining <= 0 or bti_added >= bti_max_specs:
            break
        # 2026-05-15: axis-class destructive/NOOP/inert aggregator
        # BAKED EXEMPTION: if ETF is in SESSION_BAKED_LEVERS for tp, history
        # is pre-bake-dominated and filter shouldn't block iteration around
        # the freshly-baked value.
        bti_baked_exempt = 'tp' in SESSION_BAKED_LEVERS.get(etf, [])
        if not bti_baked_exempt:
            if (etf, 'tp') in rb._destr_etf_axes:
                bti_destructive_skips += 1
                continue
            if (etf, 'tp') in rb._noop_etf_axes or (etf, 'tp') in rb._inert_etf_axes:
                bti_noop_sig_skips += 1
                continue
        m = _re.search(rf"'{etf}':\{{[^}}]*?'tp':\s*([\d.]+)", rb.base)
        if not m:
            continue
        cur_tp = float(m.group(1))
        for axis_name, mult in BTI_AXES:
            if rb.remaining <= 0 or bti_added >= bti_max_specs:
                break
            # 2026-05-13: full filter chain (previously only destructive_cells)
            ax_parts = axis_name.rsplit('_', 1)
            if len(ax_parts) == 2:
                ax_prefix, val_lbl = ax_parts
                # 2026-05-15: catastrophic cells filter (no recency window —
                # rgi tp_grow_105pct landed -0.26 in R2980, slipped past 20-round
                # _destructive_cells, wasted 6 specs in R3068+R3116).
                if (etf, ax_prefix, val_lbl) in rb._catastrophic_cells:
                    bti_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._destructive_cells:
                    bti_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._noop_sigs:
                    bti_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._quasi_noop_cells:
                    bti_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix) in rb._dead_pairs:
                    bti_dead_pair_skips += 1
                    continue
                if (ax_prefix, val_lbl) in rb._dead_axis_values:
                    bti_noop_sig_skips += 1
                    continue
            new_tp = round(cur_tp * mult, 4)
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or bti_added >= bti_max_specs:
                    break
                try:
                    code = _make_spec(etf, {'tp': new_tp}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_BTI_{etf}_{axis_name}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'BTI {etf} tp={new_tp}',
                                     rb.based_on, 1))
                    rb._spec_hashes.add(h)
                    bti_added += 1
                except Exception:
                    pass
    print(f'BTI probes (baked-tp iteration, 32.8% pos rate): {bti_added} specs '
          f'(destructive={bti_destructive_skips} noop-sig={bti_noop_sig_skips} '
          f'dead-pair={bti_dead_pair_skips})')

    # NEWLEV block 2026-05-15: probe UNPROBED lever classes on baked ETFs.
    # Audit found 9 levers configured in 50-282 ETFs but ZERO probes ever:
    # sp(282) ef(168) xf(137) ub(123) um(122) cm(114) cd(90) am(53) bw(51).
    # 2026-05-15: sp DROPPED after 17 specs (-0.05 avg), ef DROPPED after 12 specs
    # (4 neg + 8 zero, 0 positive). Continue rotation: xf/am/cd/cm/ub/um/cb.
    # 2026-05-16: 3-way rotation since NEWLEV max=6 = 2 axes/ETF.
    # R % 3 == 0: e first (entry threshold — productive on ewc BAKE-311)
    # R % 3 == 1: x first (exit threshold — under-explored)
    # R % 3 == 2: FRONTIER first (cm/cb/um/ub — totally unprobed: 115-130 ETFs each)
    # Frontier rotation guarantees coverage of zero-explored levers every 3 rounds.
    # 2026-05-16 break-stuck: tried shrink_98pct (0% pos) → shrink_90pct (8.7% pos)
    # but R3249 showed fxn e_shrink_90pct = -0.232 CATASTROPHIC. e/x levers
    # too sensitive for -10% perturbation. Reverted to shrink_95pct as
    # compromise: still meaningful change (5%) but not catastrophic on
    # entry/exit-threshold-sensitive ETFs.
    _frontier = [('ef',1.05,'ef_grow_105pct','m'), ('cm',1.05,'cm_grow_105pct','m'),
                 ('cb',1.05,'cb_grow_105pct','m'), ('um',1.05,'um_grow_105pct','m'),
                 ('ub',1.05,'ub_grow_105pct','m'), ('rg',1.05,'rg_grow_105pct','m'),
                 ('bw',1.05,'bw_grow_105pct','m')]
    # 2026-05-17 30m audit: NEWLEV e-axis -1.13% avg (9 specs, 0 pos) and
    # x-axis -0.18% avg (21 specs, 0 pos) over last 12 rounds. Only ub at
    # 11% pos. Demoted e/x from rotation-priority — kept in NEWLEV_AXES
    # tail as fallback only. All rotations now frontier-led.
    if R % 3 == 0:
        # ub-led (only productive frontier axis to date)
        NEWLEV_PRIORITY = [('ub',1.05,'ub_grow_105pct','m'), ('ub',0.95,'ub_shrink_95pct','m')] + _frontier
    elif R % 3 == 1:
        # cb-led (untested frontier, 130 ETFs)
        NEWLEV_PRIORITY = [('cb',1.05,'cb_grow_105pct','m'), ('cb',0.95,'cb_shrink_95pct','m')] + _frontier
    else:
        NEWLEV_PRIORITY = _frontier
    # 2026-05-16: reordered to prioritize TOTALLY UNPROBED levers (cm/cb/um/ub
    # have 115-130 ETFs configured each but 0 probes ever). cd dropped to last
    # after being banned by dead_axis_values filter. xf moved later — already
    # partly probed.
    # 2026-05-16 (break-stuck): added ef (168 ETFs unprobed!), rg (68 ETFs),
    # bw (52 ETFs). 22+ rounds bake drought — opening the largest unexplored
    # lever surfaces to break the plateau.
    # 2026-05-18 30m R3607 audit: NEWLEV ef_grow_105pct = 47% of 40 specs (always
    # first in tail). Rotate tail by round so cm/cb/um/ub/bw/rg/xf/am/cd cycle
    # into 2nd-priority slot evenly.
    # 2026-05-19 R3809 30m audit: per-axis 300-round yield. Pruned 100%-waste
    # shrink axes (5-11 specs / 100% neg):
    #   ef_shrink_95pct: 100% waste (11/11 neg) — REMOVED
    #   xf_shrink_95pct: 100% waste (5/5 neg) — REMOVED
    #   xf_grow_105pct:  57% waste (4/7 neg) — REMOVED
    # Promoted rg_grow_105pct: 25% pos (2/8) — productive frontier (aok BAKE-339).
    # Kept: ef_grow (17% waste but historical productive), cm_grow/cb_grow/
    # um_grow/ub_grow/bw_grow (0-2% waste), cd/am (untested or low-N).
    _NEWLEV_TAIL = [
        ('rg', 1.05, 'rg_grow_105pct', 'm'),  # 25% POS — aok BAKE-339 source
        ('ef', 1.05, 'ef_grow_105pct', 'm'),  # 17% waste, historical productive
        ('cm', 1.05, 'cm_grow_105pct', 'm'),  # FRONTIER, 4% waste
        ('cb', 1.05, 'cb_grow_105pct', 'm'),  # FRONTIER, 2% waste
        ('um', 1.05, 'um_grow_105pct', 'm'),  # FRONTIER, 8% waste
        ('ub', 1.05, 'ub_grow_105pct', 'm'),  # FRONTIER, 2% waste
        ('bw', 1.05, 'bw_grow_105pct', 'm'),  # FRONTIER, 0% waste
        ('cb', 0.95, 'cb_shrink_95pct', 'm'),  # 0% waste (13 specs)
        ('cm', 0.95, 'cm_shrink_95pct', 'm'),  # untested
        ('um', 0.95, 'um_shrink_95pct', 'm'),  # untested
        ('ub', 0.95, 'ub_shrink_95pct', 'm'),  # 25% waste but small N
        ('rg', 0.95, 'rg_shrink_95pct', 'm'),
        ('bw', 0.95, 'bw_shrink_95pct', 'm'),
        ('am', 1, 'am_grow_1', 'a'),
        ('am', -1, 'am_shrink_1', 'a'),
        ('cd', 1, 'cd_grow_1', 'a'),
        ('cd', -1, 'cd_shrink_1', 'a'),
    ]
    _newlev_tail_off = R % len(_NEWLEV_TAIL)
    NEWLEV_AXES = NEWLEV_PRIORITY + _NEWLEV_TAIL[_newlev_tail_off:] + _NEWLEV_TAIL[:_newlev_tail_off]
    # R3113 audit 2026-05-15: ETFs catastrophic on NEWLEV xf/cd lever class.
    # Per-axis filter only catches them AFTER first burn; preemptively block.
    NEWLEV_BLOCKED = {
        'ijk',   # R3109 xf_grow/shrink -0.30 × 3 (5-bake mega-baked ETF, saturated)
        'ilf',   # R3102 cd_shrink_1 -0.24 × 1 (3-bake baked, saturated)
        'ewl',   # R3107 xf_grow_105pct -0.009 × 3 + xf_shrink -0.0002
        'ddm',   # R3106 xf_shrink_95pct -0.011 × 1 (already 2-bake saturated)
        'fvd',   # R3122 xf_grow_105pct -0.0145 × 1 (atr_sl-baked, xf saturated)
        'ijr',   # R3130 xf_grow/shrink -0.012/-0.017 × 3 (month_mask-baked, xf catastrophic)
    }
    newlev_added = 0
    newlev_destr_skips = 0
    # 2026-05-16 break-stuck: on FRONTIER rounds (R%3==2), boost to 9 specs (3
    # axes × 3 salts). With 7 frontier axes (ef/cm/cb/um/ub/rg/bw) the extra
    # budget tests more frontier ETFs per round, accelerating ef/rg/bw
    # discovery on 168/68/52 untouched-ETF surfaces.
    newlev_max_specs = 2 if R % 3 == 2 else 1  # 2026-05-17 R3412 30m audit: NEWLEV 0% yield over 55 specs / 20 rounds. Further cut 4/2 → 2/1. Shifting budget to higher-yield BTI/UTNT.
    # 2026-05-16: on FRONTIER rounds, expand pool to include UNTUNED ETFs too.
    # gsg (BAKE-316) was a tp-baked commodity that responded to x. But ~150
    # cold ETFs (dbc, gld, dba, djp, pho, wood, etc.) also have x/cm/cb/etc.
    # configured and never get NEWLEV tested because pool was baked-tp-only.
    # Frontier exploration needs broader candidate base.
    base_pool = [e for e in (bti_pool_xx if 'bti_pool_xx' in dir() else bti_pool)
                 if e not in NEWLEV_BLOCKED]
    if R % 3 == 2:
        # Add untuned ETFs (excluding blocked) for broader frontier coverage
        untuned_pool = [e for e in untuned if e not in NEWLEV_BLOCKED
                        and e not in BFSW_CATASTROPHIC]
        newlev_pool = sorted(set(base_pool) | set(untuned_pool))
    else:
        newlev_pool = sorted(base_pool)
    newlev_start = (R * 9) % max(1, len(newlev_pool))
    newlev_slice = (newlev_pool[newlev_start:] + newlev_pool[:newlev_start])[:8]
    for etf in newlev_slice:
        if rb.remaining <= 0 or newlev_added >= newlev_max_specs:
            break
        for ax_key, val, label, kind in NEWLEV_AXES:
            if rb.remaining <= 0 or newlev_added >= newlev_max_specs:
                break
            # 2026-05-15: allow negative values (for 'e'/'x' on ETFs with negative thresholds)
            m = _re.search(rf"'{etf}':\{{[^}}]*?'{ax_key}':\s*(-?[\d.]+)", rb.base)
            if not m:
                continue
            cur = float(m.group(1))
            new_val = round(cur * val, 4) if kind == 'm' else cur + val
            # Allow new_val to be negative (e.g., for negative thresholds)
            if abs(new_val) < 1e-6 and kind == 'm':  # avoid zero on multiplicative
                continue
            if (etf, ax_key) in rb._destr_etf_axes:
                newlev_destr_skips += 1
                continue
            if (etf, ax_key) in rb._inert_etf_axes:
                continue
            if (etf, ax_key) in rb._noop_etf_axes:
                continue
            # 2026-05-16: global dead axis-value filter. Parse label
            # (e.g., 'cd_grow_1' → ('cd_grow', '1')) and check.
            _label_parts = label.rsplit('_', 1)
            if len(_label_parts) == 2 and tuple(_label_parts) in rb._dead_axis_values:
                newlev_destr_skips += 1
                continue
            # 2026-05-16 (R3240 bug fix): NEWLEV was missing per-cell filters
            # (catastrophic/destructive). R3240 re-queued igv e_grow_105pct
            # despite R3237 showing -0.02976 × 3 (in destructive_cells).
            # 2026-05-16 (R3262 bug fix): also missing noop_sigs check.
            # R3262 about to re-queue fxn x_grow_105pct + x_shrink_95pct
            # despite R3259 showing 6 NOOP-equivalent specs (in noop_sigs).
            if len(_label_parts) == 2:
                _ax_prefix, _val_lbl = _label_parts
                if (etf, _ax_prefix, _val_lbl) in rb._catastrophic_cells:
                    newlev_destr_skips += 1
                    continue
                if (etf, _ax_prefix, _val_lbl) in rb._destructive_cells:
                    newlev_destr_skips += 1
                    continue
                if (etf, _ax_prefix, _val_lbl) in rb._noop_sigs:
                    newlev_destr_skips += 1
                    continue
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or newlev_added >= newlev_max_specs:
                    break
                try:
                    code = _make_spec(etf, {ax_key: new_val}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_NEWLEV_{etf}_{label}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'NEWLEV {etf} {ax_key}={new_val}',
                                     rb.based_on, 2))
                    rb._spec_hashes.add(h)
                    newlev_added += 1
                except Exception:
                    pass
    print(f'NEWLEV probes (unprobed lever classes, NEW 2026-05-15): '
          f'{newlev_added} specs (destructive={newlev_destr_skips})')

    # UTNT block — moved here 2026-05-15 (30m review) because the XX blocks
    # (STX/WTX/CFX/SFX) below were consuming all budget, leaving UTNT with 0
    # specs in R3063-R3118 (55 rounds). UTNT historically delivered 32 of
    # ~70 bakes — the most productive block. Run it BEFORE XX blocks.
    # Rotate through untuned ETFs across rounds: each round picks a different 50
    start = (R * 30) % len(untuned) if untuned else 0
    untuned_slice = (untuned[start:] + untuned[:start])[:50]
    # 2026-05-17 30m R3382 audit: tp_grow_120pct cross-ETF over 22 rounds =
    # 2 single-rv lifts (variance) / 5 destructive cells / 1 CATASTROPHIC
    # (ixg -0.242). Net-negative. Demoted to last priority; tp_grow_115pct
    # (smaller 15% perturbation) promoted first. tp_grow_105pct/110pct
    # safer for untested ETFs.
    # 2026-05-18 30m R3597 audit: 50 rounds × 199 specs only tested tp_grow_115pct
    # and tp_grow_110pct (always first 2 axes). tp_shrink_75pct (6 historical
    # bakes: vis/xme/sphq/mdy/dth/dem) untested in 50+ rounds! Round-based
    # rotation cycles the priority order so all 10 safe axes get exposure.
    # 2026-05-18 30m R3624 audit: tp_grow_125pct was 3 catastrophic / 8 specs
    # (37% cata rate, iev -0.24, others). Demoted to fallback alongside 120pct.
    # 2026-05-19 R3789 audit: tp_grow_120pct has 41 historical positives (most
    # productive UTNT value!) + 42 untuned ETFs NEVER tested. Re-promoted to
    # rotation; catastrophic ETFs (ixg etc.) now permanently in cata filter.
    # tp_grow_125pct (37% cata rate) stays fallback.
    # 2026-05-19 R3807 user directive "do not wast backtests": pruned high-neg
    # axes per 300-round yield audit (all axes 0% pos):
    #   tp_shrink_50: 26% neg + 3% cata = REMOVED (148 specs / 44 waste)
    #   tp_shrink_60: 15% neg = REMOVED (188 specs / 29 waste)
    #   tp_shrink_75: 11% neg = REMOVED (101 specs / 11 waste)
    #   tp_grow_130:  6% neg = REMOVED (82 specs / 5 waste)
    #   tp_grow_125: 11% cata = REMOVED from fallback (was 27 specs / 3 cata)
    # Kept axes have ≤9% combined neg+cata rate; safer EV at plateau.
    UTNT_AXES_ROTATING = [
        ('tp_grow_115pct', 1.15),
        ('tp_grow_120pct', 1.20),  # 41 historical positives — top productive value
        ('tp_grow_110pct', 1.10),
        ('tp_shrink_90pct', 0.90),  # 0% neg over 130 specs — safest
        ('tp_shrink_85pct', 0.85),
        ('tp_shrink_80pct', 0.80),  # 4% neg
        ('tp_grow_105pct', 1.05),   # 3% neg
        ('tp_shrink_70pct', 0.70),  # 9% neg — moderate
    ]
    utnt_axis_offset = R % len(UTNT_AXES_ROTATING)
    UTNT_AXES = (UTNT_AXES_ROTATING[utnt_axis_offset:] +
                 UTNT_AXES_ROTATING[:utnt_axis_offset])
    print(f'UTNT axis rotation R%{len(UTNT_AXES_ROTATING)}={utnt_axis_offset} — first axis: {UTNT_AXES[0][0]}')
    utnt_max_specs = 12  # 2026-05-19 R3801: bumped 8→12 to honor 16-meaningful invariant (R3800 10 specs / R3801 13 specs). UTNT is highest yield surface + rotation; widening cap absorbs shortfall from saturated BTI/WTX/STX/CFX.
    # 2026-05-16: cap axes per ETF to 1 (was unlimited until budget). 109 cold
    # ETFs untested since R3200 — broader coverage > per-ETF depth. With 6 spec
    # budget and 1 axis × 3 salts per ETF, can probe 2 ETFs/round = double
    # coverage rate vs prior 1 ETF × 2 axes.
    utnt_axes_per_etf = 1
    utnt_added = 0
    utnt_destructive_skips = 0
    utnt_noop_sig_skips = 0
    utnt_dead_pair_skips = 0
    for etf in untuned_slice:
        if rb.remaining <= 0 or utnt_added >= utnt_max_specs:
            break
        m = _re.search(rf"'{etf}':\{{[^}}]*?'tp':\s*([\d.]+)", rb.base)
        if not m:
            continue
        cur_tp = float(m.group(1))
        # 2026-05-17 R3452 30m fix: UTNT was missing _destr_etf_axes check
        # (failed_vrfy unioned in). iyw + iyz both queued despite (iyw,tp)
        # and (iyz,tp) being in filter. Skip entire ETF if tp axis blocked.
        if (etf, 'tp') in rb._destr_etf_axes:
            continue
        utnt_etf_axes_added = 0
        for axis_name, mult in UTNT_AXES:
            if utnt_etf_axes_added >= utnt_axes_per_etf:
                break
            if rb.remaining <= 0 or utnt_added >= utnt_max_specs:
                break
            ax_parts = axis_name.rsplit('_', 1)
            if len(ax_parts) == 2:
                ax_prefix, val_lbl = ax_parts
                if (etf, ax_prefix, val_lbl) in rb._catastrophic_cells:
                    utnt_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._destructive_cells:
                    utnt_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._noop_sigs:
                    utnt_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._quasi_noop_cells:
                    utnt_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix) in rb._dead_pairs:
                    utnt_dead_pair_skips += 1
                    continue
                if (ax_prefix, val_lbl) in rb._dead_axis_values:
                    utnt_noop_sig_skips += 1
                    continue
            new_tp = round(cur_tp * mult, 4)
            specs_before_axis = utnt_added
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or utnt_added >= utnt_max_specs:
                    break
                try:
                    code = _make_spec(etf, {'tp': new_tp}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_UTNT_{etf}_{axis_name}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'UTNT {etf} tp={new_tp}',
                                     rb.based_on, 2))
                    rb._spec_hashes.add(h)
                    utnt_added += 1
                except Exception:
                    pass
            if utnt_added > specs_before_axis:
                utnt_etf_axes_added += 1
    print(f'UTNT probes (user-directed untuned focus, moved 2026-05-15): {utnt_added} specs '
          f'(destructive={utnt_destructive_skips} noop-sig={utnt_noop_sig_skips} '
          f'dead-pair={utnt_dead_pair_skips})')

    # STX block 2026-05-14: sl (stop loss) iteration on baked ETFs.
    # 248/311 ETFs have both tp+sl. After tp lever saturation (R2996 76-spec
    # shortfall), sl is a fresh untouched lever. Mirrors BTI pattern.
    # Reordered 2026-05-16: prefer sl_shrink_90pct (21% pos rate historically)
    # over sl_grow_110pct (11% pos rate). With stx_max_specs=3, only first axis
    # gets picked per round; 6 consecutive rounds R3215-R3228 all rotated
    # sl_grow_110pct × different ETFs (qqq/vo/ewn/ixp/dem/rhs) = 18 wasted NOOPs.
    # 2026-05-19 R3812 30m audit: 300-round STX yield by axis (all 0% pos):
    # sl_shrink_80pct: 22% waste (2 cata + 10 neg over 54) — REMOVED
    # sl_grow_120pct:  21% waste (10 neg over 47) — REMOVED
    # Kept sl_shrink_90pct (17% waste) + sl_grow_110pct (15% waste, was
    # historically 11% pos before plateau).
    _STX_AXES_POOL = [('sl_shrink_90pct', 0.90), ('sl_grow_110pct', 1.10)]
    _stx_off = R % len(_STX_AXES_POOL)
    STX_AXES = _STX_AXES_POOL[_stx_off:] + _STX_AXES_POOL[:_stx_off]
    # Unified destructive-ETF filter for all new XX blocks (R2999 audit found
    # edv -0.26 on STX, ewq -0.24 on CFX, pjp -0.24 on WTX). Skip ETFs that
    # are catastrophic on ANY lever class.
    XX_BLOCKED = BFSW_CATASTROPHIC | {
        'edv',  # STX sl_shrink_80pct -0.26498 × 3 (already BFSW_CAT)
        'ewq',  # CFX cf_grow_105/110pct -0.24 (France country ETF)
        'pjp',  # WTX wt_shrink_95pct -0.24 (Japan pharma)
        # R3005 30m review 2026-05-14:
        'pbw',  # WTX wt_shrink_95pct -0.23430 × 3 (clean energy; baked on mm=3583)
        # R3012 30m review 2026-05-14: WTX repeat destructive on baked ETFs
        'mdy',  # 12 NEG on wt_shrink (tp_shrink baked already)
        'fvd',  # 6 NEG on wt_shrink (atr_sl baked)
        'nlr',  # 6 NEG on wt_shrink (month_mask baked)
        'spdw', # 3 NEG on wt_grow_110pct
        # R3016 30m review 2026-05-14: XX block leaks
        'sds',  # CFX cf_grow_110pct -2.70435 × 3 — CATASTROPHIC (already wt-baked)
        'itot', # WTX wt_grow_110pct -0.00190 × 3 (already wt-baked)
        # R3060 30m review 2026-05-14: STX repeat destructive
        'vpl',  # STX sl all directions noise (std=0.00123, no real signal)
    }
    # Rotation across baked pool to avoid alphabetical starvation
    bti_pool_xx = [e for e in bti_pool if e not in XX_BLOCKED]
    stx_start = (R * 4) % max(1, len(bti_pool_xx))
    stx_slice = (bti_pool_xx[stx_start:] + bti_pool_xx[:stx_start])[:6]
    stx_max_specs = 2  # Halved 2026-05-17: target=16 (was 3).
    stx_added = 0
    stx_destructive_skips = 0
    stx_noop_sig_skips = 0
    stx_dead_pair_skips = 0
    for etf in stx_slice:
        if rb.remaining <= 0 or stx_added >= stx_max_specs:
            break
        # 2026-05-15: axis-class filter + baked-exemption
        stx_baked_exempt = 'sl' in SESSION_BAKED_LEVERS.get(etf, [])
        if not stx_baked_exempt:
            if (etf, 'sl') in rb._destr_etf_axes:
                stx_destructive_skips += 1
                continue
            if (etf, 'sl') in rb._noop_etf_axes or (etf, 'sl') in rb._inert_etf_axes:
                stx_noop_sig_skips += 1
                continue
        m = _re.search(rf"'{etf}':\{{[^}}]*?'sl':\s*([\d.]+)", rb.base)
        if not m:
            continue
        cur_sl = float(m.group(1))
        for axis_name, mult in STX_AXES:
            if rb.remaining <= 0 or stx_added >= stx_max_specs:
                break
            ax_parts = axis_name.rsplit('_', 1)
            if len(ax_parts) == 2:
                ax_prefix, val_lbl = ax_parts
                if (etf, ax_prefix, val_lbl) in rb._catastrophic_cells:
                    stx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._destructive_cells:
                    stx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._noop_sigs:
                    stx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._quasi_noop_cells:
                    stx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix) in rb._dead_pairs:
                    stx_dead_pair_skips += 1
                    continue
                # 2026-05-16: global dead-axis-value filter (cross-ETF NOOP).
                # sl_grow_110pct caught 15/15 NOOP / 5 ETFs.
                if (ax_prefix, val_lbl) in rb._dead_axis_values:
                    stx_noop_sig_skips += 1
                    continue
            new_sl = round(cur_sl * mult, 4)
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or stx_added >= stx_max_specs:
                    break
                try:
                    code = _make_spec(etf, {'sl': new_sl}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_STX_{etf}_{axis_name}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'STX {etf} sl={new_sl}',
                                     rb.based_on, 1))
                    rb._spec_hashes.add(h)
                    stx_added += 1
                except Exception:
                    pass
    print(f'STX probes (baked-sl iteration, NEW 2026-05-14): {stx_added} specs '
          f'(destructive={stx_destructive_skips} noop-sig={stx_noop_sig_skips} '
          f'dead-pair={stx_dead_pair_skips})')

    # WTX block 2026-05-14: wt iteration on baked ETFs. 4 of 5 session bakes
    # from this block (ige+vo+ewj+sds; ddm pending).
    # wt_shrink_90pct REMOVED R3012 — mdy/fvd/nlr consistently destructive at -10% shrink.
    _WTX_AXES_POOL = [('wt_grow_105pct', 1.05), ('wt_shrink_95pct', 0.95),
                      ('wt_grow_110pct', 1.10)]
    _wtx_off = R % len(_WTX_AXES_POOL)
    WTX_AXES = _WTX_AXES_POOL[_wtx_off:] + _WTX_AXES_POOL[:_wtx_off]
    WT_MAX = 0.0699  # match base WT_CAP
    wtx_start = (R * 5) % max(1, len(bti_pool_xx))
    wtx_slice = (bti_pool_xx[wtx_start:] + bti_pool_xx[:wtx_start])[:10]
    wtx_max_specs = 2  # Halved 2026-05-17: target=16 (was 4).
    wtx_added = 0
    wtx_destructive_skips = 0
    wtx_noop_sig_skips = 0
    wtx_dead_pair_skips = 0
    for etf in wtx_slice:
        if rb.remaining <= 0 or wtx_added >= wtx_max_specs:
            break
        # 2026-05-15: axis-class filter + baked-exemption
        wtx_baked_exempt = 'wt' in SESSION_BAKED_LEVERS.get(etf, []) or 'wt2' in SESSION_BAKED_LEVERS.get(etf, [])
        if not wtx_baked_exempt:
            if (etf, 'wt') in rb._destr_etf_axes:
                wtx_destructive_skips += 1
                continue
            if (etf, 'wt') in rb._noop_etf_axes or (etf, 'wt') in rb._inert_etf_axes:
                wtx_noop_sig_skips += 1
                continue
        m = _re.search(rf"'{etf}':\{{[^}}]*?'wt':\s*([\d.]+)", rb.base)
        if not m:
            continue
        cur_wt = float(m.group(1))
        for axis_name, mult in WTX_AXES:
            if rb.remaining <= 0 or wtx_added >= wtx_max_specs:
                break
            ax_parts = axis_name.rsplit('_', 1)
            if len(ax_parts) == 2:
                ax_prefix, val_lbl = ax_parts
                if (etf, ax_prefix, val_lbl) in rb._catastrophic_cells:
                    wtx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._destructive_cells:
                    wtx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._noop_sigs:
                    wtx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._quasi_noop_cells:
                    wtx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix) in rb._dead_pairs:
                    wtx_dead_pair_skips += 1
                    continue
                if (ax_prefix, val_lbl) in rb._dead_axis_values:
                    wtx_noop_sig_skips += 1
                    continue
            new_wt = round(cur_wt * mult, 4)
            if new_wt > WT_MAX or new_wt < 0.01:  # safety bounds
                continue
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or wtx_added >= wtx_max_specs:
                    break
                try:
                    code = _make_spec(etf, {'wt': new_wt}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_WTX_{etf}_{axis_name}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'WTX {etf} wt={new_wt}',
                                     rb.based_on, 1))
                    rb._spec_hashes.add(h)
                    wtx_added += 1
                except Exception:
                    pass
    print(f'WTX probes (baked-wt iteration, NEW 2026-05-14): {wtx_added} specs '
          f'(destructive={wtx_destructive_skips} noop-sig={wtx_noop_sig_skips} '
          f'dead-pair={wtx_dead_pair_skips})')

    # CFX block 2026-05-14: cf (close factor) iteration. 259/311 ETFs have cf.
    # Fresh untouched lever class to break tp-axis saturation.
    # 2026-05-19 R3812 30m audit: cf_grow_110pct = 30% waste (3 cata + 13 neg
    # over 54 specs) — REMOVED. Others 0-4% waste.
    _CFX_AXES_POOL = [('cf_grow_105pct', 1.05), ('cf_shrink_95pct', 0.95),
                      ('cf_shrink_90pct', 0.90)]
    _cfx_off = R % len(_CFX_AXES_POOL)
    CFX_AXES = _CFX_AXES_POOL[_cfx_off:] + _CFX_AXES_POOL[:_cfx_off]
    # R3113 audit 2026-05-15: cf-saturated ETFs; all CFX_AXES values destructive
    # despite baked-exemption (signal exhausted past current bake).
    CFX_BLOCKED = {
        'ddm',   # 8 specs over R3104+R3111 cf_grow_105pct=-0.011 × 8 (baked cf=1.012, saturated)
    }
    cfx_pool_xx = [e for e in bti_pool_xx if e not in CFX_BLOCKED]
    cfx_start = (R * 7) % max(1, len(cfx_pool_xx))
    cfx_slice = (cfx_pool_xx[cfx_start:] + cfx_pool_xx[:cfx_start])[:6]
    cfx_max_specs = 2  # Halved 2026-05-17: target=16 (was 4).
    cfx_added = 0
    cfx_destructive_skips = 0
    cfx_noop_sig_skips = 0
    cfx_dead_pair_skips = 0
    for etf in cfx_slice:
        if rb.remaining <= 0 or cfx_added >= cfx_max_specs:
            break
        # 2026-05-15: axis-class filter + baked-exemption
        cfx_baked_exempt = 'cf' in SESSION_BAKED_LEVERS.get(etf, [])
        if not cfx_baked_exempt:
            if (etf, 'cf') in rb._destr_etf_axes:
                cfx_destructive_skips += 1
                continue
            if (etf, 'cf') in rb._noop_etf_axes or (etf, 'cf') in rb._inert_etf_axes:
                cfx_noop_sig_skips += 1
                continue
        m = _re.search(rf"'{etf}':\{{[^}}]*?'cf':\s*([\d.]+)", rb.base)
        if not m:
            continue
        cur_cf = float(m.group(1))
        for axis_name, mult in CFX_AXES:
            if rb.remaining <= 0 or cfx_added >= cfx_max_specs:
                break
            ax_parts = axis_name.rsplit('_', 1)
            if len(ax_parts) == 2:
                ax_prefix, val_lbl = ax_parts
                if (etf, ax_prefix, val_lbl) in rb._catastrophic_cells:
                    cfx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._destructive_cells:
                    cfx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._noop_sigs:
                    cfx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._quasi_noop_cells:
                    cfx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix) in rb._dead_pairs:
                    cfx_dead_pair_skips += 1
                    continue
                if (ax_prefix, val_lbl) in rb._dead_axis_values:
                    cfx_noop_sig_skips += 1
                    continue
            new_cf = round(cur_cf * mult, 4)
            if not (0.5 <= new_cf <= 1.5):  # safety
                continue
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or cfx_added >= cfx_max_specs:
                    break
                try:
                    code = _make_spec(etf, {'cf': new_cf}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_CFX_{etf}_{axis_name}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'CFX {etf} cf={new_cf}',
                                     rb.based_on, 1))
                    rb._spec_hashes.add(h)
                    cfx_added += 1
                except Exception:
                    pass
    print(f'CFX probes (baked-cf iteration, NEW 2026-05-14): {cfx_added} specs '
          f'(destructive={cfx_destructive_skips} noop-sig={cfx_noop_sig_skips} '
          f'dead-pair={cfx_dead_pair_skips})')

    # SFX block 2026-05-14: sf (slip factor) iteration. 235/311 ETFs have sf.
    _SFX_AXES_POOL = [('sf_grow_105pct', 1.05), ('sf_shrink_95pct', 0.95),
                      ('sf_grow_110pct', 1.10), ('sf_shrink_90pct', 0.90)]
    _sfx_off = R % len(_SFX_AXES_POOL)
    SFX_AXES = _SFX_AXES_POOL[_sfx_off:] + _SFX_AXES_POOL[:_sfx_off]
    sfx_start = (R * 8) % max(1, len(bti_pool_xx))
    sfx_slice = (bti_pool_xx[sfx_start:] + bti_pool_xx[:sfx_start])[:6]
    sfx_max_specs = 2  # 2026-05-18 R3740 30m: 0 pos / 32 specs / last 50 rounds (100% silent). Cut 4→2. Save 2 specs/round for UTNT/BTI.
    sfx_added = 0
    sfx_destructive_skips = 0
    sfx_noop_sig_skips = 0
    sfx_dead_pair_skips = 0
    for etf in sfx_slice:
        if rb.remaining <= 0 or sfx_added >= sfx_max_specs:
            break
        m = _re.search(rf"'{etf}':\{{[^}}]*?'sf':\s*([\d.]+)", rb.base)
        if not m:
            continue
        cur_sf = float(m.group(1))
        for axis_name, mult in SFX_AXES:
            if rb.remaining <= 0 or sfx_added >= sfx_max_specs:
                break
            ax_parts = axis_name.rsplit('_', 1)
            if len(ax_parts) == 2:
                ax_prefix, val_lbl = ax_parts
                if (etf, ax_prefix, val_lbl) in rb._catastrophic_cells:
                    sfx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._destructive_cells:
                    sfx_destructive_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._noop_sigs:
                    sfx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix, val_lbl) in rb._quasi_noop_cells:
                    sfx_noop_sig_skips += 1
                    continue
                if (etf, ax_prefix) in rb._dead_pairs:
                    sfx_dead_pair_skips += 1
                    continue
                if (ax_prefix, val_lbl) in rb._dead_axis_values:
                    sfx_noop_sig_skips += 1
                    continue
            new_sf = round(cur_sf * mult, 4)
            if not (0.5 <= new_sf <= 1.5):
                continue
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or sfx_added >= sfx_max_specs:
                    break
                try:
                    code = _make_spec(etf, {'sf': new_sf}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_SFX_{etf}_{axis_name}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'SFX {etf} sf={new_sf}',
                                     rb.based_on, 1))
                    rb._spec_hashes.add(h)
                    sfx_added += 1
                except Exception:
                    pass
    print(f'SFX probes (baked-sf iteration, NEW 2026-05-14): {sfx_added} specs '
          f'(destructive={sfx_destructive_skips} noop-sig={sfx_noop_sig_skips} '
          f'dead-pair={sfx_dead_pair_skips})')

    # UTNT block moved to run BEFORE STX/WTX/CFX/SFX (after NEWLEV) 2026-05-15.
    # Original location preserved for grep history; body removed.

    # UTNT-WT block (2026-05-10): tp-axis pool exhaustion — expand to wt lever
    # Hypothesis: every baked ETF has tuned wt; safe band [0.020, 0.069]
    # Test wt_grow_125pct + wt_shrink_75pct on same untuned pool to triple
    # exploration surface. Skip if resulting wt outside safe band.
    UTNT_WT_AXES = [
        ('wt_grow_125pct', 1.25),   # boost wt within cap
        ('wt_shrink_75pct', 0.75),  # reduce wt
    ]
    WT_MIN, WT_MAX = 0.020, 0.069
    utnt_wt_added = 0
    utnt_wt_max = 0  # DISABLED 2026-05-10 — R2736 produced 21/27 NEGATIVE specs (78% catastrophic). wt mutation on untuned ETFs is destructive — wt is already-implicit-tuned even on "untuned" ETFs since base config matters.
    for etf in untuned_slice:
        if rb.remaining <= 0 or utnt_wt_added >= utnt_wt_max:
            break
        m = _re.search(rf"'{etf}':\{{[^}}]*?'wt':\s*([\d.]+)", rb.base)
        if not m:
            continue
        cur_wt = float(m.group(1))
        for axis_name, mult in UTNT_WT_AXES:
            if rb.remaining <= 0 or utnt_wt_added >= utnt_wt_max:
                break
            new_wt = round(cur_wt * mult, 4)
            if not (WT_MIN <= new_wt <= WT_MAX):
                continue  # skip if outside safe band
            for i, salt in enumerate(rb.salts[:3], 1):
                if rb.remaining <= 0 or utnt_wt_added >= utnt_wt_max:
                    break
                try:
                    code = _make_spec(etf, {'wt': new_wt}, salt, rb.base)
                    if code is None:
                        continue
                    h = _codehash(code)
                    if h in rb._noop_hashes or h in rb._spec_hashes:
                        continue
                    nm = f's002_UTNTW_{etf}_{axis_name}_rv{i}_{rb.batch}'
                    rb.specs.append((nm, code, f'UTNTW {etf} wt={new_wt}',
                                     rb.based_on, 2))
                    rb._spec_hashes.add(h)
                    utnt_wt_added += 1
                except Exception:
                    pass
    print(f'UTNT-WT probes (wt axis expansion): {utnt_wt_added} specs')

    # WORKFLOW RECONSTRUCTED 2026-05-10: replace cohort-rotation blocks
    # (DIV/DV2/DV3/FILL) with PROD block — direct iteration over
    # historically-productive (etf, axis) pairs. Every spec targets a
    # known-responsive cell at a fresh value_idx. No random axis selection.
    from round_lib import (db_productive_etfs, db_destructive_etf_axis,
                            db_productive_etf_axis, productive_axis_probes)
    PRODUCTIVE = db_productive_etfs()
    DEAD_AXIS_PAIRS = db_destructive_etf_axis()
    PROD_AXIS_PAIRS = db_productive_etf_axis()

    # PROD block DISABLED 2026-05-18 R3654 30m audit: 0 positives across 133
    # lifetime specs. value_indices=(0,1,2) maps to tp_grow_150pct/120pct/180pct
    # and tp_shrink_60pct/50pct/70pct — extreme magnitudes that always destroy
    # already-baked-tp ETFs. BAKE-217 iwb was attributed to PROD in code comments
    # but DB shows 0 PROD bakes ever. Frees 1 spec/round for productive blocks.
    prod_probes = []  # disabled
    # rb.add_probes(prod_probes, salts=rb.salts[:3], prio=2, prefix='PROD')
    print(f'PROD: DISABLED ({len(PROD_AXIS_PAIRS)} productive pairs scanned but block off)')

    # TIER-2: untouched-axis-on-productive-ETF — productive ETFs at axes
    # they haven't been tested on yet. Meaningful because the ETF is
    # T2 DISABLED 2026-05-18 R3660 30m audit: 6 specs / 5 catastrophic (83%
    # cata rate) / 0 positives lifetime. Same extreme-magnitude problem as
    # PROD — productive_axis_probes value_indices=(0,1,2) maps to
    # tp_grow_150/120/180pct and tp_shrink_60/50/70pct which destroy
    # productive ETFs at fresh axes. R3658 gwx tp_grow_120/150 = 3 cata,
    # R3660 xrt expected similar. 0 historical bake contribution.
    tier2_probes = []  # disabled

    # TIER-3: extra salts on PROD probes (cross-validation, 4-6th salts)
    if rb.remaining > 0 and len(rb.salts) >= 6:
        rb.add_probes(prod_probes, salts=rb.salts[3:6], prio=3, prefix='T3')
        print(f'T3: extra-salt cross-validation on PROD pairs')

    # TIER-4: extra salts on T2 probes
    if rb.remaining > 0 and len(rb.salts) >= 6:
        rb.add_probes(tier2_probes, salts=rb.salts[3:6], prio=4, prefix='T4')
        print(f'T4: extra-salt cross-validation on T2 pairs')

    # TIER-5: extra salts on PROD if still short
    if rb.remaining > 0:
        extra_salts = [(R * 31 + i * 17 + 1234) for i in range(10)]
        rb.add_probes(prod_probes, salts=extra_salts[:rb.remaining // max(len(prod_probes), 1) + 1],
                      prio=4, prefix='T5')
        print(f'T5: extended-salt PROD cross-validation')

    # TIER-6: extra salts on T2 (cross-validation on cross-axis)
    if rb.remaining > 0:
        extra_salts2 = [(R * 53 + i * 23 + 5678) for i in range(15)]
        rb.add_probes(tier2_probes, salts=extra_salts2[:rb.remaining // max(len(tier2_probes), 1) + 1],
                      prio=4, prefix='T6')
        print(f'T6: extended-salt T2 cross-validation')

    # TIER-7: many extra salts on ALL meaningful probes (BTI/PROD/T2 combined)
    if rb.remaining > 0:
        from round_lib import codehash
        all_meaningful = list(prod_probes) + list(tier2_probes)
        extra_salts3 = [(R * 71 + i * 29 + 9999) for i in range(40)]
        for salt_batch in range(0, 40, 3):
            if rb.remaining <= 0: break
            rb.add_probes(all_meaningful, salts=extra_salts3[salt_batch:salt_batch+3],
                          prio=5, prefix='T7')
        print(f'T7: emergency salt expansion to maintain 32 invariant')

    # EMERGENCY-FILL 2026-05-19: when PROD/T2 disabled, T5-T7 are no-ops.
    # If shortfall persists, cycle UTNT_AXES through 2nd-axis per untuned ETF
    # to honor 16-meaningful invariant. Pulls fresh (etf, tp_axis) cells past
    # the standard 1-axis-per-ETF cap. Still respects all filters.
    if rb.remaining > 0 and untuned_slice and UTNT_AXES:
        emergency_added = 0
        emergency_target = rb.remaining
        # Use later salts to avoid collision with primary UTNT
        emrg_salts = [(R * 89 + i * 37 + 4321) for i in range(6)]
        # 2026-05-19 R3805 fix: track (etf, axis_name) cells already used by
        # primary UTNT block to avoid duplicating same cell with fresh salts
        # (R3805 djp_tp_shrink_80pct got 6 specs — 3 UTNT + 3 EMRG).
        utnt_used_cells = set()
        for nm, _, _, _, _ in rb.specs:
            m = _re.match(r's002_UTNT_([a-z0-9]+)_(tp_(?:grow|shrink)_\d+pct)_', nm)
            if m:
                utnt_used_cells.add((m.group(1), m.group(2)))
        for etf in untuned_slice:
            if rb.remaining <= 0 or emergency_added >= emergency_target:
                break
            m = _re.search(rf"'{etf}':\{{[^}}]*?'tp':\s*([\d.]+)", rb.base)
            if not m:
                continue
            cur_tp = float(m.group(1))
            if (etf, 'tp') in rb._destr_etf_axes:
                continue
            # Cycle through ALL axes (including primary's first); skip the
            # ones already used by primary UTNT for this ETF.
            for axis_name, mult in UTNT_AXES:
                if rb.remaining <= 0 or emergency_added >= emergency_target:
                    break
                if (etf, axis_name) in utnt_used_cells:
                    continue
                ax_parts = axis_name.rsplit('_', 1)
                if len(ax_parts) == 2:
                    ax_prefix, val_lbl = ax_parts
                    if (etf, ax_prefix, val_lbl) in rb._catastrophic_cells:
                        continue
                    if (etf, ax_prefix, val_lbl) in rb._destructive_cells:
                        continue
                    if (etf, ax_prefix, val_lbl) in rb._noop_sigs:
                        continue
                    if (etf, ax_prefix, val_lbl) in rb._quasi_noop_cells:
                        continue
                    if (etf, ax_prefix) in rb._dead_pairs:
                        continue
                    if (ax_prefix, val_lbl) in rb._dead_axis_values:
                        continue
                new_tp = round(cur_tp * mult, 4)
                added_this_axis = 0
                for i, salt in enumerate(emrg_salts[:3], 1):
                    if rb.remaining <= 0 or emergency_added >= emergency_target:
                        break
                    try:
                        code = _make_spec(etf, {'tp': new_tp}, salt, rb.base)
                        if code is None:
                            continue
                        h = _codehash(code)
                        if h in rb._noop_hashes or h in rb._spec_hashes:
                            continue
                        nm = f's002_EMRG_{etf}_{axis_name}_rv{i}_{rb.batch}'
                        rb.specs.append((nm, code, f'EMRG {etf} tp={new_tp}',
                                         rb.based_on, 3))
                        rb._spec_hashes.add(h)
                        emergency_added += 1
                        added_this_axis += 1
                    except Exception:
                        pass
                if added_this_axis > 0:
                    utnt_used_cells.add((etf, axis_name))
                    break  # one axis per ETF in emergency too
        print(f'EMRG fill: {emergency_added} specs (NEW (etf,axis) cells only)')

    if rb.remaining > 0:
        print(f'⚠ shortfall: {rb.remaining} slots after EMRG — '
              f'true saturation. Strategy redesign needed.')

    print(f'\nTotal specs: {len(rb.specs)}')
    print(f'Composition: {rb.composition()}')
    if rb.n_skipped_dead:
        print(f'Dead-pair skips: {rb.n_skipped_dead}')
    if rb.n_skipped_behavioral_noop:
        print(f'Behavioral-noop skips: {rb.n_skipped_behavioral_noop}')
    if rb.n_skipped_dead_pair:
        print(f'Dead-axis-pair skips: {rb.n_skipped_dead_pair}')
    if rb.n_skipped_destructive:
        print(f'Destructive-cell skips: {rb.n_skipped_destructive}')
    if rb.n_skipped_axis_noop:
        print(f'Axis-NOOP skips: {rb.n_skipped_axis_noop}')
    if rb.n_skipped_axis_destr:
        print(f'Axis-DESTRUCTIVE skips: {rb.n_skipped_axis_destr}')

    if args.dry_run:
        print('\n--- first 12 specs ---')
        for nm, *_ in rb.specs[:12]:
            print(' ', nm)
        return 0

    ins, skp = rb.queue()
    print(f'queued={ins}, skipped={skp}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
