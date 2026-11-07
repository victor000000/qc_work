# Documentation guide

Reviewed against source on 2026-11-07. Executor 1.2.0, feature engine 0.9.0 and diagnostic tooling 0.9.2 have independent version identities.

| Task | Canonical reference |
|---|---|
| Install native Linux/WSL environment | [Environment](ENVIRONMENT.md) |
| Understand execution and failure ownership | [Architecture](ARCHITECTURE.md) |
| Configure paths, credentials and projects | [Configuration](CONFIGURATION.md), [credentials](CREDENTIALS.md) |
| Use the CLI | [Usage](../USAGE.md); actual `--help` is the option authority |
| Operate or recover a runtime | [Operations](OPERATIONS.md) |
| Access queues or export research data | [DuckDB/Parquet protocol](DUCKDB_MIGRATION.md) |
| Develop and run checks | [CI and local tests](CI_CD.md) |
| Navigate research code, contracts and reproduction | [Project handbook](PROJECT_HANDBOOK.md) |
| Understand diagnostic source/receipts | [0.9.2 implementation](../strategies/sstrangle/poc/v092/README.md), [reviewed design](../strategies/sstrangle/research/design_20261107_v092/DESIGN.md) |
| Find present acceptance gaps and dated evidence | [Current work](CURRENT_WORK.md), [next steps](TODO.md) |
| Understand omitted public artifacts | [Publication](../PUBLICATION.md) |
| Review documentation coverage and limitations | [Audit inventory](DOCUMENTATION_AUDIT.md) |

Current guides explain implemented behavior. Versioned designs describe their named implementations or explicit proposals. Dated verification, migration, research and release records are historical evidence; preserve their dates and source identities. Neither an old completed checklist nor an old “current” heading certifies today's account/runtime state.

Historical links into `results/`, omitted datasets, PDFs, nested repositories, `.local/`, or adjacent projects can be unavailable in a public checkout. Their absence is not proof of the underlying result and is not an instruction to recreate private data. The documentation audit records those boundaries separately from broken canonical navigation.

When changing behavior, update its canonical guide and tests together. Keep status in Current work and pending dependencies in Next steps. Link to the owning guide instead of copying configuration tables into every README. The documentation checker validates selected public navigation and inventories all owned Markdown links; it does not validate external URLs, historical economics or runtime state.
