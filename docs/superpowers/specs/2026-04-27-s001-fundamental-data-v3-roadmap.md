# S001 Fundamental Data v3 Roadmap — Future Sub-Projects

**Date:** 2026-04-27
**Status:** Roadmap notes; each sub-project gets its own design spec when started.

This doc captures the v3.x sequence agreed during the 2026-04-27 brainstorming session. Only **v3.0** (full-grid coarse sweep + adaptive prune + refine, see `2026-04-27-s001-fundamental-data-v3-design.md`) is designed and queued for implementation. The remaining sub-projects below are stubbed for future design.

---

## v3.0 — Full-Grid Coarse Sweep + Adaptive Prune (DESIGNED)

See `2026-04-27-s001-fundamental-data-v3-design.md`.

Test whether v2's narrow grid (15 cells, fixed op `>`, fixed default threshold) is missing signal:
- Add inverse op (`>` and `<`)
- Wider mag grid (4 values) + paired with op-inversion handles penalty
- Wider gate grid (3 values, same as v2)
- Threshold sweep using offline-scanned universe percentiles (`p25, p50, p75`)
- Coarse pass = 72 cells/field; adaptive dimension-prune; refine ±26 cells/field

---

## v3.1 — Time-Series Probes (FUTURE — moderate)

**Estimated:** 2-3 day plan.

### Premise

v1/v2/v3.0 only test single-period field values vs absolute thresholds. Real predictive signal often lies in trajectory: latest vs multi-year average, growth rate, acceleration. Many `*_growth` fields exist in the catalogue but aren't tested specifically as time-series.

### Probe template variants

| Template | Example | Accessor pattern |
|----------|---------|------------------|
| `latest_vs_avg` | `field.value > 1.05 * field.three_year_average.value` | needs both period accessors |
| `latest_vs_lag` | `field.value > field.previous_value` (or 1Q lag, 1Y lag) | period-aware |
| `growth_rate` | `(latest - lag) / lag > X` | computed at probe time |
| `accel` | `growth_rate_recent > growth_rate_lagged` | second-derivative |

### Implementation sketch

- Extend `accessor_for(row)` to optionally return tuple of accessors for multi-period probes.
- New `render_probe_timeseries(row, template_kind)` parallel to `render_probe`.
- New column `fundamental_fields.timeseries_template` (TEXT, NULL for static probes; one of `'latest_vs_avg', 'latest_vs_lag', 'growth_rate', 'accel'`).
- `pick_fields` learns to filter by template availability per category.
- v3.0 coarse/refine grids reused, parameterized by template kind.

### Open questions

- Which fields have multi-period accessors in the QC API? Need a one-time inventory pass.
- Threshold semantics differ for ratios vs absolutes; reuse v3.0 universe-percentile scanner with per-template percentiles.
- Backlog impact: adds ~30% to coarse cells if a field has 4 templates × 72 cells (avoid by template-specific picking).

### Non-goals

- Probability/PIT-based time-series models. Stay on rule-based gates for now.

---

## v3.2 — Composite Probes (FUTURE — high-value, structural shift)

**Estimated:** 3-5 day plan.
**Strategic note:** This is where the hand-coded BAKE-42/43/44/45 breakthroughs lived. The data most strongly suggests composite shape unlocks alpha that single-field shape cannot.

### Premise

Single-field gates have plateaued (75 v2 fields + 72 v3.0 cells/field, all ≤ 0). Real-world breakthroughs in this strategy combined 2-3 fields with AND/OR logic.

### Probe template variants

| Template | Example |
|----------|---------|
| 2-field AND | `growth > 0.10 AND margin > 0.20` |
| 2-field OR  | `pe < 15 OR fcf_yield > 0.05` |
| 3-field AND | `growth > 0.10 AND margin > 0.20 AND debt_ratio < 1` |
| field-vs-field ratio | `cash > debt` (no constants) |
| field-vs-field diff | `revenue_growth - cost_growth > 0.05` |

### Pair-selection problem

Cartesian explosion: 979 fields × 979 fields ≈ 1M pairs. Need smart selection:
- **Correlation-mined pairs**: rank pairs by similarity of their Phase 1 deltas; pairs with similar weak signal might combine to strong signal.
- **Hot × hot**: pairs of fields that each had `delta ≥ 0` in v3.0 results.
- **Hot × neutral**: a "near-zero" field combined with a slightly positive field can sometimes amplify.
- **Curated seed list**: hand-pick 20 high-yield pair candidates from analyst intuition (e.g., `growth × margin`, `pe × roic`).

### Implementation sketch

- New `composite_pair_candidates(db_path, k, bake_hash, strategy='correlation')` selector.
- New `render_probe_composite(rows, op_logic)` rendering function — handles 2-3 row tuples.
- Spec name compression: `S001_R{N}_v3comp_{cs1}_{f1}_{op_logic}_{cs2}_{f2}_m{mag}_g{gate}` truncated to 100 chars (UNIQUE constraint enforces).
- New `composite_probe_results` table OR extend `probe_results` with `field_id_2` (NULLable), `field_id_3`.
- Coarse grid expanded: per pair, 3 op_logic × 4 mags × 3 gates = 36 cells (no threshold sweep — uses each field's v3.0 winner threshold).

### Open questions

- Schema: separate `composite_probe_results` table or extend existing? Extend leans simpler.
- Threshold reuse: each pair's component fields use their own v3.0 winners as fixed thresholds (avoids re-sweeping each field's threshold inside composites).
- Storage: storing 1000 pairs × 36 cells = 36k probe_results entries per round. Manageable; sqlite scales.
- Bake-hash scoping unchanged.

### Non-goals

- 4+ field composites (combinatorial explosion; YAGNI).
- Continuous logic (`max`, `min` of fields). Boolean AND/OR only.

---

## v3.3 — Relative-Rank Probes (FUTURE — different runtime model)

**Estimated:** 3-5 day plan.

### Premise

All current probes use absolute thresholds: `field > X`. Threshold drift across baked versions matters; what's a "high P/E" today is different in 5 years. Relative-rank probes ask "is this stock in the top X% of QQQ on this field today?"

### Probe template variants

| Template | Example |
|----------|---------|
| Universe top-N% | `pct_rank(field, universe=qqq) > 0.8` |
| Universe bottom-N% | `pct_rank(field, universe=qqq) < 0.2` |
| Rank-based gate | `rank(field) <= 10` (top-10 names) |

### Runtime infrastructure

- At trade-decision time (`OnData` or scheduled handler), compute universe ranks for each ranked field.
- Inject a new `BIND_RANK` block that reads the QQQ universe, sorts by field, and produces `_rank_<field_id>` locals.
- `score *=` consumes the rank, e.g.:
  ```python
  if _rank_pe is not None and _rank_pe < 0.2: score *= 1.08
  ```
- Cost: ranking 100+ stocks × N fields per trade decision adds compute. Cache per session within a day.

### Implementation sketch

- New BIND block: `BIND_RANK = """..."""` injected after BIND.
- New `render_probe_rank(row, percentile, direction)`.
- Coarse grid: 4 percentiles × 4 mags × 3 gates = 48 cells (no separate threshold dimension; rank IS the threshold).
- Skip universe scanner — runtime computes ranks live.
- Spec naming: `S001_R{N}_v3rk_{cs}_{field}_{direction}_{pct_int}_m{mag}_g{gate}`.

### Open questions

- Performance: live universe ranking on every decision day. Bench first.
- Period selection: which period's value to rank? (v3.1 territory.)
- Categorical fields: skip — ranking undefined.

### Non-goals

- Rolling rank windows (today's rank vs 30-day-ago rank). Stay on instantaneous rank.

---

## Implementation order rationale

1. **v3.0 first** (current) — cheap-ish extension of v2; validates "the grid is too narrow" hypothesis directly. If v3.0 finds nothing positive, gives evidence single-field is exhausted regardless of grid size.
2. **v3.1 second** — moderate cost, no runtime changes, leverages v3.0 infra.
3. **v3.2 third** — biggest expected payoff per the data; can use v3.1's time-series fields as composites if available.
4. **v3.3 last** — new runtime model is the heaviest infra change; defer until v3.0/v3.1/v3.2 results inform whether the rank shape is worth the cost.

---

## Convention for future specs

When designing each sub-project:
1. Extend or replace this section's stub with the actual design spec at `docs/superpowers/specs/YYYY-MM-DD-s001-fundamental-data-v3{X}-design.md`.
2. Update this roadmap doc's status flags.
3. Each gets its own implementation plan at `docs/superpowers/plans/...`.
