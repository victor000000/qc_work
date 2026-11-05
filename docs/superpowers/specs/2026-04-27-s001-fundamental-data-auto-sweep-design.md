# S001 Fundamental Data: Auto Threshold/Gate Sweep + Bake-Hash Fix

**Date:** 2026-04-27
**Status:** Design — extends `2026-04-27-s001-fundamental-data-coverage-design.md` (v1)
**Scope:** Single implementation plan.

---

## 1. Problem

The v1 fundamental-data system catalogues 979 fields and emits per-round probes via `default_template()`. After 50+ rounds and 448 `probe_results` recorded, the v1 system shows:

- **Max recorded delta = +0.00019** in `probe_results`.
- **Actual breakthroughs found = +0.0037 (BAKE-42), +0.0034 (BAKE-43), +0.0052 (BAKE-44)** — all from hand-coded variations, NOT recorded in `probe_results`.

**Root cause:** `default_template()` heuristics (threshold `>1e9`, gate `decline > .12`, magnitude `score *= 1.08`) are systematically wrong for the QQQ universe. Hand-coded breakthroughs share a different pattern: same threshold, **shallower decline gate** (`.05` vs `.12`), **lower magnitude** (`1.05-1.06` vs `1.08-1.10`). The library never tests these variations because each field gets exactly one shot at the default template.

**Secondary bug** (per v1 spec §7.2): `pick_fields` ignores `bake_hash`, so classifications carry over after a bake. A field marked harmful on BAKE-41 stays harmful on BAKE-44 even though the v1 spec says it should reset.

## 2. Goals

1. **Two-phase sweep**: When a field's Phase 1 (default template) probe yields any non-zero delta (`|Δ| ≥ 0.0001`), automatically queue a Phase 2 sweep (5 magnitudes × 3 decline gates = 15 variants) the next round.
2. **Bake-hash scoping**: `pick_fields` filters by current `bake_hash` — old-bake classifications no longer occlude new-bake testing.
3. **Sweep winner tracking**: Best variant per field captured on `fundamental_fields` row for fast picker access.
4. **Backward compatible**: per-round generator call site unchanged. Existing `probe_results` rows preserved with `is_sweep_variant = 0`.

## 3. Non-goals

- Threshold sweeping (only mag and gate swept; threshold stays as authored in `fundamental_fields.probe_threshold`). Threshold sweep is deferred — observe outcomes from mag/gate sweep first.
- Hand-coded variant tracking (separate concern; auto-sweep should reduce reliance on hand-coded probes over time).
- Auto-promotion (sweep winners with `delta ≥ +0.003` surface in promotion query, but baking remains manual).
- Cross-bake comparison tooling.

## 4. Architecture

```
                                Round N+1
                                emit_probes_for_db()
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
   pick_fields(            pick_sweep_candidates(    pick_fields(
     classification=         bake_hash=current,       classification=
     'untested',             |delta|>=.0001,          'hot',
     bake_hash=current)      sweep_phase=0)           bake_hash=current)
              │                      │                      │
              ▼                      ▼                      ▼
       K_new=10 fields        K_sweep_fields=3 fields    M_verify=0-3
       (Phase 1 single)       × 15 = 45 sweep specs      (3-rep verify)
              │                      │                      │
              └──────────────────────┴──────────────────────┘
                                     │
                                     ▼
                            64-spec budget
                              (3 NOOP + 3 VERIFY + ~58 above)
                                     │
                                     ▼
                            score_round(round=N+1)
                                     │
                            INSERT probe_results
                            (is_sweep_variant=0 or 1)
                                     │
                                     ▼
                            For sweep-completed fields:
                              update sweep_winner_* on fundamental_fields
                              set sweep_phase = 2
                              update classification rollup
```

**Three new library functions, two modified.** Schema gains 6 columns and 1 index. No new tables.

## 5. Schema changes

### 5.1 Extend `fundamental_fields`

```sql
ALTER TABLE fundamental_fields ADD COLUMN sweep_phase INTEGER DEFAULT 0;
  -- 0 = Phase 1 default probe pending or just-completed; eligible for sweep if delta triggered
  -- 1 = Phase 2 sweep in flight (specs emitted, not all scored yet)
  -- 2 = Phase 2 sweep complete (results recorded)
ALTER TABLE fundamental_fields ADD COLUMN sweep_winner_op TEXT;
ALTER TABLE fundamental_fields ADD COLUMN sweep_winner_threshold TEXT;
ALTER TABLE fundamental_fields ADD COLUMN sweep_winner_gate TEXT;
ALTER TABLE fundamental_fields ADD COLUMN sweep_winner_boost REAL;
ALTER TABLE fundamental_fields ADD COLUMN sweep_winner_delta REAL;
  -- Best Phase 2 variant per field, denormalized for fast picker access
  -- Updated by score_round after Phase 2 completes
```

### 5.2 Extend `probe_results`

```sql
ALTER TABLE probe_results ADD COLUMN is_sweep_variant INTEGER DEFAULT 0;
  -- 0 = Phase 1 default probe result (existing behavior)
  -- 1 = Phase 2 sweep variant result
```

### 5.3 New index

```sql
CREATE INDEX idx_pr_field_bake ON probe_results(field_id, bake_hash);
  -- Speeds bake-aware picker join
```

### 5.4 Migration

No backfill required. Existing rows take the column defaults (`sweep_phase = 0`, `is_sweep_variant = 0`). Historical probe results stay v1-shaped and queryable.

### 5.5 Settings table addition

```sql
INSERT INTO settings (category, key, value, description, updated_at)
VALUES ('strategy', 'current_bake_hash', '<md5>', 'Current S001 base hash for bake-aware picking', CURRENT_TIMESTAMP);
```

`pick_fields` reads this when no explicit `bake_hash` argument is passed. Updated by user (or a small CLI) whenever a bake changes the base.

## 6. Sweep grid

### 6.1 Magnitudes × Gates (5 × 3 = 15 variants per field)

|         | mag 1.04 | mag 1.06 | mag 1.08 | mag 1.10 | mag 1.13 |
|---------|----------|----------|----------|----------|----------|
| **decline > .05** | v1 | v2 | v3 | v4 | v5 |
| **decline > .10** | v6 | v7 | v8 | v9 | v10 |
| **decline > .15** | v11 | v12 | v13 | v14 | v15 |

**Threshold** stays at `fundamental_fields.probe_threshold` (the value Phase 1 used). Not swept.

**Magnitude rationale:**
- 1.04 / 1.06 straddle observed cfsap winner (1.06).
- 1.08 = original library default.
- 1.10 / 1.13 test stronger boosts on rare triggers.

**Gate rationale:**
- .05 (shallow) — pattern that yielded breakthroughs.
- .10 (medium) — original library default.
- .15 (deep) — captures fields that only matter in panic regimes.

### 6.2 Spec naming

Format:
```
S001_R{round_n}_sw_{container_short}_{field_name}_m{mag_short}_g{gate_short}
```

Examples:
- `S001_R475_sw_cfs_change_in_account_payable_m104_g05`
- `S001_R475_sw_bs_cash_equivalents_m113_g15`
- `S001_R475_sw_vr_pe_ratio_m106_g10`

`sw` prefix distinguishes sweep specs from Phase 1 (`gt`/`lt`/`eq`/`in` op suffix) and from hand-coded specs.

`mag_short`: 3-4 digit no-decimal (`1.06` → `106`, `1.13` → `113`).
`gate_short`: 2-digit no-decimal (`.05` → `05`, `.15` → `15`).

Truncated to 100 chars; `UNIQUE(name)` on `backtest_queue` is the safety net.

### 6.3 Score regex extension

`score_probes.py` adds a sweep-name regex alongside the existing v1 regex:

```python
SWEEP_NAME_RE = re.compile(
    r'^S001_R(?P<round>\d+)_sw_(?P<cs>[a-z]+)_(?P<field>[a-z0-9_]+?)'
    r'_m(?P<mag>\d+)_g(?P<gate>\d+)$'
)
```

When a name matches the sweep regex:
1. Look up the field by `(container, field_name)`.
2. Reconstruct `applied_op` = `field.probe_op`, `applied_threshold` = `field.probe_threshold`.
3. Reconstruct `applied_gate` from `gate_short` (`05` → `'decline > .05'`).
4. Reconstruct `applied_boost` from `mag_short` (`106` → `1.06`).
5. INSERT into `probe_results` with `is_sweep_variant = 1`.

After all 15 variants for a field score (or after the round's `score_round` finishes), call `update_sweep_winner(field_id, bake_hash)`:
- Find variant with max delta in `probe_results` where `field_id = ? AND bake_hash = ? AND is_sweep_variant = 1`.
- Write its `(op, threshold, gate, boost, delta)` to `sweep_winner_*` columns.
- Set `sweep_phase = 2`.

## 7. Bake-hash fix

### 7.1 `pick_fields` becomes bake-aware

```python
def pick_fields(db_path, k, classification='untested', bake_hash=None):
    """Pick up to k fields with classification on the CURRENT bake_hash.

    For 'untested': fields with NO probe_results on this bake_hash.
    For 'hot'/'neutral'/'harmful': fields with at least one matching
    classification in probe_results for this bake_hash.
    """
    if bake_hash is None:
        bake_hash = current_bake_hash(db_path)  # reads from settings table

    queues = {}
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        for cont in CONTAINER_CYCLE:
            if classification == 'untested':
                cur.execute("""
                    SELECT * FROM fundamental_fields f
                    WHERE f.container = ?
                      AND f.probe_threshold IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM probe_results p
                        WHERE p.field_id = f.id AND p.bake_hash = ?
                      )
                    ORDER BY f.id ASC
                """, (cont, bake_hash))
            else:
                cur.execute("""
                    SELECT DISTINCT f.* FROM fundamental_fields f
                    JOIN probe_results p ON p.field_id = f.id
                    WHERE f.container = ? AND p.bake_hash = ?
                      AND p.classification = ?
                      AND f.probe_threshold IS NOT NULL
                    ORDER BY f.id ASC
                """, (cont, bake_hash, classification))
            queues[cont] = [dict(r) for r in cur.fetchall()]
    # ... existing container-cycle pop loop unchanged
```

### 7.2 `current_bake_hash(db_path)` helper

```python
def current_bake_hash(db_path):
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("""
            SELECT value FROM settings
            WHERE category = 'strategy' AND key = 'current_bake_hash'
        """)
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                "settings.current_bake_hash not set; "
                "run `UPDATE settings SET value=<md5> WHERE category='strategy' "
                "AND key='current_bake_hash'` after baking.")
        return row[0]
```

### 7.3 Effect

- Field scored harmful on BAKE-41 (`probe_results.bake_hash = 'b4619f...'`) NOT skipped on BAKE-44 (`probe_results.bake_hash = 'd941d5...'`) because the harmful row has wrong `bake_hash`.
- New bake = full universe re-eligible for Phase 1 picking.

## 8. New & modified library functions

### 8.1 New: `pick_sweep_candidates`

```python
def pick_sweep_candidates(db_path, k, bake_hash, min_abs_delta=0.0001):
    """Pick up to k fields with |Phase 1 delta| >= min_abs_delta AND sweep_phase = 0.
    
    Sorted by max(|delta|) DESC so highest-impact fields sweep first.
    Returns list of dict rows from fundamental_fields (with template attached).
    """
    sql = """
    SELECT f.*, MAX(ABS(p.delta)) AS max_abs_delta
    FROM fundamental_fields f
    JOIN probe_results p ON p.field_id = f.id
    WHERE p.bake_hash = ?
      AND p.is_sweep_variant = 0
      AND ABS(p.delta) >= ?
      AND f.sweep_phase = 0
      AND f.probe_threshold IS NOT NULL
    GROUP BY f.id
    ORDER BY max_abs_delta DESC
    LIMIT ?
    """
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(sql, (bake_hash, min_abs_delta, k))
        return [dict(r) for r in cur.fetchall()]
```

### 8.2 New: `emit_phase2_sweep`

```python
SWEEP_MAGS = ['1.04', '1.06', '1.08', '1.10', '1.13']
SWEEP_GATES = ['.05', '.10', '.15']


def emit_phase2_sweep(field_row, round_n):
    """Emit 15 (name, code) tuples for one field's Phase 2 sweep."""
    out = []
    for mag in SWEEP_MAGS:
        for gate in SWEEP_GATES:
            row = dict(field_row)
            row['probe_boost'] = float(mag)
            row['probe_gate'] = f'decline > {gate}'
            body = render_probe(row)
            mag_short = mag.replace('.', '')
            gate_short = gate.replace('.', '').lstrip('-') or '0'
            cs = CONTAINER_SHORT[field_row['container']]
            name = (f"S001_R{round_n}_sw_{cs}_{field_row['field_name']}"
                    f"_m{mag_short}_g{gate_short}")[:100]
            out.append((name, body))
    return out
```

### 8.3 New: `update_sweep_winner`

```python
def update_sweep_winner(con, field_id, bake_hash):
    """After Phase 2 sweep completes, find best variant and write to
    fundamental_fields.sweep_winner_* columns. Set sweep_phase = 2."""
    cur = con.cursor()
    cur.execute("""
        SELECT applied_op, applied_threshold, applied_gate, applied_boost, delta
        FROM probe_results
        WHERE field_id = ? AND bake_hash = ? AND is_sweep_variant = 1
        ORDER BY delta DESC LIMIT 1
    """, (field_id, bake_hash))
    row = cur.fetchone()
    if row is None:
        return  # no sweep variants yet; not ready
    op, thr, gate, boost, delta = row
    cur.execute("""
        UPDATE fundamental_fields
        SET sweep_winner_op = ?, sweep_winner_threshold = ?,
            sweep_winner_gate = ?, sweep_winner_boost = ?,
            sweep_winner_delta = ?, sweep_phase = 2
        WHERE id = ?
    """, (op, thr, gate, boost, delta, field_id))
```

### 8.4 Modified: `emit_probes_for_db`

Add `k_sweep_fields` parameter. Default 3.

```python
def emit_probes_for_db(db_path, round_n, k_new=10, k_verify=0,
                       k_sweep_fields=3, include_bind=False):
    bake_hash = current_bake_hash(db_path)
    
    new_picks = pick_fields(db_path, k_new, 'untested', bake_hash)
    sweep_picks = pick_sweep_candidates(db_path, k_sweep_fields, bake_hash)
    hot_picks = pick_fields(db_path, k_verify, 'hot', bake_hash)
    
    out = []
    
    for row in new_picks:
        # existing v1 Phase 1 emission, unchanged
        body = render_probe(row)
        if include_bind:
            body = BIND + body
        out.append((spec_name(row, round_n), body))
    
    for row in sweep_picks:
        sweep_specs = emit_phase2_sweep(row, round_n)
        if include_bind:
            sweep_specs = [(n, BIND + b) for n, b in sweep_specs]
        out.extend(sweep_specs)
        # mark sweep_phase = 1 to prevent re-emission next round
        with sqlite3.connect(db_path) as con:
            con.execute(
                "UPDATE fundamental_fields SET sweep_phase = 1 WHERE id = ?",
                (row['id'],))
    
    for row in hot_picks:
        # existing 3-rep verify behavior
        ...
    
    return out
```

### 8.5 Modified: `score_round`

After existing scoring loop, add sweep handling:

```python
# Existing v1 score loop populates probe_results with is_sweep_variant=0 or 1
# based on which regex (default vs sweep) matched the spec name.

# After all round's specs are scored, find fields where ALL 15 sweep
# variants have results (sweep is fully complete) and update sweep_winner.
cur.execute("""
    SELECT field_id, COUNT(*) AS n_swept
    FROM probe_results
    WHERE round_n = ? AND bake_hash = ? AND is_sweep_variant = 1
    GROUP BY field_id
    HAVING n_swept = 15
""", (round_n, bake_hash))
for (field_id, _) in cur.fetchall():
    update_sweep_winner(con, field_id, bake_hash)
```

If a field has fewer than 15 sweep results in this round (e.g., 12 of 15 done because some failed), `update_sweep_winner` runs only when the remaining 3 complete in a later round's score pass.

## 9. Promotion query (updated)

The v1 promotion query for hot Phase 1 results stays unchanged. Add a sweep-winner promotion query:

```sql
-- Sweep-winner promotion candidates (sweep_phase=2 means sweep complete)
SELECT f.field_name, f.container,
       f.sweep_winner_op AS op,
       f.sweep_winner_threshold AS threshold,
       f.sweep_winner_gate AS gate,
       f.sweep_winner_boost AS boost,
       f.sweep_winner_delta AS delta
FROM fundamental_fields f
WHERE f.sweep_phase = 2
  AND f.sweep_winner_delta >= 0.003
ORDER BY f.sweep_winner_delta DESC;
```

Sweep-winner candidates with `delta ≥ +0.003` are bake-eligible. The user runs a 3-rep verify next round to confirm determinism before baking.

## 10. Per-round generator integration

Existing per-round generator call site:
```python
specs.extend(emit_probes_for_db(db_path, round_n=N, k_new=10, k_verify=0))
```

Becomes:
```python
specs.extend(emit_probes_for_db(db_path, round_n=N, k_new=10, k_verify=0, k_sweep_fields=3))
```

That's the only generator-side change. The new arg is optional (default 3) so existing generators continue working without modification — they just get sweep specs included automatically.

## 11. Spec count budget per round

**Round size is a floor, not a cap.** The cron prompt asks for "≥64 specs" — generators may queue more when the auto-sweep needs the capacity. Per the memory rule `feedback_s001_round_size_flexible`, do NOT truncate sweep output to fit 64.

Typical composition:
- 3 NOOP + 3 VERIFY = 6 (generator's hand-written baseline confirmation)
- 10 Phase 1 default probes (`k_new = 10`)
- 45 Phase 2 sweep specs (3 fields × 15 variants) when k_sweep_fields=3
- 0+ hot verify (after sweep winners surface)

When K eligible Phase 2 fields > k_sweep_fields, increasing `k_sweep_fields` is encouraged — `5 × 15 = 75` plus `10 + 6 = 16` = 91 specs in a single round is fine. The generator decides per-round based on how many fields earned a sweep.

When `pick_sweep_candidates` returns fewer than `k_sweep_fields` rows (early rounds), freed budget can go to more `k_new` Phase 1 probes (the generator caller decides). The library does not impose a 64-spec cap.

## 12. Testing

### 12.1 Library tests

| Function                | Test                                                          |
|-------------------------|---------------------------------------------------------------|
| `pick_fields(...)`      | Filters by bake_hash; returns 'untested' for fields with no current-bake results even if classified harmful on old bake |
| `pick_sweep_candidates` | Returns fields with `|delta| ≥ 0.0001` AND `sweep_phase = 0`; sorted by max |delta| DESC; respects `k` limit |
| `emit_phase2_sweep`     | Returns exactly 15 (name, code) tuples per field; names follow `_sw_` convention; bodies pass `ast.parse` |
| `update_sweep_winner`   | Picks max-delta variant; writes 5 winner columns; sets `sweep_phase = 2` |
| `current_bake_hash`     | Reads from settings; raises if unset                          |

### 12.2 score_probes test extensions

| Test                          | Assertion                                              |
|-------------------------------|--------------------------------------------------------|
| `test_score_recognizes_sweep_name` | Sweep spec → INSERT with `is_sweep_variant = 1` and reconstructed `applied_*` |
| `test_score_updates_sweep_winner`  | After 15 variants score for a field, `sweep_winner_*` populated, `sweep_phase = 2` |
| `test_partial_sweep_no_winner`     | After only 12/15 score, `sweep_winner_*` NOT yet written, `sweep_phase` stays 1 |

### 12.3 emit_probes test extensions

| Test                                    | Assertion                                |
|-----------------------------------------|------------------------------------------|
| `test_emit_includes_sweep_when_eligible`| Seed 1 field with `delta = 0.0005`, `sweep_phase = 0` → `emit_probes_for_db` returns 15 sweep specs for it |
| `test_emit_skips_swept_fields`          | Seed field with `sweep_phase = 1` or `2` → `pick_sweep_candidates` ignores it |
| `test_emit_marks_sweep_phase_1`         | After emit, queried field has `sweep_phase = 1`         |

### 12.4 End-to-end smoke (manual)

1. Apply schema migration to S001.db.
2. Seed `settings.current_bake_hash` with current value.
3. Run `gen_s001_R{N}.py` once with `k_sweep_fields=3`. Confirm 64 specs queued including 45 `_sw_` named specs.
4. After backtest run + import, `python -m scripts.score_probes --round N`. Confirm 15 `is_sweep_variant=1` rows per swept field; `sweep_winner_*` populated; `sweep_phase = 2`.
5. Run promotion query. Confirm any field with `sweep_winner_delta ≥ +0.003` appears.

## 13. File layout

```
/home/txy/qc_work/data/
├── s001/
│   └── fundamental_probes.py          # MODIFIED: +3 functions, +2 modified, +sweep constants
├── scripts/
│   ├── catalogue_universe.py          # unchanged
│   ├── emit_probes.py                 # unchanged (passes through new arg)
│   ├── migrate_schema.py              # MODIFIED: adds 6 ALTERs + index
│   └── score_probes.py                # MODIFIED: sweep regex + update_sweep_winner call
├── tests/                             # MODIFIED: 3 new tests in test_fundamental_probes,
│                                      #           3 in test_score_probes, 3 in test_emit_probes
└── gen_s001_R{N}.py                   # generator: pass k_sweep_fields=3
```

## 14. Migration sequence

1. Update `scripts/migrate_schema.py` with the 6 new ALTERs + index. Apply to S001.db.
2. INSERT initial `settings.current_bake_hash` row with the current BAKE-44 hash.
3. Implement library + tests; verify all green.
4. Update `gen_s001_R{N}.py` template (or just R462+) to pass `k_sweep_fields=3`.
5. Run R462 with new sweep emission. Monitor results.
6. After R462 + R463 cycle: confirm sweep variants land in `probe_results` with `is_sweep_variant = 1`; sweep winners populated; promotion query produces candidates.

## 15. Risks & mitigations

| Risk                                                    | Mitigation                                                 |
|---------------------------------------------------------|-------------------------------------------------------------|
| Sweep produces 15 specs all neutral on a field          | Acceptable — `sweep_phase = 2` prevents re-sweep; budget recovers next round |
| Phase 1 trigger threshold (≥0.0001) too generous, sweeps everything | Tune up if observed; `min_abs_delta` is a parameter |
| Bake-hash filter breaks existing v1 generators that didn't pass `bake_hash` | `pick_fields` defaults to `current_bake_hash()` from settings — backward compatible |
| Sweep grid (5×3=15) too narrow to catch winner          | Threshold sweep can be added in v3; mag/gate already covers 60% of breakthrough discovery space (per observed cases) |
| Two-phase latency: a delta in round N waits for round N+1 to sweep | Acceptable; cron is 5 min; lag is one cron cycle |
| Score regex edge case: field name contains `m` or `g`   | Regex anchors on `_m\d+_g\d+$` — only matches at end of name; field names can contain those letters internally |

## 16. Out-of-scope future work

- **Threshold sweep**: 3rd dimension on the sweep grid (currently fixed at field's authored threshold).
- **Adaptive sweep grid**: bigger grid for bigger Phase 1 deltas (proposed but rejected for v2 simplicity).
- **Hand-coded variant tracking**: capture user-written probes outside the auto-naming pattern.
- **Cross-bake trend analysis**: does a sweep winner survive bake changes?
- **Auto-promotion**: bake the sweep winner directly without manual review (always manual per spec §13 of v1).
- **Multi-axis joint sweep**: sweep two fields simultaneously to capture stacks (e.g., `cfsap_decl_05 + bs_cash_decl_10` jointly tuned).

These are deferrable to follow-up specs. v2 is bounded to mag/gate sweep + bake-hash fix.
