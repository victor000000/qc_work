"""S001 diagnostics — bake detection, cohort firing oracle, poison-mag registry.

Closes the workflow gap exposed when BAKE-WH-R1650 (+0.00287) was missed
for a full /loop tick. Run propose_bakes() at the START of every round
generation; AuditFailed-style halt if eligible bakes are unbaked.
"""
from __future__ import annotations

from s001.paths import WORKSPACE_ROOT, DATA_DIR
import qc_storage as storage, statistics, re
from pathlib import Path

DB_PATH = str(DATA_DIR / 'S001.duckdb')
BASE_PATH = str(WORKSPACE_ROOT / 'strategies/s001/s001_20260628_base.py')
BAKE_THRESHOLD = 0.0005  # 2026-05-10: lowered from 0.0007 (user directive); gated by multi-mag confirmation
BAKE_THRESHOLD_NO_CONFIRM = 0.001  # threshold when multi-mag NOT confirmed (variance risk)
POISON_TOLERANCE = -0.0015  # consider a mag "poison" if it hurt by this much
# QC infrastructure variance floor (added 2026-05-10): R1851/R1852 measured
# 0.00447-0.00457 spread between NOOP branches. This is an infrastructure-
# level noise that persists across base versions. Any single-mag candidate
# at delta < this + 0.0005 is suspect — likely matching the high branch
# while NOOPs sampled low (or vice versa). Multi-mag confirmation overrides.
VARIANCE_FLOOR = 0.0070  # 2026-05-14: raised from 0.0046 — R2181-R2186 bimodal
# variance widened to 0.00628 spread; need 0.007+ to safely clear band.


# ---------- NOOP tracking ----------

def round_noop(rid: int, db_path: str = DB_PATH) -> tuple[float | None, int | None, int]:
    """Return (median car_mdd, orders, n) for round's NOOPs.

    2026-05-13 fix: switched from mean→median + outlier filter. R2056/R2057
    had partial-write corruption (base.py modified mid-round) → catastrophic
    NOOPs at 0.86/0.98 (90% portfolio loss). Mean was skewed (2.77/2.94)
    causing propose_bakes to falsely compute large positive deltas.
    """
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT car_mdd, total_orders FROM experiments
                   WHERE name LIKE ? AND name LIKE '%NOOP%' AND car_mdd IS NOT NULL""",
                (f'S001_R{rid}_lp_%',))
    rows = cur.fetchall(); con.close()
    if not rows: return (None, None, 0)
    cms = [r[0] for r in rows]
    med = statistics.median(cms)
    # Filter outliers: drop NOOPs > 30% below median (catastrophic crashes from
    # partial-write base corruption). Keep all NOOPs within 30% of median.
    kept = [(cm, to) for cm, to in rows if cm >= med * 0.70]
    if not kept:
        return (med, rows[0][1], len(rows))
    return (statistics.median(r[0] for r in kept), kept[0][1], len(kept))


def latest_noop_baseline(db_path: str = DB_PATH) -> float | None:
    """Find the most recent round's NOOP avg as the live baseline."""
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name, car_mdd FROM experiments
                   WHERE name LIKE 'S001_R%_lp_NOOP_%' AND car_mdd IS NOT NULL
                   ORDER BY id DESC LIMIT 32""")
    by_rid: dict[int, list[float]] = {}
    for name, cm in cur.fetchall():
        m = re.match(r'S001_R(\d+)_', name)
        if m: by_rid.setdefault(int(m.group(1)), []).append(cm)
    con.close()
    if not by_rid: return None
    latest = max(by_rid)
    return statistics.mean(by_rid[latest])


# ---------- bake proposal ----------

def parse_axis_from_name(name: str, rid: int) -> tuple[str, str]:
    """S001_R{rid}_lp_{axis}_{tag} -> (axis, tag). Tag is 'm125', 'a10', 'a-50' etc.
    Axis names may contain underscores (e.g. 'ISO_FG'); tag is the last
    `_a-?\\d+` or `_m-?\\d+` segment (negative tags from R1840+ entry_score_gate)."""
    bare = name.replace(f'S001_R{rid}_lp_', '')
    m = re.match(r'^(.+)_([am]-?\d+)$', bare)
    if m:
        return (m.group(1), m.group(2))
    # No mag suffix (skip-style probe with mags=(0,) → tag empty)
    return (bare, '')


def parse_mag(tag: str) -> tuple[str, float] | None:
    """Tag 'm125' -> ('*=', 1.25); 'a10' -> ('+=', 0.010); 'a-100' -> ('+=', -0.100)."""
    m = re.match(r'm(-?\d+)$', tag)
    if m: return ('*=', int(m.group(1)) / 100)
    m = re.match(r'a(-?\d+)$', tag)
    if m: return ('+=', int(m.group(1)) / 1000)
    return None


def _multi_mag_check(rid: int, axis: str, candidate_op: str, candidate_mag: float,
                      candidate_delta: float, all_rows: list, noop_cm: float,
                      noop_orders: int) -> bool:
    """Check if `axis` has multiple mags producing positive monotonic lift.

    Returns True if at least 2 mags of this axis (including the candidate)
    show delta > 0 with monotonic relationship to mag value. This guards
    against variance-borderline single-mag hits (e.g., FE_a20 hit but
    FE_a40 was -0.011 → variance, NOT a true bake).
    """
    # Collect all mag results for this axis
    by_mag: dict[float, float] = {}
    for row in all_rows:
        name, cm, to = row[0], row[1], row[2]
        m = re.match(rf'S001_R{rid}_lp_(.+)$', name)
        if not m: continue
        bare = m.group(1)
        ax_m = re.match(r'^(.+)_([am]-?\d+)$', bare)
        if not ax_m or ax_m.group(1) != axis: continue
        opmag = parse_mag(ax_m.group(2))
        if not opmag or opmag[0] != candidate_op: continue
        by_mag[opmag[1]] = cm - noop_cm
    # Multi-mag confirmed if ≥2 mags positive AND not single-mag-only spike
    pos_mags = [m for m, d in by_mag.items() if d > 0]
    if len(pos_mags) < 2: return False

    # 2026-05-12 ADJACENT-MONOTONIC filter: require ≥2 positive mags to be
    # ADJACENT when sorted by "magnitude depth" (no negative-delta mag between).
    # R2029 evidence: C_SD m65=+0.00298 / m75=-0.00404 / m80=-0.00064 / m85=+0.00319.
    # Old filter passed it (2 positive). New filter rejects: m65 and m85 are
    # NOT adjacent (m75/m80 between them are negative). Non-monotonic = variance.
    def _depth(op: str, mag: float) -> float:
        """Sort-key for magnitude depth (greater = more aggressive)."""
        if op == '*=':
            return abs(1.0 - mag)  # demote distance from 1.0
        return abs(mag)  # additive: raw abs
    sorted_by_depth = sorted(by_mag.keys(), key=lambda m: _depth(candidate_op, m))
    # Find candidate in sorted order; look for ≥2 adjacent positives including it.
    deltas_in_order = [(m, by_mag[m]) for m in sorted_by_depth]
    has_adjacent_pos = False
    for i, (m, d) in enumerate(deltas_in_order):
        if d <= 0:
            continue
        # Check if neighbor (left or right in depth order) is also positive
        left_pos = i > 0 and deltas_in_order[i-1][1] > 0
        right_pos = i < len(deltas_in_order)-1 and deltas_in_order[i+1][1] > 0
        if left_pos or right_pos:
            has_adjacent_pos = True
            break
    if not has_adjacent_pos:
        return False

    # Check no catastrophic-negative at adjacent mag.
    # 2026-05-11 refinement (deep review R1957): only check catastrophic
    # neighbors AT OR INSIDE the candidate's mag range. Hyper-sensitive
    # levers (e.g., entry_score_gate at mag -0.05 productive, -0.15 destructive)
    # have a SMALL productive region — large mags beyond candidate going
    # catastrophic doesn't invalidate the productive small-mag bake.
    # Rule: if candidate is at mag M (in absolute value), only catastrophic
    # mags with |mag| <= |M| invalidate. Larger |mags| are out-of-region.
    # 2026-05-12 FIX: in-region must use DEPTH (more aggressive direction),
    # not raw abs. For *= ops, smaller raw value = more aggressive demote.
    # Previously in-region check included m88 as "below" m92 by raw abs;
    # but m88 is actually MORE aggressive — adjacent mags going LESS
    # aggressive (m94) are the safety buffer. Use _depth defined above.
    candidate_depth = _depth(candidate_op, candidate_mag)
    # Sort by depth ascending (less aggressive → more aggressive).
    sorted_mags = sorted(by_mag.keys(), key=lambda m: _depth(candidate_op, m))
    # in-region = mags with depth ≤ candidate's, plus 1 deeper as safety
    safety_idx = next((i for i, m in enumerate(sorted_mags)
                       if _depth(candidate_op, m) > candidate_depth),
                      len(sorted_mags))
    in_region_mags = sorted_mags[:safety_idx + 1]
    for m in in_region_mags:
        if by_mag[m] < -0.005: return False

    # 2026-05-12 REVERTED tightening: ADJACENT-MONOTONIC filter above already
    # catches V-shape variance (R2029 C_SD). R2033 SD_QZERO_S308_HD3_VF_1
    # m91=+0.00202 is REAL — m85/m88 byte-identical fingerprint (same trade
    # set, "no-op demote zone"), m91/m94 both positive (adjacent). Cliff
    # check at -0.002 over-rejected. Keep -0.005 as the catastrophic floor.

    # 2026-05-14 NOOP-VARIANCE GUARD: R2181-R2183 audit revealed QC bimodal
    # variance (±0.00628 between cm branches). When probe cm values lock to
    # the same bimodal values as NOOPs, the probe is NOT actually changing
    # behavior — the "lift" is just hitting the lucky variance branch.
    # Reject if ≥80% of positive mags' cm values match a NOOP cm value.
    import qc_storage as _sql
    _con = _sql.connect(DB_PATH)
    noop_rows = _con.execute(
        "SELECT car_mdd, total_orders FROM experiments WHERE name LIKE ? AND car_mdd IS NOT NULL",
        (f'S001_R{rid}_lp_NOOP%',)).fetchall()
    noop_cms = {round(r[0], 5) for r in noop_rows}
    noop_orders_set = {r[1] for r in noop_rows if r[1] is not None}
    # 2026-05-14 HISTORICAL-VARIANCE EXTENSION: include NOOP cm values from
    # last 10 rounds. R2191 showed all NOOPs at low branch (3.47064), but
    # probes landed at OLD high branch (3.47691) producing +0.00627
    # "lifts" — pure historical variance, not real signal.
    hist_rows = _con.execute(
        "SELECT DISTINCT car_mdd FROM experiments WHERE name LIKE 'S001_R%_lp_NOOP_%' "
        "AND car_mdd IS NOT NULL ORDER BY id DESC LIMIT 64"
    ).fetchall()
    hist_noop_cms = {round(r[0], 5) for r in hist_rows}
    noop_cms |= hist_noop_cms  # Union with historical NOOP values
    if len(noop_cms) >= 2:  # only check when variance present
        # Get cm + orders for positive mags
        all_rows_for_axis = []
        for row in all_rows:
            nm, cm = row[0], row[1]
            orders = row[2] if len(row) > 2 else None
            m_match = re.match(rf'S001_R{rid}_lp_(.+)$', nm)
            if not m_match: continue
            ax_m = re.match(r'^(.+)_([am]-?\d+)$', m_match.group(1))
            if not ax_m or ax_m.group(1) != axis: continue
            opmag = parse_mag(ax_m.group(2))
            if opmag and opmag[0] == candidate_op:
                all_rows_for_axis.append((opmag[1], cm, orders))
        pos_data = [(round(cm, 5), o) for mag, cm, o in all_rows_for_axis
                    if cm - noop_cm > 0]
        if pos_data:
            # Rule A: cm near a NOOP variance value (within 0.0002 tolerance)
            # 2026-05-14: relaxed exact-match to fuzzy match — R2187 showed
            # probe cm=3.476808 hit ~0.00011 below NOOP-high 3.476914 (within
            # variance band). Exact match missed it.
            def _near_noop(cm):
                return any(abs(cm - n) < 0.0002 for n in noop_cms)
            locked_count = sum(1 for cm, _ in pos_data if _near_noop(cm))
            locked_pct = locked_count / len(pos_data)
            if locked_pct >= 0.8:
                return False  # variance artifact, not real signal

            # Rule B: orders identical to NOOP for ALL positive mags
            # (probe didn't fire — cm difference is pure QC noise)
            if noop_orders_set:
                silent_count = sum(1 for _, o in pos_data
                                   if o is not None and o in noop_orders_set)
                if silent_count == len(pos_data) and len(pos_data) >= 2:
                    return False  # silent probe under variance

            # Rule B2 (2026-05-14): mixed silent+near-NOOP positive mags.
            # If ANY positive mag has orders==NOOP AND cm near NOOP, the
            # cohort contains variance-contaminated mags. Reject unless
            # ≥3 OTHER positive mags have non-NOOP orders AND non-near-NOOP cm.
            if noop_orders_set:
                clean_count = 0
                contaminated_count = 0
                for cm, o in pos_data:
                    is_silent = o is not None and o in noop_orders_set
                    is_near = _near_noop(cm)
                    if is_silent and is_near:
                        contaminated_count += 1
                    elif not is_silent and not is_near:
                        clean_count += 1
                if contaminated_count > 0 and clean_count < 3:
                    return False  # variance-contaminated axis

            # Rule C (2026-05-14): REPLICATE-VERIFY guard.
            # If axis has a sibling (same lever + cohort, suffix _V1/_V2 or
            # _R1/_R2) and the sibling DISAGREES at the candidate's mag,
            # the cm difference is QC variance, not real probe effect.
            # Look up sibling axes by cohort identity (extracted from rows).
            cur_cohort_pattern = None
            for row in all_rows:
                nm = row[0]
                if axis in nm and len(row) > 2:
                    # Find matching probe — use partial cohort matching
                    pass
            sibling_suffixes = ['_V2', '_V1', '_R1', '_R2']
            cand_base_axis = axis
            for sfx in sibling_suffixes:
                if axis.endswith(sfx):
                    cand_base_axis = axis[:-len(sfx)]
                    break
            if cand_base_axis != axis:
                # Find sibling axes
                sibling_axes = set()
                for row in all_rows:
                    nm = row[0]
                    m_match = re.match(rf'S001_R{rid}_lp_(.+)$', nm)
                    if not m_match: continue
                    ax_m = re.match(r'^(.+)_([am]-?\d+)$', m_match.group(1))
                    if not ax_m: continue
                    ax_name = ax_m.group(1)
                    if ax_name == axis: continue
                    for sfx in sibling_suffixes:
                        if ax_name == cand_base_axis + sfx:
                            sibling_axes.add(ax_name)
                            break
                # Check sibling cm values at same mag as candidate
                cand_mag_cm = None
                for r in all_rows:
                    nm = r[0]
                    if axis in nm:
                        ax_m = re.match(rf'S001_R{rid}_lp_(.+)_([am]-?\d+)$', nm)
                        if ax_m and ax_m.group(1) == axis:
                            opmag2 = parse_mag(ax_m.group(2))
                            if opmag2 and opmag2[1] == candidate_mag:
                                cand_mag_cm = round(r[1], 5)
                                break
                disagree_count = 0
                for sib_ax in sibling_axes:
                    for r in all_rows:
                        nm = r[0]
                        ax_m = re.match(rf'S001_R{rid}_lp_(.+)_([am]-?\d+)$', nm)
                        if ax_m and ax_m.group(1) == sib_ax:
                            opmag2 = parse_mag(ax_m.group(2))
                            if opmag2 and opmag2[1] == candidate_mag:
                                sib_cm = round(r[1], 5)
                                if cand_mag_cm and abs(sib_cm - cand_mag_cm) > 0.002:
                                    disagree_count += 1
                                break
                if disagree_count > 0:
                    return False  # replicate disagreement = variance

    return True


def propose_bakes(rid: int, threshold: float = BAKE_THRESHOLD,
                  no_confirm_threshold: float = BAKE_THRESHOLD_NO_CONFIRM,
                  db_path: str = DB_PATH) -> list[dict]:
    """Return bake-eligible probes from a completed round.

    Two-tier threshold:
      - delta ≥ no_confirm_threshold (default 0.001): always eligible
      - threshold ≤ delta < no_confirm_threshold (0.0007-0.001): eligible only
        if multi-mag confirmed (axis has ≥2 mags with positive delta and no
        catastrophic adjacent mag)

    This captures real but variance-borderline lifts while filtering noise.

    Each item: {axis, tag, op, mag, delta, name, orders, multi_mag_confirmed}.
    Sorted by delta descending. Caller must look up cohort/lever from gen
    script (this layer is stateless on the script structure).

    Falls back to latest available NOOP across rounds if current round's
    NOOPs haven't run yet (queue order may push NOOPs to the end).
    """
    noop_cm, noop_orders, n_noop = round_noop(rid, db_path)
    # EARLY-INVOCATION GUARD (2026-05-12, post-R2026 false-positive):
    # If THIS round's NOOPs haven't all completed yet, do NOT fall back
    # to prior-round NOOPs — that path used 3.40489 to evaluate R2026
    # results which were actually measured against 3.40734, producing
    # 8 false-positive +0.00245 candidates that were all silent-NOOP-
    # fingerprint matches.
    # 2026-05-15 fix: gen scripts use noops=4, floor 3 = 75% of 4-NOOP.
    # 2026-05-18 fix: user reduced noops=1 (16-spec budget). Floor must
    # match: with noops=1, n_noop>=1 means round NOOP is in. NOOP-
    # fingerprint variance filter downstream still catches false positives.
    # Without this patch, propose_bakes returned [] for ALL recent rounds
    # forcing manual bake applies (BAKE-32/33/34 all manual).
    if noop_cm is None or n_noop < 1:
        return []
    # Sanity check: drop only TRULY broken bases (NOOP near 0).
    # Updated 2026-05-09 v2: user accepted new diminished-legacy regime
    # (NOOP ~0.577 baseline). Set floor at 0.3 — only rejects fully-broken
    # (R1715 NOOP=0.0 territory) while allowing the diminished regime to
    # propose bakes.
    if noop_cm < 0.3:
        return []  # fully broken base; skip bake proposals
    con = storage.connect(db_path); cur = con.cursor()
    # Base-mtime invalidation: if the round was QUEUED before the most recent
    # base modification, its results are measured against an obsolete code
    # path. Skip bake proposals for stale rounds — re-test against new base.
    import os as _os
    base_mtime = _os.path.getmtime(BASE_PATH)
    cur.execute("""SELECT MIN(submitted_at) FROM backtest_queue
                   WHERE name LIKE ?""", (f'S001_R{rid}_lp_%',))
    submitted_row = cur.fetchone()
    if submitted_row and submitted_row[0]:
        import datetime as _dt
        # SQLite datetime('now') stores naive UTC. fromisoformat parses as
        # naive datetime; .timestamp() then interprets as LOCAL TIME (BUG).
        # Force UTC interpretation by attaching tzinfo before timestamp().
        try:
            sub_dt = _dt.datetime.fromisoformat(submitted_row[0]).replace(
                tzinfo=_dt.timezone.utc)
            sub_ts = sub_dt.timestamp()
            if base_mtime > sub_ts + 60:  # base modified after queue
                # 2026-05-11 patch: only stale if the base modification came
                # from a DIFFERENT round's bake. If the only post-submission
                # bakes are from THIS rid itself, the remaining R{rid} probes
                # are still valid against their original base. Inspect
                # bakes.json for applied_at timestamps post-sub_ts.
                log = _load_bake_log()
                foreign_post_sub = False
                for entry in log:
                    if entry.get('rid') == rid:
                        continue
                    applied_at = entry.get('applied_at')
                    if not applied_at:
                        continue
                    try:
                        ap_dt = _dt.datetime.fromisoformat(applied_at)
                        if ap_dt.tzinfo is None:
                            ap_dt = ap_dt.replace(tzinfo=_dt.timezone.utc)
                        if ap_dt.timestamp() > sub_ts + 60:
                            foreign_post_sub = True
                            break
                    except Exception:
                        pass
                if foreign_post_sub:
                    con.close()
                    return []  # round is stale; results pending re-test
                # else: only this rid's own bakes triggered the mtime bump;
                # remaining probes still valid.
        except Exception:
            pass
    cur.execute("""SELECT name, car_mdd, total_orders, end_equity FROM experiments
                   WHERE name LIKE ? AND name NOT LIKE '%NOOP%'
                     AND name NOT LIKE '%_lp_DCY_%' AND car_mdd IS NOT NULL""",
                (f'S001_R{rid}_lp_%',))
    rows = cur.fetchall()
    # Build NOOP-fingerprint set for variance-cluster filter:
    # If a probe's (car_mdd, total_orders, end_equity) byte-matches ANY round
    # NOOP exactly, it's the same code-path as that NOOP — the lift is QC
    # variance, not a real effect.
    #
    # CROSS-ROUND fingerprint aggregation (added 2026-05-10): R1851+ rounds
    # show NOOP variance branches (+0.00457 spread between two clusters).
    # If THIS round's NOOPs only sampled one branch, but recent same-base
    # rounds sampled the other, candidates matching the other branch must
    # also be filtered. Pull NOOP fingerprints from current round + last 4
    # rounds with submitted_at >= base_mtime (same base).
    cur.execute("""SELECT name, car_mdd, total_orders, end_equity FROM experiments
                   WHERE name LIKE 'S001_R%_lp_NOOP_%' AND car_mdd IS NOT NULL
                   ORDER BY id DESC LIMIT 64""")
    candidate_noops = cur.fetchall()
    # Filter to recent rounds with same-base submission timestamps
    noop_fingerprints: set = set()
    seen_rids: set = set()
    cur.execute("""SELECT name, MIN(submitted_at) FROM backtest_queue
                   WHERE name LIKE 'S001_R%_lp_NOOP_%'
                   GROUP BY name""")
    sub_by_name = {n: s for n, s in cur.fetchall()}
    import datetime as _dt
    for name, cm, to, eq in candidate_noops:
        if cm is None or to is None or eq is None:
            continue
        # Extract rid
        m = re.match(r'S001_R(\d+)_', name)
        if not m:
            continue
        rid_n = int(m.group(1))
        # Always include current round
        if rid_n == rid:
            noop_fingerprints.add((cm, to, eq))
            seen_rids.add(rid_n)
            continue
        # Include recent rounds whose submission is post-base-mtime
        sub = sub_by_name.get(name)
        if sub:
            try:
                sub_ts = _dt.datetime.fromisoformat(sub).replace(
                    tzinfo=_dt.timezone.utc).timestamp()
                if sub_ts >= base_mtime - 60 and len(seen_rids) < 5:
                    noop_fingerprints.add((cm, to, eq))
                    seen_rids.add(rid_n)
            except Exception:
                pass
    con.close()
    # NOOP variance window — observed spread of NOOPs across same-base rounds.
    # Lifts within this window are likely variance, not real effect.
    if noop_fingerprints:
        noop_cms = [fp[0] for fp in noop_fingerprints]
        noop_variance_window = max(noop_cms) - min(noop_cms)
    else:
        noop_variance_window = 0.0

    # Build axis → all-mag-deltas index for catastrophic-neighbor check.
    # If any OTHER mag of the same axis is catastrophic (delta < -0.005),
    # the candidate is non-monotonic — likely a destructive lever where
    # small lift hides a cliff at higher magnitudes (R1702 ZSE2: a10=+0.003,
    # a20=-0.070, a40=-0.238).
    axis_mag_deltas: dict[str, list[float]] = {}
    for name, cm, to, eq in rows:
        a, t = parse_axis_from_name(name, rid)
        if a:
            axis_mag_deltas.setdefault(a, []).append(cm - noop_cm)

    bakes = []
    for name, cm, to, eq in rows:
        delta = cm - noop_cm
        if delta < threshold: continue
        # NOOP-variance filter: reject probes whose fingerprint matches any
        # round-NOOP exactly (same code-path = real lift = 0).
        if (cm, to, eq) in noop_fingerprints:
            continue
        axis, tag = parse_axis_from_name(name, rid)
        opmag = parse_mag(tag)
        # Catastrophic-neighbor filter: reject if any IN-REGION mag of this
        # axis produced delta < -0.005 (non-monotonic destructive cliff).
        # 2026-05-11 refinement (deep review R1957): only count catastrophic
        # mags AT OR INSIDE the candidate's |mag| range, not larger-mag
        # cliffs. Hyper-sensitive levers with small productive region +
        # large-mag cliff (e.g., entry_score_gate at -0.05 +0.00223 but
        # -0.15 catastrophic) are real bakes at the small mag.
        if axis in axis_mag_deltas and opmag:
            # 2026-05-12 FIX: use DEPTH not raw abs. For *= ops, raw 0.88
            # is MORE aggressive than 0.92 (deeper demote). The old
            # `abs(om2[1]) > cand_abs * 2.0` check left m88 in-region for
            # m92 candidate; m88=-0.00681 then rejected the otherwise-valid
            # m92 bake. Now in-region = mags with depth ≤ candidate's depth
            # plus a margin (i.e., similar-aggressiveness OR more aggressive
            # by no more than 50%).
            cand_op = opmag[0]
            cand_depth = abs(1.0 - opmag[1]) if cand_op == '*=' else abs(opmag[1])
            in_region_cat = False
            for r2 in rows:
                ax2, tag2 = parse_axis_from_name(r2[0], rid)
                if ax2 != axis: continue
                om2 = parse_mag(tag2)
                if not om2 or om2[0] != cand_op: continue
                m2_depth = abs(1.0 - om2[1]) if cand_op == '*=' else abs(om2[1])
                # In-region = m2_depth within [0, cand_depth * 1.5]
                # Mags much more aggressive than candidate × 1.5 are out-of-region
                if m2_depth > cand_depth * 1.5: continue
                # 2026-05-14 VARIANCE-EXCLUSION: if m2 cm matches a NOOP
                # variance branch (within 0.001), the "catastrophic" delta
                # is actually variance landing, not real cliff. Skip.
                # Wider tolerance (0.001) here because variance landings can
                # have minor offsets from exact NOOP values when probe fires.
                m2_cm = r2[1]
                noop_branches = [fp[0] for fp in noop_fingerprints]
                if any(abs(m2_cm - br) < 0.001 for br in noop_branches):
                    continue
                if (m2_cm - noop_cm) < -0.005:
                    in_region_cat = True
                    break
            if in_region_cat:
                continue
        # End-equity guard per memory s001 end_equity bake guard: reject if
        # total_orders or end_equity drops below 95% of NOOP
        if to is not None and noop_orders is not None and to < 0.95 * noop_orders:
            continue
        # Variance-window guard: if probe's orders match the variance-branch
        # NOOPs (those that diverged from majority NOOP) AND its lift is
        # smaller than the round's NOOP variance window, treat as variance.
        # (R1698: CSC_m120 orders=14858 matched variance-NOOP_4/_5 with
        # lift +0.00248 — well within window 3.21745→3.22170 = 0.00425.)
        variance_branch_orders = {fp[1] for fp in noop_fingerprints
                                  if fp[1] != noop_orders}
        if (to in variance_branch_orders
                and delta < max(noop_variance_window, BAKE_THRESHOLD)):
            continue
        # Variance-window-aware threshold (added 2026-05-10): when NOOP
        # variance branches exist (R1851+ 0.00457 spread), require delta
        # to clear the variance window even for single-mag candidates.
        # Without this, candidates landing on the high-NOOP-branch produce
        # spurious +0.00457 deltas vs LOW-NOOP-branch (R1853 false positives).
        #
        # Also apply infrastructure-level VARIANCE_FLOOR (0.0046) — even
        # when current rounds only sample one branch, prior rounds showed
        # this variance is real and persistent. Don't trust single-mag
        # below this floor.
        effective_no_confirm = max(no_confirm_threshold,
                                    noop_variance_window + BAKE_THRESHOLD,
                                    VARIANCE_FLOOR + BAKE_THRESHOLD)
        # Multi-mag confirmation gate for variance-borderline lifts
        multi_confirmed = False
        if opmag:
            multi_confirmed = _multi_mag_check(
                rid, axis, opmag[0], opmag[1], delta, rows, noop_cm, noop_orders)
        # Apply two-tier threshold:
        # - delta >= effective_no_confirm: always eligible
        # - threshold <= delta < effective_no_confirm: only if multi-mag confirmed
        if delta < effective_no_confirm and not multi_confirmed:
            continue
        # 2026-05-11 capture-ratio audit (deep review R1949):
        # *= multiplicative bakes are higher-risk. Audit of last 13 bakes:
        # 11/11 += / boost-*= bakes captured 100%, but 2/13 *= bakes
        # captured only 35% (BAKE-B_BST_S310_Q3_0 BOOST) and 59%
        # (BAKE-H_SCM_S311_HA_1 score *=). For sub-+0.001 *= bakes
        # require multi-mag confirmed AND delta ≥ +0.0008 (raise floor
        # from +0.0005 to +0.0008 specifically for *= variant).
        # 2026-05-12: relaxed from 0.0008 → 0.0006. Old floor was set
        # from R1900s-era audit (2/13 *= bakes captured 35-59%). Recent
        # *= bakes R2025/R2033/R2036/R2040 all captured 100% — old floor
        # was too conservative and blocked R2043 SD2_QZERO_S206_HD14_Q3
        # at +0.00064 (multi-mag confirmed, productive pair from R2040).
        # 2026-05-16: relaxed further to 0.0005 ONLY when multi_mag_confirmed
        # is true. R2368 productive cluster (HD14 × cash-flow-fund × dec
        # 0.5-1%) peaked at +0.000516 multi-mag-confirmed across 5 mags
        # but was blocked by the 0.0006 floor. Cluster has 0 existing
        # wt_tilt bakes in that dec band (truly virgin) so stacking risk
        # is minimal. Keep 0.0006 floor for single-mag candidates.
        if opmag and opmag[0] == '*=':
            min_required = 0.0005 if multi_confirmed else 0.0006
            if delta < min_required:
                continue
        bakes.append({
            'axis': axis, 'tag': tag, 'name': name,
            'op': opmag[0] if opmag else None,
            'mag': opmag[1] if opmag else None,
            'delta': delta, 'orders': to,
            'multi_mag_confirmed': multi_confirmed,
        })
    bakes.sort(key=lambda b: -b['delta'])
    return bakes


# ---------- cohort firing oracle ----------

def cohort_firing_history(db_path: str = DB_PATH) -> dict[str, dict]:
    """Aggregate per-axis-name firing history across all rounds.

    Returns {axis_name: {'rounds': [rid,...], 'total_specs': N, 'null': N,
                         'fired': N, 'best_delta': ±}}.

    NB: matches by axis NAME, which is what humans control in gen scripts.
    Same axis name across rounds usually means same cohort family (FA, WA, etc.).
    """
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name, car_mdd, total_orders FROM experiments
                   WHERE name LIKE 'S001_R%_lp_%' AND car_mdd IS NOT NULL""")
    rows = cur.fetchall(); con.close()
    by_round_noop = {}
    by_round_orders = {}
    for name, cm, to in rows:
        if 'NOOP' in name:
            m = re.match(r'S001_R(\d+)_', name)
            if m:
                rid = int(m.group(1))
                by_round_noop.setdefault(rid, []).append(cm)
                if rid not in by_round_orders: by_round_orders[rid] = to
    noop_avg = {r: statistics.mean(v) for r, v in by_round_noop.items()}

    by_axis: dict[str, dict] = {}
    for name, cm, to in rows:
        if 'NOOP' in name: continue
        m = re.match(r'S001_R(\d+)_lp_(.+)$', name)
        if not m: continue
        rid = int(m.group(1))
        axis = m.group(2).split('_')[0]
        if rid not in noop_avg: continue
        delta = cm - noop_avg[rid]
        slot = by_axis.setdefault(axis, {'rounds': set(), 'total_specs': 0,
                                         'null': 0, 'fired': 0,
                                         'best_delta': 0.0, 'worst_delta': 0.0})
        slot['rounds'].add(rid)
        slot['total_specs'] += 1
        if to == by_round_orders[rid] and abs(delta) < 1e-6:
            slot['null'] += 1
        else:
            slot['fired'] += 1
            if delta > slot['best_delta']: slot['best_delta'] = delta
            if delta < slot['worst_delta']: slot['worst_delta'] = delta
    for s in by_axis.values():
        s['rounds'] = sorted(s['rounds'])
    return by_axis


def poison_mags(db_path: str = DB_PATH) -> dict[float, list[str]]:
    """Return {mag: [axes_where_repeatedly_negative]} for *= mags that
    hurt across multiple rounds at same value (e.g., m=1.40)."""
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name, car_mdd, total_orders FROM experiments
                   WHERE name LIKE 'S001_R%_lp_%' AND car_mdd IS NOT NULL""")
    rows = cur.fetchall(); con.close()
    # NOOPs per round
    noop_cm: dict[int, list[float]] = {}
    for name, cm, to in rows:
        if 'NOOP' in name:
            m = re.match(r'S001_R(\d+)_', name)
            if m: noop_cm.setdefault(int(m.group(1)), []).append(cm)
    noop_avg = {r: statistics.mean(v) for r, v in noop_cm.items()}
    # mag → list of (axis, rid, delta)
    by_mag: dict[float, list[tuple[str, int, float]]] = {}
    for name, cm, to in rows:
        if 'NOOP' in name: continue
        m = re.match(r'S001_R(\d+)_lp_(.+)$', name)
        if not m: continue
        rid = int(m.group(1))
        if rid not in noop_avg: continue
        bare = m.group(2)
        # tag is last underscore-separated chunk
        chunks = bare.split('_')
        axis = chunks[0]
        tag = chunks[-1]
        opmag = parse_mag(tag)
        if not opmag or opmag[0] != '*=': continue
        delta = cm - noop_avg[rid]
        by_mag.setdefault(opmag[1], []).append((axis, rid, delta))
    poison: dict[float, list[str]] = {}
    for mag, items in by_mag.items():
        # poison if seen in ≥2 rounds AND mean delta below threshold
        if len(items) < 2: continue
        mean_d = statistics.mean(d for _, _, d in items)
        if mean_d < POISON_TOLERANCE:
            poison[mag] = sorted({a for a, _, _ in items})
    return poison


# ---------- bake application ----------

# Insert markers per lever: where to put the bake to match probe-time semantics.
# - wt_tilt bakes go right after `wt_tilt = 1.0` (base has no wt_tilt mods
#   between init and ENTRY INJECT POINT except the line-1591 case).
# - score / conv bakes go right BEFORE ENTRY INJECT POINT (after all base
#   score/conv mods, matching where probes inject).
# - petgt / stop bakes go right BEFORE EXIT INJECT POINT (after base EXIT mods).
BAKE_INSERT_AFTER_WT  = '   wt_tilt = 1.0\n'
BAKE_INSERT_BEFORE_ENTRY = '   # --- ENTRY INJECT POINT ---'
BAKE_INSERT_BEFORE_EXIT  = '   # --- EXIT INJECT POINT ---'
# Post-2026-05-09 marker — new score+= bakes route through entry_signal
# accumulator. Inserts AFTER the multiplicative tail-chain, AT the
# entry-signal aggregation point. Cleaner architecture (memory:
# feedback_s001_score_system_unified) — uses the canonical score-system
# path; gen scripts can target with lever='entry_signal'.
BAKE_INSERT_BEFORE_SIGNAL = '   # --- ENTRY SIGNAL BAKE INSERT ---'


def format_bake_patch(cohort: str, lever: str, op: str, mag: float,
                      comment: str = '') -> str:
    """Generate the python snippet to insert into base for a bake."""
    if op == '*=':
        rhs = f'{lever} *= {mag}'
    elif op == '+=':
        rhs = f'{lever} += {mag}'
    else:
        raise ValueError(f'unsupported op {op!r}')
    block = f'   # BAKE {comment}\n' if comment else '   # BAKE\n'
    block += f'   try:\n'
    block += f'    if {cohort}: {rhs}\n'
    block += f'   except: pass\n'
    return block


_SIGNAL_LEVERS = {'entry_signal', 'entry_score_mtf', 'entry_score_regime',
                   'entry_score_conv', 'entry_score_quality',
                   'entry_score_gate'}


def insert_marker_for(lever: str, inject: str = 'ENTRY') -> str:
    """Choose insertion marker based on lever/inject.

    Routing (post-2026-05-09 score-system unification, updated 2026-05-10):
    - wt_tilt              → AFTER `wt_tilt = 1.0` (early)
    - any EXIT-side        → BEFORE EXIT INJECT POINT
    - SIGNAL_LEVERS (entry_signal/_score_mtf/_regime/_conv/_quality/_gate)
                            → BEFORE ENTRY SIGNAL BAKE INSERT (post-chain;
                            matches emit() routing so probes test at same
                            position they bake at — critical for accumulators
                            R1851 entry_score_quality breakthrough)
    - score *= / score +=  → BEFORE ENTRY INJECT POINT (legacy mid-chain
                            for direct score mutation — bake search tuned there)
    """
    if lever == 'wt_tilt': return BAKE_INSERT_AFTER_WT
    if inject == 'EXIT': return BAKE_INSERT_BEFORE_EXIT
    if lever in _SIGNAL_LEVERS:
        return BAKE_INSERT_BEFORE_SIGNAL
    return BAKE_INSERT_BEFORE_ENTRY


def apply_bake_to_base(base_path: str, cohort: str, lever: str, op: str,
                       mag: float, comment: str = '', inject: str = 'ENTRY') -> str:
    """Insert bake at the lever-appropriate location. Returns patched source.
    Caller writes to disk explicitly.

    NOTE: Caller MUST use atomic write (temp + rename) — R2056/R2057
    suffered catastrophic NOOP corruption from partial reads during direct
    `Path.write_text()`. Use write_base_atomic() helper.
    """
    src = Path(base_path).read_text()
    marker = insert_marker_for(lever, inject)
    if marker not in src:
        raise RuntimeError(f'bake insert marker {marker!r} not found in {base_path}')
    patch = format_bake_patch(cohort, lever, op, mag, comment)
    if marker == BAKE_INSERT_AFTER_WT:
        return src.replace(marker, marker + patch, 1)
    # for ENTRY/EXIT markers, insert BEFORE the marker line
    return src.replace(marker, patch + marker, 1)


def write_base_atomic(base_path: str, content: str):
    """Atomic write: write to temp file, fsync, rename. Prevents partial
    reads during base modification while backtests are running.

    R2056/R2057 evidence: 5 of 15 NOOPs returned catastrophic ~0.86 cm
    (90% portfolio loss) from reading mid-write base.py. Median filter
    in round_noop handles existing data; this prevents future occurrence.
    """
    import os
    import tempfile
    base_path = str(base_path)
    base_dir = os.path.dirname(base_path)
    fd, tmp_path = tempfile.mkstemp(dir=base_dir, prefix='.base_atomic_',
                                     suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, base_path)
    except Exception:
        try: os.unlink(tmp_path)
        except OSError: pass
        raise


# ---------- P5 capture-ratio guard ----------

def capture_ratio(n_rounds: int = 3, db_path: str = DB_PATH,
                  bakes_path: str = str(WORKSPACE_ROOT / 'strategies/s001/research/bakes.json')) -> dict:
    """Compute actual / predicted capture ratio over recent bakes.

    Pulls the last `n_rounds` distinct rids from bakes.json (non-reverted)
    as the "recent" set. predicted = sum(predicted_lift). actual = NOOP shift
    from the round BEFORE the earliest recent bake to the latest completed
    round NOOP. Returns dict with `ratio`, `actual`, `predicted`, plus a
    `force_virgin` flag set True when ratio<0.6 (P5 trigger).
    """
    import json as _json
    try:
        bakes = _json.load(open(bakes_path))
    except Exception:
        return {'ratio': None, 'reason': 'bakes.json missing/unreadable',
                'force_virgin': False}
    bakes = [b for b in bakes if not b.get('reverted')]
    if not bakes:
        return {'ratio': None, 'reason': 'no active bakes',
                'force_virgin': False}

    rids_sorted = sorted({b['rid'] for b in bakes if b.get('rid')})[-n_rounds:]
    if not rids_sorted:
        return {'ratio': None, 'reason': 'no rids in bakes', 'force_virgin': False}
    earliest = rids_sorted[0]

    recent = [b for b in bakes if b.get('rid') in rids_sorted]
    predicted = sum(b.get('predicted_lift', 0) or 0 for b in recent)
    if predicted <= 0:
        return {'ratio': None, 'reason': 'predicted ≤ 0', 'force_virgin': False}

    # Actual: NOOP shift from earliest's prev_noop to latest_noop_baseline.
    # Use the earliest bake's `prev_noop` as the floor (recorded snapshot),
    # so we compare against what NOOP was BEFORE the recent bake batch.
    earliest_bake = next(b for b in recent if b.get('rid') == earliest)
    floor = earliest_bake.get('prev_noop')
    cur_noop = latest_noop_baseline(db_path)
    if floor is None or cur_noop is None:
        return {'ratio': None, 'reason': 'no NOOP anchor',
                'force_virgin': False, 'recent_count': len(recent)}

    actual = cur_noop - floor
    ratio = actual / predicted if predicted else 0.0
    return {
        'ratio': ratio,
        'actual': actual,
        'predicted': predicted,
        'recent_count': len(recent),
        'rids': rids_sorted,
        'floor_noop': floor,
        'cur_noop': cur_noop,
        # Threshold relaxed 60%→50% on 2026-05-17 30m deep-review #2.
        # Saturation era (35+ rounds 0 bakes) means nothing stacking, so
        # interference risk near zero — virgin-mode at 60% was over-strict
        # (R2531/R2532 lost 2+ axes per round to virgin-mode drops).
        'force_virgin': ratio < 0.50,
    }


def _cohort_tokens(cohort: str) -> set[str]:
    """Decompose cohort string into a set of structural tokens for
    overlap comparison. Covers: qstate, decline bands, _v/_bc/_d2_4
    buckets, sector codes, regime gates, fundamental accessors.
    """
    if not cohort:
        return set()
    toks: set[str] = set()
    # q-state
    m = re.search(r'\b(_q(?:pos|neg|zero|spos|sneg)|_qa|_qs)\b', cohort)
    if m:
        toks.add(f'qstate:{m.group(1)}')
    # decline band (rounded to 0.005)
    lo, hi = _decline_band(cohort)
    if lo is not None:
        toks.add(f'dec_lo:{round(lo*1000)//5*5/1000:.3f}')
    if hi is not None:
        toks.add(f'dec_hi:{round(hi*1000)//5*5/1000:.3f}')
    # decline buckets
    for b in re.findall(r'\b(_d2_4|_d4_8|_d6_12)\b', cohort):
        toks.add(f'decbucket:{b}')
    # _v / _bc / _capec / _haccel / _accel / _hi_cape / _hi_vol / etc.
    # Catch ALL `_word op number` AND `_word.field op number` gates so novel
    # dims don't share tokens by accident with bakes that simply lack that
    # dim. Dotted form (e.g. `_vr_z.ev_to_ebit_3_yr_avg < 15`) was missed
    # by single-word regex pre-2026-05-17 — caused R2489 ev_to_X siblings
    # to register 100% Jaccard with bake (true overlap ~80% — different
    # valuation ratio).
    for accessor, op, thr in re.findall(
            r'\b(_[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+|_[a-z][a-z0-9_]*)\s*(>=|>|<=|<|==)\s*(-?\d+(?:\.\d+)?)',
            cohort):
        # skip `decline` — already handled as banded ranges above
        if accessor == 'decline':
            continue
        # skip _secc — already handled by sector pattern
        if accessor == '_secc':
            continue
        toks.add(f'{accessor}{op}{thr}')
    # sector codes
    for s in re.findall(r'_secc\s*==\s*(\d+)', cohort):
        toks.add(f'sec:{s}')
    # regime gates (self._reg_*) — only add the generic regime token if it's
    # used as a BOOLEAN gate (no comparison). When there's an explicit
    # comparison (e.g. `self._reg_haccel > 0`), the comparison token already
    # captures the regime; double-counting inflates Jaccard overlap.
    for reg in re.findall(r'self\._reg_\w+', cohort):
        reg_name = reg.split(".")[-1]
        # Skip if this regime appears in a comparison anywhere in the cohort.
        if re.search(rf'{re.escape(reg_name)}\s*(?:>=|>|<=|<|==)', cohort):
            continue
        toks.add(f'reg:{reg_name}')
    # fundamental accessors used in _ngt/_nlt/_nfg checks
    for acc in re.findall(r'\b_(?:ngt|nlt|nrg)\(\s*([\w.]+)', cohort):
        # use last 2 path components for stability across z-suffix variants
        parts = acc.split('.')
        toks.add(f'fund:{".".join(parts[-2:])}')
    # parent gates: bare `_hi_vol` / `_hi_cape` / `_hi_iv` / `_lo_*` etc.
    # appear as boolean conditions (no comparison op, no `self.` prefix).
    # These are parent-dimension differentiators — a cohort with `_hi_vol`
    # is structurally different from one without, even if other tokens
    # match. Without this, P6 over-blocks parent-novel cohorts (R1946:
    # _hi_vol/_hi_cape × productive cells incorrectly matched non-parent
    # bakes at 67% Jaccard). Match standalone `_hi_*` / `_lo_*` words.
    parent_pat = re.compile(r'(?:^|\s|\(and\s)(_(?:hi|lo)_[a-z][a-z0-9_]*)\b(?!\s*(?:>=|>|<=|<|==))')
    for tok in parent_pat.findall(cohort):
        toks.add(f'parent:{tok}')
    # exit-side: pnl gates
    for op, val in re.findall(r'\bpnl\s*([<>])\s*(-?[\d.]+)', cohort):
        toks.add(f'pnl{op}{val}')
    return toks


def cohort_overlap(candidate_cohort: str,
                   base_path: str = BASE_PATH,
                   candidate_lever: str | None = None) -> dict:
    """Score candidate cohort's structural overlap vs each active bake.

    Computes Jaccard similarity between candidate's token set and each
    active bake's token set; returns dict with `max_overlap` (worst case)
    and `worst_label` (which bake the candidate most resembles).

    When `candidate_lever` is provided, bakes with a DIFFERENT lever are
    skipped from the overlap check entirely. Different levers operate on
    different mathematical paths (e.g. score *= vs entry_score_gate +=
    vs petgt at exit) and can co-fire on overlapping populations without
    destructive stacking. Use this to allow lever-class transfer testing
    on already-baked cohort cells.
    """
    cand_toks = _cohort_tokens(candidate_cohort)
    if not cand_toks:
        return {'max_overlap': 0.0, 'worst_label': None,
                'reason': 'candidate has no parseable tokens',
                'cand_token_count': 0}
    best_jaccard = 0.0
    best_label = None
    best_intersect: set[str] = set()
    for b in applied_bakes(base_path):
        if b.get('reverted'):
            continue
        # Lever-aware skip: only check overlap against same-lever bakes.
        if candidate_lever is not None and b.get('lever') != candidate_lever:
            continue
        bake_toks = _cohort_tokens(b['cohort'])
        if not bake_toks:
            continue
        # Sector-disjointness override (2026-05-17 30m reconstruct #3):
        # When both cohorts pin a sector via `_secc==N` AND the N values
        # differ, the populations are DISJOINT (different stock universes).
        # Without this, Jaccard treats them as 67% overlap (sharing qstate
        # /regime/band/fund tokens), incorrectly blocking sector-frontier
        # exploration after BAKE-SC_QP_S310-R2533 (R2537 lost 3+ axes to
        # this false-overlap).
        cand_secs = {t for t in cand_toks if t.startswith('sec:')}
        bake_secs = {t for t in bake_toks if t.startswith('sec:')}
        if cand_secs and bake_secs and cand_secs.isdisjoint(bake_secs):
            continue  # different sectors → disjoint populations → no overlap
        inter = cand_toks & bake_toks
        union = cand_toks | bake_toks
        jac = len(inter) / len(union) if union else 0.0
        if jac > best_jaccard:
            best_jaccard = jac
            best_label = b['label']
            best_intersect = inter
    return {
        'max_overlap': best_jaccard,
        'worst_label': best_label,
        'shared_tokens': sorted(best_intersect),
        'cand_token_count': len(cand_toks),
    }


def used_cohort_tokens(base_path: str = BASE_PATH) -> set[str]:
    """Return the union of structural tokens across all active bakes.
    Useful for picking VIRGIN tokens that won't trip P6 overlap.
    """
    out: set[str] = set()
    for b in applied_bakes(base_path):
        if b.get('reverted'):
            continue
        out |= _cohort_tokens(b['cohort'])
    return out


def virgin_token_suggestions(base_path: str = BASE_PATH) -> dict[str, list[str]]:
    """Suggest virgin tokens not yet used in any active bake.

    Returns a dict {category: [virgin_tokens]} where each category is
    qstate / decline / accel / capec / regime / sector / pnl / etc.
    Each item is a string-formatted token plus the cohort fragment that
    would generate it. Caller picks combos that pass P6.
    """
    used = used_cohort_tokens(base_path)
    cands = {
        'accel': [
            ('_accel >= 5', '_accel>=5'),
            ('_accel >= 3', '_accel>=3'),
            ('_accel >= 1', '_accel>=1'),
            ('_accel <= -1', '_accel<=-1'),
            ('_accel <= -3', '_accel<=-3'),
            ('_accel <= -5', '_accel<=-5'),
        ],
        'haccel': [
            ('_haccel == 1', '_haccel==1'),
            ('_haccel == -1', '_haccel==-1'),
            ('_haccel >= 1', '_haccel>=1'),
        ],
        'capec': [
            ('_capec >= 30', '_capec>=30'),
            ('_capec >= 25', '_capec>=25'),
            ('_capec >= 20', '_capec>=20'),
            ('_capec < 15', '_capec<15'),
        ],
        'pnl': [
            ('pnl > 0.05', 'pnl>0.05'),
            ('pnl > 0.10', 'pnl>0.10'),
            ('pnl > 0.30', 'pnl>0.30'),
            ('pnl > 0.50', 'pnl>0.50'),
            ('pnl < -0.05', 'pnl<-0.05'),
            ('pnl < -0.10', 'pnl<-0.10'),
            ('pnl < -0.20', 'pnl<-0.20'),
        ],
        'sector_v_bc': [
            ('_v >= 100', '_v>=100'),
            ('_v >= 500', '_v>=500'),
            ('_bc >= 50', '_bc>=50'),
            ('_bc >= 100', '_bc>=100'),
            ('_secc == 313', 'sec:313'),
            ('_secc == 314', 'sec:314'),
            ('_secc == 315', 'sec:315'),
            ('_secc == 316', 'sec:316'),
        ],
    }
    out: dict[str, list[str]] = {}
    for cat, items in cands.items():
        out[cat] = [expr for expr, key in items if key not in used]
    return out


def cohort_overlap_block(candidate_cohort: str, threshold: float = 0.40,
                          base_path: str = BASE_PATH,
                          candidate_lever: str | None = None) -> tuple[bool, str]:
    """Returns (blocked, message). Block when overlap >threshold.

    When `candidate_lever` is set, only same-lever bakes are checked.
    """
    res = cohort_overlap(candidate_cohort, base_path, candidate_lever)
    if res['max_overlap'] > threshold:
        return True, (f"overlap {res['max_overlap']:.0%} > {threshold:.0%} "
                      f"with {res['worst_label']}; shared tokens "
                      f"{res['shared_tokens']}")
    return False, f"overlap {res['max_overlap']:.0%} ≤ {threshold:.0%}"


def cross_lever_warning(candidate_cohort: str, candidate_lever: str,
                        candidate_mag: float | None = None,
                        base_path: str = BASE_PATH) -> dict | None:
    """Detect cross-lever interference risk.

    R2546 evidence: SC_QP_S311_HA_D12 (score lever) on cell where
    BAKE-WT_QP_S311_HA_D12-R2545 (wt_tilt) exists → CATASTROPHIC -0.01
    to -0.015 at mag 1.07/1.09.

    Triggers when:
    - Candidate lever is score-family (score/wt_tilt)
    - Some applied bake has DIFFERENT lever (the OTHER of score/wt_tilt)
      with high cohort overlap (≥70% Jaccard token match)
    - Candidate mag > 1.05 (lower mags too small to cause cata)

    Returns warning dict if risk detected, None otherwise.
    """
    if candidate_lever not in ('score', 'wt_tilt'):
        return None
    if candidate_mag is not None and candidate_mag <= 1.05:
        return None
    opposite_lever = 'wt_tilt' if candidate_lever == 'score' else 'score'
    cand_toks = _cohort_tokens(candidate_cohort)
    if not cand_toks:
        return None
    for b in applied_bakes(base_path):
        if b.get('reverted'):
            continue
        if b.get('lever') != opposite_lever:
            continue
        bake_toks = _cohort_tokens(b['cohort'])
        if not bake_toks:
            continue
        # Use sector-disjoint check (same as cohort_overlap)
        cand_secs = {t for t in cand_toks if t.startswith('sec:')}
        bake_secs = {t for t in bake_toks if t.startswith('sec:')}
        if cand_secs and bake_secs and cand_secs.isdisjoint(bake_secs):
            continue
        inter = cand_toks & bake_toks
        union = cand_toks | bake_toks
        jac = len(inter) / len(union) if union else 0.0
        if jac >= 0.70:  # high overlap = same cell, different lever
            return {
                'opposite_lever': opposite_lever,
                'bake_label': b['label'],
                'overlap': jac,
                'shared_tokens': sorted(inter),
                'msg': (f'CROSS-LEVER RISK: {candidate_lever} *= {candidate_mag} '
                        f'overlaps {jac:.0%} with {opposite_lever}-baked cell '
                        f'({b["label"]}). R2546 evidence: SC × S311 (wt_tilt baked) '
                        f'at m1.07/1.09 = -0.010 to -0.015.'),
            }
    return None


def cohort_is_virgin(candidate_cohort: str, base_path: str = BASE_PATH,
                     candidate_lever: str | None = None) -> bool:
    """A cohort is virgin if NO active bake has the same cohort string
    AND no active bake's cohort subsumes the candidate (per cohort_subsumes).

    Lever-aware (added 2026-05-10): when `candidate_lever` is supplied,
    only same-lever active bakes are considered. Different levers operate
    on different mathematical paths (matches cohort_overlap_block semantics).
    """
    candidate = (candidate_cohort or '').strip()
    if not candidate:
        return False
    for b in applied_bakes(base_path):
        if candidate_lever is not None and b.get('lever') != candidate_lever:
            continue
        applied = b['cohort'].strip()
        if candidate == applied:
            return False
        if cohort_subsumes(applied, candidate):
            return False
    return True


# ---------- /loop tick guard ----------

def applied_bakes(base_path: str = BASE_PATH) -> list[dict]:
    """Parse `# BAKE` blocks already in base. Returns list of
    {label, cohort, lever, op, mag} extracted from inserted patches.

    Captures the *first BAKE-XXX-Rnnn token* in the comment line, so
    'BAKE-FC-R1657' is recognized whether the comment says
    '# BAKE-FC-R1657: ...' or '# BAKE BAKE-FC-R1657 (...)'.

    Tolerates up to 5 intervening comment lines between marker and try:
    (BAKE-WH-R1650 has 2 placement-note comments). Negative lookahead
    prevents extra-comment match from swallowing the next BAKE marker.
    """
    src = Path(base_path).read_text()
    out = []
    pat = re.compile(
        # Anchor on a `# BAKE` marker line specifically (was `#[^\n]*\n` —
        # matched any comment, eating BAKE markers when traversing dead bake
        # code blocks).
        r'^[ \t]*#[ \t]*(?:BAKE[ \t]+)?BAKE-[A-Z0-9_]+-R\d+[^\n]*\n'
        # Allow optional intervening comment lines (excluding next BAKE).
        r'(?:[ \t]*#(?!.*BAKE-[A-Z0-9_]+-R\d)[^\n]*\n){0,5}'
        r'\s*try:\s*\n'
        r"\s*if\s+(?P<cohort>.+?):\s*"
        r'(?P<lever>\w+)\s*(?P<op>\*=|\+=)\s*(?P<mag>[\d.eE+-]+)\s*\n',
        re.MULTILINE)
    label_pat = re.compile(r'BAKE-[A-Z0-9_]+-R\d+')
    for m in pat.finditer(src):
        # find label token in the marker line
        marker_line = src[m.start():src.index('\n', m.start())]
        labels = label_pat.findall(marker_line)
        label = labels[0] if labels else 'BAKE'
        out.append({'label': label,
                    'cohort': m.group('cohort').strip(),
                    'lever': m.group('lever'),
                    'op': m.group('op'),
                    'mag': float(m.group('mag'))})
    return out


_DECLINE_RANGE_RE = re.compile(r'decline\s*([<>])\s*([\d.]+)')

def _decline_band(cohort: str) -> tuple[float | None, float | None]:
    """Extract (lo, hi) from a cohort's decline-band gate. Approximate."""
    lo, hi = None, None
    for op, val in _DECLINE_RANGE_RE.findall(cohort):
        v = float(val)
        if op == '>': lo = v if lo is None else min(lo, v)
        if op == '<': hi = v if hi is None else max(hi, v)
    return lo, hi


def _qstate_token(cohort: str) -> str | None:
    """Extract qstate gate (_qpos/_qneg/_qzero/_qspos/_qsneg) if present."""
    import re as _re
    m = _re.search(r'\b(_q(?:pos|neg|zero|spos|sneg))\b', cohort or '')
    return m.group(1) if m else None


def cohort_subsumes(applied_cohort: str, candidate_cohort: str) -> bool:
    """Conservative subsumption check.

    For ENTRY probes (decline-band cohorts):
      candidate ⊆ applied iff (decline-band ⊆) AND (qstate matches)
      AND (applied has all regime gates of candidate).

    For EXIT probes (no decline band — pnl/fund/regime cohorts):
      candidate ⊆ applied iff applied_cohort is a STRING SUBSET of
      candidate_cohort (i.e., candidate adds extra gates on top of
      applied; firing population strictly smaller).

    Regime-narrowing carve-out (added 2026-05-10 after R1764 RGZ_VFL3):
    if candidate has a regime gate (`self._reg_*` or `_qqq_dn*` etc.)
    that applied does NOT have, the candidate fires on a strictly
    smaller, regime-conditioned subset — different effective population.
    Treat as orthogonal even if decline-band+qstate match.
    """
    a_lo, a_hi = _decline_band(applied_cohort)
    c_lo, c_hi = _decline_band(candidate_cohort)
    if a_lo is None and c_lo is None:
        # Both no decline-band — likely EXIT probes. Use string subset.
        norm_a = ' '.join(applied_cohort.split())
        norm_c = ' '.join(candidate_cohort.split())
        return norm_a in norm_c
    if a_lo is None or c_lo is None:
        return False
    # 2026-05-16: open-ended decline bands (no upper bound) are equivalent
    # to (lo, +inf). Treat missing hi as infinity so `decline > 0.05`
    # subsumes `decline > 0.05` (and any narrower `decline > 0.05 and
    # decline < 0.10`). Previously rejected when a_hi/c_hi was None,
    # causing auto-bake to miss same-cohort duplicate detection.
    a_hi_eff = a_hi if a_hi is not None else float('inf')
    c_hi_eff = c_hi if c_hi is not None else float('inf')
    if not (a_lo <= c_lo and c_hi_eff <= a_hi_eff):
        return False
    a_q = _qstate_token(applied_cohort)
    c_q = _qstate_token(candidate_cohort)
    if a_q != c_q:
        return False
    # Regime-narrowing carve-out: if candidate has regime gates not in applied,
    # firing populations differ → not subsumed.
    import re as _re
    REGIME_RE = _re.compile(
        r'self\._reg_\w+|_(?:qqq|hyg|vxx)_(?:dn|up|fall|rais|low|high)\w*'
        r'|_secc\s*==\s*\d+|_v\s*==\s*\d+|_d\d_\d+')
    a_regs = set(REGIME_RE.findall(applied_cohort))
    c_regs = set(REGIME_RE.findall(candidate_cohort))
    if c_regs - a_regs:
        # Candidate has additional regime gates → narrower population
        return False
    # Fund-accessor carve-out (added 2026-05-10): if candidate uses a
    # DIFFERENT fund accessor than applied (e.g. _ngt(amortization,...)
    # vs _ngt(asset_impairment,...)), firing populations differ → not
    # subsumed. Both fire on the same parent cohort but on different
    # subsets defined by the fund threshold.
    FUND_RE = _re.compile(r'_(?:ngt|nlt|nrg)\(\s*([\w.]+)')
    a_funds = set(FUND_RE.findall(applied_cohort))
    c_funds = set(FUND_RE.findall(candidate_cohort))
    if a_funds and c_funds and a_funds != c_funds:
        # Different fund-accessor sets → different firing populations
        return False
    return True


def annotate_with_overlap(bakes: list[dict], applied: list[dict],
                          axis_to_cohort: dict[str, str] | None = None,
                          rid: int | None = None,
                          saturation_at: int = 2) -> list[dict]:
    """For each bake candidate, attach 'cohort' (from gen script) and
    'overlaps_baked' flag. axis_to_cohort comes from parsing the round's gen script.

    Saturation is counted PER (lever, op) tuple on the parent cohort.
    `score +=` and `score *=` are separate lever spaces — empirical
    BAKE-QZX6 (mult) succeeded on `_qzero × bake-zone` after that parent
    already had 2 score+= bakes (BAKE-QZ1, BAKE-QZS1). Per-op counting
    prevents the additive saturation from blocking multiplicative
    exploration (and vice versa).

    `overlaps_baked` is set True when the candidate's parent cohort
    already has ≥ `saturation_at` bakes IN THE SAME LEVER+OP.
    """
    if axis_to_cohort is None:
        axis_to_cohort = {}
    for b in bakes:
        b['cohort'] = axis_to_cohort.get(b['axis'], '')
        b['overlaps_baked'] = False
        # Label-match check first (works without cohort parsing) — exact
        # axis-rid duplicate is always overlapping regardless of count.
        if rid is not None:
            label_token = f'{b["axis"]}-R{rid}'
            for ap in applied:
                if label_token in ap['label']:
                    b['overlaps_baked'] = ap['label']
                    break
            if b['overlaps_baked']: continue
        # Cohort-subsumption check (requires parsed cohort).
        if not b['cohort']: continue
        cand_op = b.get('op', '')
        cand_lever = b.get('lever', '') or ''
        # Count bakes ON THE SAME LEVER+OP that subsume this candidate's parent.
        matching_bakes = [
            ap for ap in applied
            if not ap.get('reverted')
            # Same op (additive vs multiplicative are separate spaces)
            and ap.get('op', '') == cand_op
            and cohort_subsumes(ap['cohort'], b['cohort'])
        ]
        # 2026-05-16: conv/*= and wt_tilt/*= stack MULTIPLICATIVELY across
        # subsumed cohorts. Even ONE matching subsuming bake on the same
        # cohort family pushes the multiplier past mag-peak — destructive.
        # R2347 evidence: CV_HA_D5_DEEP m118 + CV_HA_D5_PEAK m114 would
        # have stacked conv *= 1.345; reverted manually. Use saturation_at=1
        # for these multiplicative levers.
        effective_sat = saturation_at
        if cand_op == '*=' and cand_lever in ('conv', 'wt_tilt'):
            effective_sat = 1
        if len(matching_bakes) >= effective_sat:
            b['overlaps_baked'] = matching_bakes[-1]['label']
    return bakes


def parse_round_axis_cohorts(rid: int, gen_dir: str = str(WORKSPACE_ROOT / 'strategies/s001')) -> dict[str, str]:
    """Crude parse of the round's gen script — extract cohort= strings per axis name."""
    path = f'{gen_dir}/gen_s001_R{rid}.py'
    try:
        src = Path(path).read_text()
    except OSError:
        return {}
    out = {}
    # Look for Probe(name='X' or name=f'X', ..., cohort=f'Y' or '...').
    # Newer gen scripts use f-string axis names like name=f'QZX2_{i}' —
    # match the literal prefix before the {i} interpolation. We capture
    # the literal portion only; the runtime expansion (QZX2_0..QZX2_7 for
    # i in 0..7) is reconstructed using a wildcard match downstream.
    for m in re.finditer(
        r"name=f?['\"]([^'\"{}]*)(?:\{[^}]*\})?['\"][^)]*?cohort=f?['\"]([^'\"]*)['\"]",
        src, re.DOTALL):
        prefix = m.group(1)
        cohort = m.group(2)
        if not prefix: continue
        # If the cohort uses an f-string interpolation pattern (e.g.
        # `_ngt({accessor},1e6)`), keep the literal — cohort_subsumes
        # works on string-prefix matching for parent-cohort detection.
        out[prefix] = cohort
        # Also map literal index expansions: for `name=f'QZX2_{i}'` with
        # `for i in range(N)` likely producing QZX2_0..QZX2_15, store
        # entries for each common index range so propose_bakes lookup hits.
        # We don't know N here, but axes are typically 0-31.
        for idx in range(32):
            out[f'{prefix}{idx}'] = cohort
    # Helper-generated probes: score_mult_fresh(R, 'PREFIX', 'COHORT', ...).
    # Helper patterns use positional (R, prefix, cohort_template, accessors).
    # Match common helper names; capture prefix + cohort_template.
    helper_names = (
        'score_mult_fresh', 'score_additive_grid', 'wt_tilt_fund_grid',
        'bake_zone_grid', 'compound_sector_fund',
    )
    helper_pat = re.compile(
        r'(?:' + '|'.join(helper_names) + r')\s*\(\s*R\s*,\s*'
        r"f?['\"]([^'\"]+)['\"]\s*,\s*"
        r"f?['\"]([^'\"]+)['\"]",
        re.DOTALL)
    for m in helper_pat.finditer(src):
        prefix = m.group(1)
        cohort = m.group(2)
        if not prefix: continue
        out[prefix] = cohort
        for idx in range(32):
            out[f'{prefix}{idx}'] = cohort
    # Also wt_tilt_decline_band('X', lo, hi, ..., extra_cohort='Y')
    for m in re.finditer(
        r"wt_tilt_decline_band\(['\"](\w+)['\"]\s*,\s*([\d.]+)\s*,\s*([\d.]+)[^)]*"
        r"extra_cohort=['\"]([^'\"]*)['\"]",
        src, re.DOTALL):
        ax, lo, hi, extra = m.group(1), m.group(2), m.group(3), m.group(4)
        cohort = f'decline > {lo} and decline < {hi}'
        if extra: cohort = f'{extra} and {cohort}'
        out[ax] = cohort
    return out


def latest_completed_round(min_done_frac: float = 0.95, db_path: str = DB_PATH) -> int | None:
    """Highest round id whose specs are ≥`min_done_frac` done."""
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name, status FROM backtest_queue
                   WHERE name LIKE 'S001_R%_lp_%'""")
    by_rid: dict[int, dict[str, int]] = {}
    for name, status in cur.fetchall():
        m = re.match(r'S001_R(\d+)_', name)
        if not m: continue
        rid = int(m.group(1))
        by_rid.setdefault(rid, {}).setdefault(status, 0)
        by_rid[rid][status] += 1
    con.close()
    for rid in sorted(by_rid, reverse=True):
        d = by_rid[rid]
        total = sum(d.values())
        done = d.get('done', 0)
        if total > 0 and done / total >= min_done_frac:
            return rid
    return None


def pretick_guard(rid_completed: int | None = None, db_path: str = DB_PATH,
                  base_path: str = BASE_PATH) -> tuple[bool, str]:
    """Run before queueing the next round. Returns (clear_to_queue, message).

    Bake-eligible probes whose cohort is SUBSUMED by an already-applied
    bake are flagged but not blocking. Pure-orthogonal eligible bakes block.

    If rid_completed is None, auto-picks the latest completed round.
    """
    if rid_completed is None:
        rid_completed = latest_completed_round(db_path=db_path)
        if rid_completed is None:
            return (True, 'no completed rounds yet')
    bakes = propose_bakes(rid_completed, db_path=db_path)
    if not bakes:
        return (True, f'R{rid_completed}: no eligible bakes (0 probes ≥+{BAKE_THRESHOLD})')
    # Filter out previously-applied or REVERTED axes for this rid — both
    # represent "we've decided about this candidate; don't propose again".
    log = _load_bake_log()
    decided_labels = {e.get('label') for e in log}
    bakes = [b for b in bakes
             if f'BAKE-{b["axis"]}-R{rid_completed}' not in decided_labels]
    if not bakes:
        return (True, f'R{rid_completed}: all eligible bakes already applied or reverted')
    applied = applied_bakes(base_path)
    cohorts = parse_round_axis_cohorts(rid_completed)
    # Resolve cohorts via dry_import_round (handles constants like COHORT_BAKE_ZONE
    # that the regex parser can't extract). Fall back to regex if import fails.
    try:
        R_dry = dry_import_round(rid_completed)
        if R_dry is not None:
            for p in R_dry.probes:
                full = p.cohort or ''
                if p.fund: full = f'{full} and {p.fund}' if full else p.fund
                if p.extra: full = f'{full} and {p.extra}' if full else p.extra
                cohorts.setdefault(p.name, full)
    except Exception:
        pass
    bakes = annotate_with_overlap(bakes, applied, cohorts, rid=rid_completed)
    # Same-accessor guard (mirrors auto_apply_bake): mark candidates whose
    # accessor already has 2 score+= or 2 score*= bakes as overlapping —
    # multi-regime stacking disaster R1770 prevention.
    import re as _r
    for b in bakes:
        if b.get('overlaps_baked'): continue
        cand_cohort = b.get('cohort','')
        m = _r.search(r'_n(?:gt|lt)\(([^,]+),', cand_cohort)
        if not m: continue
        cand_acc = m.group(1).strip()
        # If parser returned literal `{accessor}` placeholder (helper-built
        # probe), fall back to queued-code extraction for the real accessor.
        if cand_acc == '{accessor}':
            actual_cohort = _extract_actual_probe_cohort(
                rid_completed, b['name'], 'score', b.get('op','+='),
                b.get('mag', 0.020), db_path)
            if actual_cohort:
                m2 = _r.search(r'_n(?:gt|lt)\(([^,]+),', actual_cohort)
                if m2:
                    cand_acc = m2.group(1).strip()
        # We don't know op from candidate dict directly; check both += and *=.
        for op in ('+=','*='):
            same_acc_count = sum(
                1 for ap in applied
                if ap['lever']=='score' and ap.get('op')==op
                and not ap.get('reverted')
                and cand_acc in ap.get('cohort','')
            )
            if same_acc_count >= 2:
                b['overlaps_baked'] = f'same-accessor cap ({op}, {cand_acc[:40]})'
                break
    orthogonal = [b for b in bakes if not b['overlaps_baked']]
    lines = [f'R{rid_completed}: {len(bakes)} bake-eligible '
             f'({len(orthogonal)} orthogonal, {len(bakes) - len(orthogonal)} subsumed by existing bakes)']
    for b in bakes[:10]:
        flag = f' [SUBSUMED by {b["overlaps_baked"]}]' if b['overlaps_baked'] else ' [ORTHOGONAL]'
        lines.append(f'  {b["axis"]:<6} {b["tag"]:<6} {b["op"] or "?"} {b["mag"] or "?"} '
                     f'd={b["delta"]:+.5f} cohort={b["cohort"][:60]}{flag}')
    if not orthogonal:
        lines.append('=> CLEAR: all eligible bakes subsumed by existing bakes')
        return (True, '\n'.join(lines))
    lines.append('=> HALT: apply orthogonal bake to base, then re-run')
    return (False, '\n'.join(lines))


# ---------- dry-run gen-script import (capture Round metadata) ----------

def dry_import_round(rid: int, gen_dir: str = str(WORKSPACE_ROOT / 'strategies/s001')):
    """Import gen_s001_R{rid}.py without queueing, returning the built Round.

    Stubs out pretick_or_die and run_audit_and_queue so main() builds the
    Round object but skips DB writes. Returns the Round (with all probes,
    cohorts, ops, mags accessible via R.find_probe(name)).
    """
    import importlib.util
    from s001 import gen_s001_strategies as strat
    captured = {'round': None}
    orig_pretick = strat.pretick_or_die
    orig_run = strat.run_audit_and_queue
    strat.pretick_or_die = lambda *a, **kw: None
    strat.run_audit_and_queue = lambda R: captured.__setitem__('round', R) or {}
    try:
        path = f'{gen_dir}/gen_s001_R{rid}.py'
        spec = importlib.util.spec_from_file_location(f'_dry_R{rid}', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, 'main'):
            mod.main()
    finally:
        strat.pretick_or_die = orig_pretick
        strat.run_audit_and_queue = orig_run
    return captured['round']


# ---------- one-shot bake automation ----------

# Path to the bake audit trail (JSON list, one entry per applied bake).
BAKES_LOG_PATH = str(WORKSPACE_ROOT / 'strategies/s001/research/bakes.json')


def _load_bake_log() -> list[dict]:
    import json
    p = Path(BAKES_LOG_PATH)
    if not p.exists(): return []
    try: return json.loads(p.read_text())
    except Exception: return []


def _save_bake_log(entries: list[dict]) -> None:
    import json
    Path(BAKES_LOG_PATH).write_text(json.dumps(entries, indent=2) + '\n')


def append_bake_log(entry: dict) -> None:
    """Append a bake-apply record. Entry must contain at least: label, rid,
    axis, lever, op, mag, cohort, predicted_lift, applied_at."""
    log = _load_bake_log()
    log.append(entry)
    _save_bake_log(log)


def get_bake_log(label: str | None = None) -> list[dict] | dict | None:
    """Return all bake records, or the one matching `label` (or None)."""
    log = _load_bake_log()
    if label is None: return log
    for e in log:
        if e.get('label') == label: return e
    return None


def verify_noop_shift(label: str, db_path: str = DB_PATH) -> dict:
    """Compare the actual post-bake NOOP shift against the bake's predicted lift.

    Looks up the bake by label in bakes.json, finds the FIRST round AFTER the
    bake's rid that has completed NOOPs, and reports:
        predicted_lift, prev_noop, post_noop, actual_shift, ratio (actual/predicted),
        verdict ('OK' if |ratio - 1| < 0.30, 'OFF' otherwise, 'pending' if no
        post-bake NOOPs yet).
    """
    rec = get_bake_log(label)
    if rec is None: return {'verdict': 'unknown', 'reason': f'no bake {label!r} in log'}
    predicted = rec['predicted_lift']
    prev_noop = rec.get('prev_noop')
    if prev_noop is None: return {'verdict': 'unknown', 'reason': 'no prev_noop in record'}
    # Use first_post_bake_rid if recorded; else fall back to rid+1
    floor_rid = rec.get('first_post_bake_rid', rec['rid'] + 1)

    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name, car_mdd FROM experiments
                   WHERE name LIKE 'S001_R%_lp_NOOP_%' AND car_mdd IS NOT NULL""")
    rows = cur.fetchall(); con.close()
    by_rid: dict[int, list[float]] = {}
    for name, cm in rows:
        m = re.match(r'S001_R(\d+)_', name)
        if m: by_rid.setdefault(int(m.group(1)), []).append(cm)

    post_rids = sorted(r for r in by_rid if r >= floor_rid)
    if not post_rids:
        return {'verdict': 'pending', 'reason': f'no NOOPs from R{floor_rid}+ yet',
                'predicted_lift': predicted, 'prev_noop': prev_noop}
    first_post = post_rids[0]
    post_noop = sum(by_rid[first_post]) / len(by_rid[first_post])
    actual = post_noop - prev_noop
    ratio = actual / predicted if predicted else float('nan')
    verdict = 'OK' if abs(ratio - 1.0) < 0.30 else 'OFF'
    return {'verdict': verdict, 'predicted_lift': predicted, 'prev_noop': prev_noop,
            'post_noop': post_noop, 'actual_shift': actual, 'ratio': ratio,
            'first_post_rid': first_post, 'label': label}


def all_bakes_status() -> list[dict]:
    """Run verify_noop_shift on every record in the bake log."""
    return [verify_noop_shift(rec['label']) for rec in _load_bake_log()]


def _extract_actual_probe_cohort(rid: int, spec_name: str, lever: str,
                                  op: str, mag: float,
                                  db_path: str = DB_PATH) -> str | None:
    """Extract the actual cohort string from the queued backtest code,
    not the dry-import (which re-runs non-deterministic pickers).
    Returns None if the cohort can't be reliably extracted.
    """
    import re as _re
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("SELECT code FROM backtest_queue WHERE name = ?", (spec_name,))
    row = cur.fetchone(); con.close()
    if not row or not row[0]:
        return None
    code = row[0]
    # Probes are injected immediately BEFORE the
    # `# --- ENTRY INJECT POINT ---` (or EXIT INJECT POINT) marker, wrapped
    # in `try: ... except: pass`. Locate the marker(s), then scan the ~80
    # lines BEFORE each marker for a matching `if <cohort>: <lever> <op><mag>`
    # line. Skip lines preceded by `# BAKE-` comments (those are baked-in
    # cohorts, not injected probes).
    op_re = _re.escape(op)
    mag_pat = rf'{mag}0*'
    pat = rf'\s*if\s+(.+?):\s*{lever}\s*{op_re}\s*{mag_pat}\s*$'
    lines = code.split('\n')
    markers = [i for i, ln in enumerate(lines)
               if 'INJECT POINT' in ln and ('ENTRY' in ln or 'EXIT' in ln)]
    scan_ranges = [(max(0, m - 80), m) for m in markers] if markers \
        else [(0, len(lines))]
    for start, end in scan_ranges:
        # Scan backwards from end-1 down to start so we get the LAST
        # matching probe (most recent injection wins).
        for i in range(end - 1, start - 1, -1):
            line = lines[i]
            m = _re.match(pat, line)
            if not m: continue
            # Tight bake-skip: only skip if the `# BAKE-` comment is the
            # most recent non-empty line BEFORE the probe (not from an
            # earlier bake block in the same window).
            ctx_lines = lines[max(0, i-3):i]
            non_empty = [ln for ln in ctx_lines if ln.strip()
                         and ln.strip() not in ('try:',)]
            if non_empty and _re.search(r'#\s*BAKE[-\s]', non_empty[-1]):
                continue
            return m.group(1).strip()
    return None


def audit_bake_delivery(db_path: str = DB_PATH,
                        min_delivery_ratio: float = 0.30) -> list[dict]:
    """Audit ALL active bakes' predicted vs actual post-bake NOOP shift.

    Returns list of suspect bakes where actual shift < min_delivery_ratio
    of predicted, ANNOTATED with variance-reliability flag.

    Each suspect also reports `noop_variance_at_revert`: the spread of
    NOOPs in the round measured. If variance > 0.001, the audit signal
    is UNRELIABLE — historical NOOP cluster shifts can mask real bake
    contribution (R2180+R2182 case: audit said null/destructive but
    R2355 revert experiment showed NOOP fell -0.0012 = bakes were
    productive).

    Trust audit only when noop_variance < 0.001 (single-cluster NOOPs).
    """
    import statistics as _stat
    log = _load_bake_log()
    active = [b for b in log
              if not b.get('reverted') and b.get('predicted_lift')
              and b.get('first_post_bake_rid') and b.get('prev_noop')]
    con = storage.connect(db_path); cur = con.cursor()
    suspects = []
    for b in active:
        cur.execute("""SELECT car_mdd FROM experiments WHERE name LIKE ?
                       AND car_mdd IS NOT NULL""",
                    (f'S001_R{b["first_post_bake_rid"]}_lp_NOOP_%',))
        noops = [r[0] for r in cur.fetchall()]
        if not noops:
            continue
        post = _stat.median(noops)
        shift = post - b['prev_noop']
        pred = b['predicted_lift']
        ratio = shift / pred if pred else 0
        variance = max(noops) - min(noops) if len(noops) > 1 else 0.0
        if ratio < min_delivery_ratio:
            suspects.append({
                'label': b['label'], 'lever': b.get('lever', ''),
                'predicted': pred, 'actual_shift': shift,
                'ratio': ratio, 'rid': b.get('rid'),
                'noop_variance': variance,
                'reliable': variance < 0.001,
            })
    con.close()
    suspects.sort(key=lambda s: s['predicted'] - s['actual_shift'], reverse=True)
    return suspects


def verify_recent_bake_lift(db_path: str = DB_PATH,
                            min_delivery_ratio: float = 0.30) -> None:
    """Audit the most recent applied bake's predicted vs actual NOOP shift.

    Print a WARNING if actual shift is less than `min_delivery_ratio` of
    predicted (default 30%). Does not auto-revert — caller must decide.

    Skips bakes already marked reverted, and bakes whose first_post_bake_rid
    doesn't have completed NOOPs yet (verification pending).

    R2347 evidence: 3 conv bakes predicted +0.00206 stacked, R2348 NOOP
    shift was +0.00000. Null bakes accumulate compute waste + clutter
    the base.py.
    """
    import statistics as _stat
    log = _load_bake_log()
    candidates = [b for b in log
                  if not b.get('reverted') and b.get('predicted_lift')
                  and b.get('first_post_bake_rid')
                  and b.get('prev_noop')]
    if not candidates:
        return
    # Take the most-recently-applied bake (highest applied_at)
    candidates.sort(key=lambda b: b.get('applied_at', ''), reverse=True)
    latest = candidates[0]
    post_rid = latest['first_post_bake_rid']
    pred = latest['predicted_lift']
    prev = latest['prev_noop']
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT car_mdd FROM experiments WHERE name LIKE ?
                   AND car_mdd IS NOT NULL""",
                (f'S001_R{post_rid}_lp_NOOP_%',))
    post_noops = [r[0] for r in cur.fetchall()]
    con.close()
    if not post_noops:
        return  # post-bake round not yet measurable
    post = _stat.median(post_noops)
    actual = post - prev
    ratio = (actual / pred) if pred else 0
    if ratio < min_delivery_ratio:
        print(f'  ⚠ POST-BAKE-VERIFY: {latest["label"]} '
              f'predicted +{pred:.5f}, actual NOOP shift '
              f'{actual:+.5f} ({ratio*100:.0f}% of predicted) — '
              f'consider reverting if subsequent rounds confirm null lift')


def auto_apply_bake(rid_completed: int | None = None, dry_run: bool = False,
                    db_path: str = DB_PATH, base_path: str = BASE_PATH) -> dict | None:
    """Apply the highest-delta orthogonal bake from rid_completed automatically.

    Looks up cohort/op/mag/inject from the gen script's Round (via dry-import),
    formats the patch, and writes to base. Logs to bakes.json (unless dry_run).
    Returns metadata dict or None if no orthogonal bake is eligible.
    """
    if rid_completed is None:
        rid_completed = latest_completed_round(db_path=db_path)
        if rid_completed is None:
            return None
    raw_bakes = propose_bakes(rid_completed, db_path=db_path)
    if not raw_bakes:
        return None
    applied = applied_bakes(base_path)
    # Guard: skip if a bake with the same label (axis × rid) was already
    # logged. R1755 QZX6 dueto-vs-duefrom bug 2026-05-09 — second call
    # re-applied with wrong cohort due to non-deterministic dry-import.
    log = _load_bake_log()
    already_labels = {e.get('label') for e in log}
    raw_bakes = [b for b in raw_bakes
                 if f'BAKE-{b["axis"]}-R{rid_completed}' not in already_labels]
    if not raw_bakes:
        return None
    cohorts = parse_round_axis_cohorts(rid_completed)
    bakes = annotate_with_overlap(raw_bakes, applied, cohorts, rid=rid_completed)
    orthogonal = [b for b in bakes if not b['overlaps_baked']]
    if not orthogonal:
        return None
    # Cohort-saturation guard: per memory feedback_s001_destructive_stacking,
    # after 2+ score+= bakes on a parent cohort, further bakes there
    # destructively stack. Tracked parent cohorts (2026-05-09):
    #   BAKE-ZONE      = `_qpos × decline ∈ (0.020, 0.050)` (3 bakes: WH/FC/FG)
    #   JUST-BELOW-BAKE = `_qpos × decline ∈ (0.015, 0.020)` (2 bakes: JBC/J0)
    SATURATED_PREFIXES = [
        '_qpos and decline > 0.020 and decline < 0.050',  # BAKE-ZONE
        '_qpos and decline > 0.015 and decline < 0.020',  # JUST-BELOW-BAKE
        '_qzero and decline > 0.020 and decline < 0.050', # QZERO-BZ (added 2026-05-10 after QZX6+QZX2_1)
        '_qzero and decline > 0.012 and decline < 0.015', # QZERO-A (BAKE-QZA + BAKE-QZAS)
    ]
    # Per-op counting: score += and score *= are separate lever spaces.
    # R1755 BAKE-QZX6 (mult) was productive on `_qzero × bake-zone` even
    # after BAKE-QZ1 + QZS1 had saturated the additive lane. Same parent,
    # different effect. Track each op separately.
    score_bakes_by_prefix_op: dict[tuple[str, str], int] = {
        (p, op): 0 for p in SATURATED_PREFIXES for op in ('+=', '*=')
    }
    for ap in applied:
        if ap['lever'] != 'score' or ap.get('reverted'):
            continue
        if ap['op'] not in ('+=', '*='):
            continue
        for p in SATURATED_PREFIXES:
            if ap['cohort'].startswith(p):
                score_bakes_by_prefix_op[(p, ap['op'])] += 1
                break
    # Count existing exit-side large-cap-size bakes (TOTEXP/TOTASSETS/TOTREV
    # etc.). Once we have >= 3, additional same-firing-population gates
    # are highly redundant — they fire on same set of stocks already
    # exited by the existing trio.
    large_cap_exit_bake_count = sum(
        1 for ap in applied
        if ap['lever'] == 'exit_signal' and not ap.get('reverted')
        and _is_large_cap_size_gate(ap['cohort']))

    # Saturation guard 2026-05-09: when round silent rate exceeds 70%,
    # most probes have reached NOOP — the lever space is saturated.
    # Reject exit-side bake candidates from such rounds (likely tiny lifts
    # on noise). Memory: feedback_s001_005_cap_saturated.
    silent_pct = silent_noop_audit(rid_completed, db_path).get('silent_pct', 0)
    saturated_round = silent_pct > 70.0
    total_exit_bakes = sum(
        1 for ap in applied
        if ap['lever'] == 'exit_signal' and not ap.get('reverted'))
    R_dry = dry_import_round(rid_completed)
    # 2026-05-09: prefer candidates already at mag ≤ 0.05 for exit_signal
    # lever (user cap). Re-sort orthogonal so cap-eligible exit_signal
    # probes come first, ties broken by delta.
    def _sort_key(b):
        # 0 = cap-eligible exit_signal; 1 = anything else
        is_exit = (R_dry.find_probe(b['axis']) and
                   R_dry.find_probe(b['axis']).lever == 'exit_signal') if R_dry else False
        if is_exit and b['mag'] > 0.05:
            return (1, -b['delta'])  # exit_signal at >0.05: deprioritize
        return (0, -b['delta'])
    if R_dry:
        orthogonal.sort(key=_sort_key)
    while orthogonal:
        candidate = orthogonal[0]
        candidate_probe = R_dry.find_probe(candidate['axis']) if R_dry else None
        if candidate_probe and candidate_probe.lever == 'score' and candidate_probe.op in ('+=', '*='):
            full = candidate_probe.cohort or ''
            if candidate_probe.fund: full = f'{full} and {candidate_probe.fund}' if full else candidate_probe.fund
            saturated = False
            cand_op = candidate_probe.op
            import re as _r
            REGIME_RE = _r.compile(
                r'self\._reg_\w+|_(?:qqq|hyg|vxx)_(?:dn|up|fall|rais|low|high)\w*')
            cand_regs = set(REGIME_RE.findall(full))

            # NEW guard: same-accessor multi-regime stacking limit. R1770
            # disaster: 4 score*=1.05 bakes with same accessor (excise_taxes)
            # × 4 regimes on _qzero × 0.005-0.012 caused -0.00426 NOOP
            # regression vs +0.00724 predicted. Multiplicative compounds when
            # multiple regime gates fire simultaneously. Cap same-accessor
            # same-op bakes at 2.
            cand_accessor_match = _r.search(
                r'_n(?:gt|lt)\(([^,]+),', full)
            cand_accessor = cand_accessor_match.group(1).strip() if cand_accessor_match else None
            if cand_accessor:
                same_accessor_bakes = sum(
                    1 for ap in applied
                    if ap['lever']=='score' and ap['op']==cand_op
                    and not ap.get('reverted')
                    and (cand_accessor in ap.get('cohort',''))
                )
                if same_accessor_bakes >= 2:
                    print(f'  SKIP candidate {candidate.get("axis","?")}: '
                          f'accessor {cand_accessor[:50]!r} already has '
                          f'{same_accessor_bakes} {cand_op} bakes (multi-'
                          f'regime stacking disaster R1770)')
                    orthogonal.pop(0)
                    continue

            for p in SATURATED_PREFIXES:
                if not full.startswith(p): continue
                if score_bakes_by_prefix_op.get((p, cand_op), 0) < 2: continue
                blocking_bakes = [
                    ap for ap in applied
                    if ap['lever']=='score' and ap['op']==cand_op
                    and not ap.get('reverted')
                    and ap['cohort'].startswith(p)
                ]
                blocking_with_regime_match = sum(
                    1 for ap in blocking_bakes
                    if cand_regs.issubset(set(REGIME_RE.findall(ap['cohort'])))
                )
                if blocking_with_regime_match >= 2:
                    saturated = True
                    break
            if saturated:
                orthogonal.pop(0)
                continue
        # Skip exit-side large-cap-size redundancy: if we already have ≥3
        # such bakes (TOTEXP/TOTASSETS/TOTREV typically), reject more.
        if (candidate_probe and candidate_probe.lever == 'exit_signal'
                and large_cap_exit_bake_count >= 3
                and _is_large_cap_size_gate(candidate.get('cohort', ''))):
            orthogonal.pop(0)
            continue
        # Saturation guard: reject exit-side bakes when round silent rate
        # >70% AND we already have ≥6 exit bakes. The lift is likely
        # noise on saturated baseline.
        if (saturated_round and total_exit_bakes >= 6
                and candidate_probe and candidate_probe.lever == 'exit_signal'):
            orthogonal.pop(0)
            continue
        break
    if not orthogonal:
        return None
    best = orthogonal[0]
    R = dry_import_round(rid_completed)
    if R is None:
        raise RuntimeError(f'could not dry-import R{rid_completed} gen script')
    probe = R.find_probe(best['axis'])
    if probe is None:
        # Dry-import may skip probes (e.g. guards added after queue time,
        # OR helper-generated cohorts that dry-import non-deterministically
        # mis-allocates). Fall back: infer lever from axis name conventions
        # (EM_*→entry_score_mtf, EQ_*→entry_score_quality, EG_*→entry_score_gate,
        # ER_*→entry_score_regime, EC_*→entry_score_conv, ES_*→entry_signal,
        # WSN_*/W*→wt_tilt, SD_*→score). Cohort comes from _extract_actual_probe_cohort.
        class _FallbackProbe:
            cohort = ''
            fund = ''
            extra = ''
        probe = _FallbackProbe()
        axis_name = best['axis']
        # axis names follow letter-prefixed convention like 'A_EM_S311_HA_1'
        # or helper-emitted like 'EM_QPOS_S311_DP'. Strip leading letter+
        # underscore if present and check the next token.
        import re as _re
        token = axis_name
        # Strip leading letter+_ (e.g., 'A_EM_...')
        m_pfx = _re.match(r'^[A-Z]_(\w+)', axis_name)
        if m_pfx:
            token = m_pfx.group(1)
        LEVER_BY_PREFIX = {
            'EM_': 'entry_score_mtf', 'EQ_': 'entry_score_quality',
            'EG_': 'entry_score_gate', 'ER_': 'entry_score_regime',
            'EC_': 'entry_score_conv', 'ES_': 'entry_signal',
            'WSN_': 'wt_tilt', 'WT_': 'wt_tilt', 'SD_': 'score',
            'SCM_': 'score', 'WZ_': 'wt_tilt',
        }
        inferred_lever = 'score'
        for pfx, lvr in LEVER_BY_PREFIX.items():
            if token.startswith(pfx):
                inferred_lever = lvr
                break
        probe.lever = inferred_lever
        # Op normalization — propose_bakes returns op in tag-style ('+=' etc.)
        probe.op = best.get('op', '*=')
        probe.inject = 'ENTRY'
        probe.cohort = ''
        probe.fund = ''
        probe.extra = ''
        print(f'  WARN: axis {best["axis"]!r} missing from dry-import; '
              f'inferred lever={inferred_lever}, using queued-code fallback for cohort')
    parts = []
    if probe.cohort: parts.append(probe.cohort)
    if probe.fund:   parts.append(probe.fund)
    if probe.extra:  parts.append(probe.extra)
    full_cohort_dry = ' and '.join(parts) if parts else 'True'

    # CRITICAL: dry_import_round re-runs picker non-deterministically
    # (pick_fresh_fields_under_explored returns different ordering across
    # runs). Cross-check the stored backtest code to get the ACTUAL
    # cohort/fund as it was injected at queue time. R1699 BAKE-QNA1
    # bug 2026-05-09: dry-import returned net_income_extraordinary but
    # actual queued probe was excise_taxes.
    full_cohort = _extract_actual_probe_cohort(
        rid_completed, best['name'], probe.lever, best['op'], best['mag'],
        db_path) or full_cohort_dry

    # 2026-05-11 SAFETY GUARD: if cohort extraction failed and we fell back
    # to bare 'True', the bake would apply UNCONDITIONALLY to every entry
    # — destructive structural change. Reject this case explicitly.
    # Root cause: dry_import_round doesn't see helper-generated cohorts
    # (build_128_round emits cohorts at runtime); + _extract_actual_probe_cohort
    # used wrong default lever for the fallback search.
    if not full_cohort or full_cohort.strip() == 'True':
        print(f'  ABORT: cohort extraction failed for {best["axis"]!r} '
              f'(dry-import miss + queued-code lookup miss). '
              f'Would inject unconditional `if True:` bake. Skipping.')
        return None

    # User 2026-05-09: max exit_signal bake mag = 0.05.
    # Cap at apply time even if propose returned candidate at higher mag.
    apply_mag = best['mag']
    if probe.lever == 'exit_signal' and apply_mag > 0.05:
        apply_mag = 0.05  # capped per user directive
    label = f'BAKE-{best["axis"]}-R{rid_completed}'
    comment = f'{label} (+{best["delta"]:.5f})'
    patched = apply_bake_to_base(base_path, full_cohort, probe.lever,
                                 best['op'], apply_mag,
                                 comment=comment, inject=probe.inject)
    # Capture pre-bake NOOP for later verification
    noop_cm, _, _ = round_noop(rid_completed, db_path=db_path)
    if noop_cm is None:
        noop_cm = latest_noop_baseline(db_path=db_path)
    # Find the highest queued rid at apply time — first post-bake round = that+1.
    # Rounds queued BEFORE the bake ran on the pre-bake base, so their NOOPs
    # don't reflect the bake.
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name FROM backtest_queue WHERE name LIKE 'S001_R%_lp_%'""")
    rids: set[int] = set()
    for (n,) in cur.fetchall():
        m = re.match(r'S001_R(\d+)_', n)
        if m: rids.add(int(m.group(1)))
    con.close()
    max_queued_rid = max(rids) if rids else rid_completed
    first_post_bake_rid = max_queued_rid + 1

    result = {
        'label': label, 'axis': best['axis'], 'tag': best['tag'],
        'lever': probe.lever, 'op': best['op'], 'mag': apply_mag,
        'orig_mag': best['mag'],
        'inject': probe.inject, 'cohort': full_cohort,
        'predicted_lift': best['delta'], 'delta': best['delta'],
        'orders': best['orders'], 'prev_noop': noop_cm,
        'first_post_bake_rid': first_post_bake_rid,
        'dry_run': dry_run, 'rid': rid_completed,
    }
    if not dry_run:
        Path(base_path).write_text(patched)
        from datetime import datetime
        result['applied_at'] = datetime.now().isoformat(timespec='seconds')
        append_bake_log(result)
    return result


# ---------- accessor fire-rate empirics (R1690-R1701 audit 2026-05-09) ----------
# Across 12 rounds, 199 of 485 accessors had 0% fire rate. Cause: QQQ universe
# is tech-heavy — bank / insurance / REIT-specific fields (e.g.,
# `policyholder_funds`, `gross_notes_receivable`, `bank_owned_life_insurance`,
# `trading_assets`) never have stocks > $1M because QQQ has no banks/insurers.
# These 199 accessors waste ~30% of every round's spec budget.

# Curated list of NEVER-FIRES accessors (≥3 trials, 0% fire rate, R1690-R1701).
# These are bank/insurance/REIT/specialty fields not represented in QQQ.
NEVER_FIRES_ACCESSORS = frozenset({
    # Banking / lending
    '_bs_z.gross_notes_receivable.twelve_months',
    '_bs_z.allowance_for_doubtful_accounts_receivable.twelve_months',
    '_bs_z.allowance_for_loans_and_lease_losses.twelve_months',
    '_bs_z.bank_owned_life_insurance.twelve_months',
    '_bs_z.security_borrowed.twelve_months',
    # Trading / investment desks
    '_bs_z.trading_assets.twelve_months',
    '_bs_z.trading_securities.twelve_months',
    '_bs_z.held_to_maturity_securities.twelve_months',
    '_bs_z.total_investments.twelve_months',
    '_bs_z.other_invested_assets.twelve_months',
    '_bs_z.policy_loans.twelve_months',
    # Insurance
    '_bs_z.policyholder_funds.twelve_months',
    '_bs_z.assets_held_for_sale.twelve_months',
    '_bs_z.unrealized_gain_loss.twelve_months',
    '_bs_z.receivables_adjustments_allowances.twelve_months',
    # Real estate / specialty
    '_bs_z.other_real_estate_owned.twelve_months',
    '_bs_z.deferred_costs.twelve_months',
    '_bs_z.restricted_cash_and_cash_equivalents.twelve_months',
    '_bs_z.restricted_cash_and_investments.twelve_months',
    '_bs_z.other_liabilities.twelve_months',
    # CFS / dividends
    '_cfs_z.dividends_received.twelve_months',
    '_vr_z.fcf_yield_one_year_avg',
    '_vr_z.price_to_sales',
    '_vr_z.buyback_yield',
})


def accessor_fire_rates(min_trials: int = 3,
                        db_path: str = DB_PATH) -> dict[str, dict]:
    """Aggregate fire/silent counts per accessor across all rounds.

    A probe is "silent" iff its (car_mdd, total_orders, end_equity) matches
    any NOOP fingerprint from the same round. "Fire" = anything else.

    Returns {accessor: {'fired': N, 'total': N, 'rate': float}} for
    accessors with at least `min_trials`.
    """
    import re as _re
    con = storage.connect(db_path); cur = con.cursor()

    cur.execute("""SELECT name, car_mdd, total_orders, end_equity FROM experiments
                   WHERE name LIKE 'S001_R%_lp_NOOP_%' AND car_mdd IS NOT NULL""")
    noops_by_rid: dict[int, set] = {}
    for n, c, o, e in cur.fetchall():
        rid = int(_re.search(r'_R(\d+)_', n).group(1))
        noops_by_rid.setdefault(rid, set()).add((c, o, e))

    cur.execute("""SELECT bq.name, e.car_mdd, e.total_orders, e.end_equity, bq.code
                   FROM backtest_queue bq JOIN experiments e ON bq.name = e.name
                   WHERE bq.name LIKE 'S001_R%_lp_%' AND bq.name NOT LIKE '%NOOP%'
                   AND e.car_mdd IS NOT NULL AND bq.code IS NOT NULL""")
    stats: dict[str, list[int]] = {}
    for name, cm, to, eq, code in cur.fetchall():
        rid_m = _re.search(r'_R(\d+)_', name)
        if not rid_m: continue
        rid = int(rid_m.group(1))
        noops = noops_by_rid.get(rid, set())
        silent = (cm, to, eq) in noops
        # Locate injected probe (line just before salt comment)
        lines = code.split('\n')
        salt_idx = next((i for i, ln in enumerate(lines)
                         if _re.search(r'#\s*loop_salt_', ln)), -1)
        if salt_idx < 0: continue
        # Search up to 8 lines back for an accessor reference
        for i in range(salt_idx - 1, max(-1, salt_idx - 9), -1):
            ln = lines[i]
            am = _re.search(
                r'(_(?:vr|ops|ers|ac|er|sr|fs|bs|inc|cfs)_z\.[a-z_]+(?:\.[a-z_]+)?)', ln)
            if am and ('score' in ln or 'wt_tilt' in ln or 'conv' in ln):
                acc = am.group(1)
                stats.setdefault(acc, [0, 0])
                stats[acc][1] += 1
                if not silent: stats[acc][0] += 1
                break
    con.close()
    return {acc: {'fired': f, 'total': t, 'rate': f / t}
            for acc, (f, t) in stats.items() if t >= min_trials}


def pick_high_fire_rate_fresh(n: int = 8, min_rate: float = 0.25,
                              gen_dir: str = str(WORKSPACE_ROOT / 'strategies/s001'),
                              db_path: str = DB_PATH) -> list[str]:
    """Pick fresh accessors that have HIGH historical fire rate in QQQ universe.

    Combines the existing fresh-field selection (untouched in gen scripts) with
    an empirical fire-rate prior. Falls back to category-filtered picker if
    no high-fire-rate fresh fields are available.

    Use for high-EV exploration rounds. For frontier rounds (testing truly
    new fields), use pick_fresh_fields_under_explored directly.
    """
    rates = accessor_fire_rates(min_trials=3, db_path=db_path)
    high_fire = {acc for acc, s in rates.items() if s['rate'] >= min_rate}
    fresh = pick_fresh_fields_under_explored(n=n * 4, gen_dir=gen_dir, db_path=db_path)
    # Prefer fresh ∩ high-fire-rate
    preferred = [f for f in fresh if f in high_fire]
    # Fallback: include other fresh if not enough preferred
    rest = [f for f in fresh if f not in high_fire]
    out = (preferred + rest)[:n]
    return out


# ---------- fresh-field auto-picker ----------

# Common "large-company size" accessors — gates using `> Xe6/Xe7/Xe8/Xe9`
# on these fire on ~all QQQ stocks (highly redundant). Track how many
# already baked; reject candidates that would be the 3rd+ such bake.
_LARGE_CAP_SIZE_ACCESSORS = (
    'total_revenue', 'total_expenses', 'total_assets',
    'total_liabilities', 'gross_profit', 'operating_income',
    'pretax_income', 'ebit', 'ebitda', 'cash_and_cash_equivalents',
    'current_assets', 'current_liabilities', 'accounts_payable',
    'accounts_receivable', 'gross_ppe', 'inventory',
    'goodwill', 'intangible_assets', 'stockholders_equity',
    'depreciation', 'depreciation_amortization_depletion',
    'operating_cash_flow', 'capital_expenditure', 'free_cash_flow',
    'net_income', 'eps',
)


def _is_large_cap_size_gate(cohort: str) -> bool:
    """Heuristic: cohort is an 'any large company' gate if it uses a
    common size-related accessor with absolute-dollar threshold."""
    return any(acc in cohort for acc in _LARGE_CAP_SIZE_ACCESSORS)


# Field-name patterns that indicate categorical / ratio / non-absolute
# fields — these fail `fund_gt(accessor, 1e6)` and produce silent no-op
# probes (R1697 audit: 75.8% silent-noop'd, large share from this).
# Threshold > 1e6 is meaningful for absolute dollar amounts (revenue,
# balance-sheet items) but meaningless for ratios/scores/grades/codes.
_NONNUMERIC_FIELD_PATTERNS = (
    # categorical / identifier / string
    'symbol', 'exchange_id', 'currency_id', 'ipo_date', 'sic', 'naics',
    'nace', 'morningstar_industry', 'morningstar_economy', 'morningstar_sector',
    'is_depositary', 'depositary_receipt', 'forward_calculation_style',
    'security_type', 'security_status', 'company_status',
    # grades / scores / classes
    'grade', 'score', 'rank', 'class', 'tier',
    # _sr_z (security reference) is mostly identifiers; very rarely numeric
    # ratios / yields / margins (values typically [-1, 5])
    'ratio', 'yield', 'margin_', '_yield', '_pct', '_percentage',
    'roe', 'roa', 'roic',
    # forward estimates can be either, but most are ratios — exclude conservatively
    'forward_pe', 'forward_eps', 'forward_dividend', 'forward_book',
    # per-share dollar values (EPS, BVPS) — typical range $0-50, fails > 1e6
    'eps', '_per_share', 'book_value_per_share', 'price_per',
    # tax loss carryforward, accounting change in EPS form
    'accounting_change',
)

# Namespaces with mostly absolute dollar values (safe for > 1e6).
# Other namespaces rejected by default to avoid silent-noop waste.
_ABSOLUTE_NAMESPACES = ('_bs', '_inc', '_cfs', '_er', '_ers')


def _is_likely_numeric_absolute(accessor: str) -> bool:
    """Reject categorical/grade/ratio fields where `> 1e6` is meaningless.
    Returns True only for fields plausibly in absolute-dollar units.
    """
    parts = accessor.split('.', 1)
    if len(parts) < 2: return False
    ns_raw, rest = parts[0], parts[1]
    ns = ns_raw[:-2] if ns_raw.endswith('_z') else ns_raw
    # Hard reject ns where most fields are non-absolute
    if ns in ('_ac', '_sr', '_vr'): return False
    # Reject by name patterns
    fld_lower = rest.lower()
    if any(p in fld_lower for p in _NONNUMERIC_FIELD_PATTERNS): return False
    return True


def _empirical_zero_fire_accessors(min_trials: int = 3,
                                    db_path: str = DB_PATH) -> set[str]:
    """Live query: return accessors with 0% fire rate (≥`min_trials` trials)."""
    rates = accessor_fire_rates(min_trials=min_trials, db_path=db_path)
    return {acc for acc, s in rates.items() if s['fired'] == 0}


def pick_fresh_fields_under_explored(n: int = 8,
                                      gen_dir: str = str(WORKSPACE_ROOT / 'strategies/s001'),
                                      db_path: str = DB_PATH) -> list[str]:
    """Pick N fresh accessors biased toward LEAST-EXPLORED namespaces.

    Coverage audit 2026-05-09 revealed:
      _ac: 6%, _er: 12%, _cfs: 13%, _inc: 12%, _vr: 32%, _bs: 55%, _ers: 56%, _ops: 81%

    This picker rotates through least-covered namespaces first to maximize
    chance of breakthrough in untested domains. BAKE-J0-R1682 came from
    _bs_z.preferred_stock_equity (then-untested capital structure domain).
    """
    # Least-covered namespaces first
    priority_ns = ['_ac', '_er', '_cfs', '_inc', '_sr', '_vr', '_bs', '_ers', '_ops']
    # Query empirical never-fires once (cached for this picker call)
    zero_fire = _empirical_zero_fire_accessors(min_trials=3, db_path=db_path)
    all_fresh = []
    for ns in priority_ns:
        ns_fresh = pick_fresh_fields(n=40, namespaces=[ns], gen_dir=gen_dir, db_path=db_path)
        # Drop empirical 0% fire-rate accessors
        ns_fresh = [f for f in ns_fresh if f not in zero_fire]
        all_fresh.extend(ns_fresh)
        if len(all_fresh) >= n * 3: break  # over-pick to allow rotation
    # Round-robin pick to mix namespaces
    out = []
    by_ns_buckets = {ns: [] for ns in priority_ns}
    for acc in all_fresh:
        ns = acc.split('.')[0].replace('_z', '')
        by_ns_buckets.setdefault(ns, []).append(acc)
    while len(out) < n:
        added = False
        for ns in priority_ns:
            if by_ns_buckets[ns]:
                out.append(by_ns_buckets[ns].pop(0))
                added = True
                if len(out) >= n: break
        if not added: break
    return out[:n]


def pick_fresh_fields(n: int = 8, namespaces: list[str] | None = None,
                      gen_dir: str = str(WORKSPACE_ROOT / 'strategies/s001'),
                      db_path: str = DB_PATH) -> list[str]:
    """Return up to N fresh accessor strings (e.g., '_vr_z.cape_ratio') from
    the DB universe that have NEVER appeared in a gen_s001_R*.py or base file.

    namespaces: optional restrict to ['_vr', '_ops', '_bs', '_inc', '_cfs',
                                       '_ers', '_er', '_ac', '_sr', '_fs'].
    """
    import glob
    used: set[tuple[str, str, str | None]] = set()
    for path in glob.glob(f'{gen_dir}/gen_s001_R*.py') + glob.glob(f'{gen_dir}/s001/s001_*base*.py'):
        if any(skip in path for skip in ['gen_s001_lib', 'gen_s001_strategies', 'gen_s001_diagnostics']):
            continue
        try: src = Path(path).read_text()
        except OSError: continue
        for m in re.finditer(
            r'_(?:vr|ops|ers|ac|er|sr|fs|bs|inc|cfs)(?:_z)?\.([a-z_][a-z_0-9]*)(?:\.([a-z_][a-z_0-9]*))?',
            src):
            ns_match = re.match(r'_(?:vr|ops|ers|ac|er|sr|fs|bs|inc|cfs)', m.group(0))
            ns = ns_match.group(0).replace('_z', '')
            used.add((ns, m.group(1), m.group(2)))
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("SELECT accessor, category FROM fundamental_fields ORDER BY id")
    out: list[str] = []
    for accessor, category in cur.fetchall():
        if len(out) >= n: break
        parts = accessor.split('.')
        if len(parts) < 2: continue
        # DB stores accessor as '_ns.fld[.sub]' OR '_ns_z.fld[.sub]'; normalize to non-z
        ns_raw = parts[0]
        ns = ns_raw[:-2] if ns_raw.endswith('_z') else ns_raw
        fld = parts[1]
        sub = parts[2] if len(parts) > 2 else None
        if namespaces and ns not in namespaces: continue
        if (ns, fld, sub) in used or (ns, fld, None) in used: continue
        # Skip categorical / non-numeric fields that fail `> 1e6` (silent no-op).
        candidate = f'{ns}_z.{fld}' + (f'.{sub}' if sub else '')
        if not _is_likely_numeric_absolute(candidate): continue
        # Skip empirically-known never-fires accessors (R1690-R1701 audit:
        # 199 accessors had 0% fire rate, mostly bank/insurance/REIT fields
        # not represented in QQQ).
        if candidate in NEVER_FIRES_ACCESSORS: continue
        # Output the _z form for use in gen scripts (which inject as Python code)
        out.append(candidate)
    con.close()
    return out


# Empirical hit rates from R1645-R1660 audit (~1100 probes); used to predict
# round waste before queueing. Higher = more likely to fire productively.
# Mag bucket → estimated probability of (delta > +0.001).
_MAG_HIT_RATE = {
    # score additive
    ('+=', 0.005): 0.0, ('+=', 0.010): 0.0,
    ('+=', 0.020): 0.05, ('+=', 0.040): 0.025,
    ('+=', 0.080): 0.0, ('+=', 0.160): 0.0,
    ('+=', 0.320): 0.0,
    # mults — boost
    ('*=', 1.05): 0.0, ('*=', 1.08): 0.0, ('*=', 1.10): 0.0, ('*=', 1.13): 0.0,
    ('*=', 1.15): 0.0, ('*=', 1.20): 0.0, ('*=', 1.25): 0.025,
    ('*=', 1.30): 0.0, ('*=', 1.40): 0.0,  # 1.40 is poison
    ('*=', 1.50): 0.01, ('*=', 1.60): 0.10,
    ('*=', 1.70): 0.20, ('*=', 1.75): 0.0,
    ('*=', 1.80): 0.0, ('*=', 2.00): 0.10,
    # mults — demote (all 0% historical)
    ('*=', 0.30): 0.0, ('*=', 0.40): 0.0, ('*=', 0.50): 0.0,
    ('*=', 0.55): 0.0, ('*=', 0.60): 0.0, ('*=', 0.65): 0.0,
    ('*=', 0.70): 0.0, ('*=', 0.75): 0.0, ('*=', 0.80): 0.0,
    ('*=', 0.85): 0.0, ('*=', 0.90): 0.0, ('*=', 0.95): 0.0,
}


def predicted_waste(R) -> dict:
    """Estimate the round's expected null/positive yield based on
    empirical mag hit-rates. Returns {'expected_positive_specs', 'expected_pure_waste',
    'total_specs', 'efficiency_pct'}."""
    total = 0
    expected_pos = 0.0
    expected_waste = 0
    for p in R.probes:
        for m in p.mags or (1.0,):
            total += 1
            if p.op == 'continue':
                # skip-panic specs almost always NULL
                continue
            rate = _MAG_HIT_RATE.get((p.op, round(m, 3)), 0.0)
            if rate == 0.0:
                expected_waste += 1
            else:
                expected_pos += rate
    total += R.noops
    return {
        'total_specs': total,
        'expected_positive_specs': round(expected_pos, 2),
        'expected_pure_waste': expected_waste,
        'efficiency_pct': round((total - expected_waste) * 100 / total, 1) if total else 0,
    }


def fund_gate_fire_history(db_path: str = DB_PATH) -> dict[str, dict]:
    """Per fund accessor (e.g. '_ops_z.peg_ratio'), aggregate fire rate across
    all rounds. A 'fire' = the spec changed orders or car_mdd from NOOP.

    Returns {accessor: {'specs': N, 'fired': N, 'pos_001': N, 'fire_rate': float}}.
    Useful to skip probes whose fund gate has historically <1% fire rate.
    """
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name, car_mdd, total_orders FROM experiments
                   WHERE name LIKE 'S001_R%_lp_NOOP_%' AND car_mdd IS NOT NULL""")
    noop_by_rid: dict[int, list[tuple[float, int]]] = {}
    for n, cm, to in cur.fetchall():
        m = re.match(r'S001_R(\d+)_', n)
        if m: noop_by_rid.setdefault(int(m.group(1)), []).append((cm, to))
    cur.execute("""SELECT name, car_mdd, total_orders FROM experiments
                   WHERE name LIKE 'S001_R%_lp_%' AND name NOT LIKE '%NOOP%'
                   AND car_mdd IS NOT NULL""")
    rows = cur.fetchall(); con.close()

    # Map spec name to fund accessor by scanning gen scripts
    import glob
    name_to_accessor: dict[str, str] = {}
    for path in glob.glob(str(WORKSPACE_ROOT / 'strategies/s001/**/gen_s001_R*.py'), recursive=True):
        if any(skip in path for skip in ['gen_s001_lib','gen_s001_strategies','gen_s001_diagnostics']):
            continue
        try: src = Path(path).read_text()
        except OSError: continue
        # Match accessor strings like '_ops_z.foo.bar' or '_vr_z.foo'
        for m in re.finditer(
            r"['\"](_(?:vr|ops|ers|ac|er|sr|fs|bs|inc|cfs)_z\.[a-z_][a-z_0-9]*(?:\.[a-z_][a-z_0-9]*)?)['\"]",
            src):
            pass  # too noisy — would need full Probe parsing

    # Simpler: aggregate by full spec-name pattern (axis prefix)
    # to give per-axis fire rates; this is more useful in practice.
    by_axis: dict[str, dict] = {}
    for name, cm, to in rows:
        m = re.match(r'S001_R(\d+)_lp_(.+)$', name)
        if not m: continue
        rid, bare = int(m.group(1)), m.group(2)
        if rid not in noop_by_rid: continue
        noop_cm = sum(c for c, _ in noop_by_rid[rid]) / len(noop_by_rid[rid])
        noop_to = noop_by_rid[rid][0][1]
        # Strip mag suffix to get axis
        axis_m = re.match(r'^(.+)_([am]\d+)$', bare)
        axis = axis_m.group(1) if axis_m else bare
        slot = by_axis.setdefault(axis, {'specs': 0, 'fired': 0, 'pos_001': 0})
        slot['specs'] += 1
        delta = cm - noop_cm
        if to != noop_to or abs(delta) > 1e-6:
            slot['fired'] += 1
        if delta > 0.001:
            slot['pos_001'] += 1
    for a in by_axis.values():
        a['fire_rate'] = a['fired'] / a['specs'] if a['specs'] else 0
    return by_axis


def lift_distribution(rid: int, db_path: str = DB_PATH) -> dict:
    """Bucket a round's probes by lift (rounded to 5dp). Use to detect
    saturation: many probes hitting identical lift suggests cohort-not-gate
    is the discriminator → stop probing that cohort×lever combo.

    Returns {rounded_delta: count}, sorted by count desc.
    """
    noop_cm, noop_orders, _ = round_noop(rid, db_path)
    if noop_cm is None:
        noop_cm = latest_noop_baseline(db_path)
    if noop_cm is None: return {}
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT car_mdd FROM experiments
                   WHERE name LIKE ? AND name NOT LIKE '%NOOP%' AND car_mdd IS NOT NULL""",
                (f'S001_R{rid}_lp_%',))
    rows = cur.fetchall(); con.close()
    from collections import Counter
    buckets: Counter = Counter()
    for (cm,) in rows:
        d = round(cm - noop_cm, 5)
        buckets[d] += 1
    return dict(buckets.most_common())


def silent_noop_audit(rid: int, db_path: str = DB_PATH) -> dict:
    """Detect probes that produced byte-identical NOOP results — they
    didn't fire (cohort matched zero stocks, gate was always-false,
    or referenced an undefined variable that silently no-op'd via
    try/except). These are pure waste.

    Returns {'silent': [names], 'fired': N, 'total': N, 'silent_pct': float,
             'cohorts': {cohort_str: silent_count}} for the round.
    """
    noop_cm, noop_orders, _ = round_noop(rid, db_path)
    if noop_cm is None:
        return {'silent': [], 'fired': 0, 'total': 0, 'silent_pct': 0.0, 'cohorts': {}}
    con = storage.connect(db_path); cur = con.cursor()
    cur.execute("""SELECT name, car_mdd, total_orders FROM experiments
                   WHERE name LIKE ? AND name NOT LIKE '%NOOP%' AND car_mdd IS NOT NULL""",
                (f'S001_R{rid}_lp_%',))
    rows = cur.fetchall(); con.close()
    silent = []
    for n, cm, to in rows:
        if cm is not None and abs(cm - noop_cm) < 1e-5 and to == noop_orders:
            silent.append(n.replace(f'S001_R{rid}_lp_', ''))
    total = len(rows)
    fired = total - len(silent)
    return {
        'silent': silent,
        'fired': fired,
        'total': total,
        'silent_pct': (len(silent) / total * 100.0) if total else 0.0,
    }


def cohort_saturation_check(rid: int, threshold: int = 5,
                            db_path: str = DB_PATH) -> list[dict]:
    """Detect saturated cohorts in a round. If ≥`threshold` probes return
    the SAME lift (within precision), the cohort×lever×op combo is
    saturated — fund gates aren't discriminating, the cohort is.

    Returns list of {delta, count} for saturated lift buckets. Empty if
    no saturation detected.
    """
    dist = lift_distribution(rid, db_path)
    return [{'delta': d, 'count': c} for d, c in dist.items()
            if c >= threshold and d != 0.0]


if __name__ == '__main__':
    import sys
    rid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if rid:
        print('=== bake proposal ===')
        for b in propose_bakes(rid):
            print(f"  {b['axis']:<6} {b['tag']:<6} {b['op']} {b['mag']} d={b['delta']:+.5f} {b['name']}")
        print()
    print('=== latest NOOP ===')
    print(f'  {latest_noop_baseline()}')
    print()
    print('=== poison mags ===')
    for mag, axes in poison_mags().items():
        print(f'  m={mag}: hurts {sorted(axes)[:8]}{"..." if len(axes) > 8 else ""}')
    print()
    print('=== top firing axes (best 10 by best_delta) ===')
    hist = cohort_firing_history()
    top = sorted(hist.items(), key=lambda x: -x[1]['best_delta'])[:10]
    for axis, s in top:
        print(f"  {axis}: rounds={s['rounds']} fired={s['fired']}/{s['total_specs']} "
              f"best={s['best_delta']:+.5f}")


def harvest_uncashed_bakes(rid_start: int, rid_end: int,
                            db_path: str = DB_PATH,
                            min_delta: float = BAKE_THRESHOLD,
                            min_mags: int = 2) -> list[dict]:
    """Find multi-mag-confirmed bake candidates from past rounds that were
    NEVER applied via auto_apply_bake (typically because another candidate
    had higher delta in the same round).

    auto_apply takes the top non-overlapping bake per round; orthogonal
    multi-mag winners get left behind. This helper surfaces them so they
    can be re-queued for verification + bake.

    Returns list of {rid, axis, top_mag, top_delta, n_mags, cohort_hint}
    sorted by top_delta descending. Caller should re-queue these for
    verification on current base (lift may have shifted post-bake).
    """
    import json as _json
    import re as _re
    import qc_storage as _sql
    from collections import defaultdict as _dd

    with open(BAKES_LOG_PATH) as f:
        bakes = _json.load(f)
    applied_axes = {b.get('axis') for b in bakes}

    con = _sql.connect(db_path)
    uncashed = []
    for rid in range(rid_start, rid_end + 1):
        noop_rows = con.execute(
            "SELECT car_mdd FROM experiments WHERE name LIKE ? AND car_mdd IS NOT NULL",
            (f'S001_R{rid}_lp_NOOP%',)).fetchall()
        if not noop_rows:
            continue
        noop = sum(r[0] for r in noop_rows) / len(noop_rows)
        rows = con.execute(
            "SELECT name, car_mdd FROM experiments WHERE name LIKE ? "
            "AND car_mdd IS NOT NULL AND status='success'",
            (f'S001_R{rid}_%',)).fetchall()
        axis_mags = _dd(list)
        for name, cm in rows:
            if 'NOOP' in name:
                continue
            d = cm - noop
            m = _re.match(rf'S001_R{rid}_lp_(\w+?)_(m\d+|a-?\d+)$', name)
            if m and d > min_delta:
                axis_mags[m.group(1)].append((m.group(2), d))
        for axis, mags in axis_mags.items():
            if axis in applied_axes:
                continue
            if len(mags) >= min_mags:
                sorted_mags = sorted(mags, key=lambda x: -x[1])
                top_mag, top_delta = sorted_mags[0]
                uncashed.append({
                    'rid': rid,
                    'axis': axis,
                    'top_mag': top_mag,
                    'top_delta': top_delta,
                    'n_mags': len(mags),
                    'all_mags': dict(sorted_mags),
                })
    return sorted(uncashed, key=lambda x: -x['top_delta'])
