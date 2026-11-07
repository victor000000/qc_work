# 0.9.1 bounded native margin investigation

Date: 2026-11-07. Status: design reviewed before implementation; local engineering release.

## Problem and objective

The C0 account still encounters a native margin failure. Historical MB/MA receipts are post-fill, so they cannot explain pre-trigger group composition. The November 7 v090 immutable writer fixes overwriting but has no integrated bounded probe. IV replay nonrecurrence supplies no historical failing contract or solver cause. Build a reproducible diagnostic source to collect better evidence without changing execution, quotes, capital, or native risk requests.

## Architecture and contract

Keep the v090 feature engine and all historical source/evidence intact. Add a v091 probe module and standalone source assembler. A probe plan contains 1–4 unique prefixes matching M[A-Z0-9]{1,7}, callback phase (`on_data`, `on_order_event`, `on_margin_call`), and inclusive start/end naive ISO datetimes in the algorithm's own clock. Each window lasts at most one session (24 hours); phases are caller context only. First eligible invocation seals its receipt. Missed windows produce no receipt and cannot count as valid evidence. Record observed time and callback; a delayed observation never inherits its requested time. Order-event receipts refer to any order event, not necessarily a fill.

Each receipt includes native equity, cash, used/remaining margin, holdings, native group reserve and each group's position symbol/quantity. Missing APIs produce explicit error evidence. Use the existing 16 x 180-character runtime-statistic transport; oversized snapshots produce capacity errors. At most four prefixes cap output at 68 statistics. Diagnostic exceptions, including publication failures, must not propagate into trading callbacks. A failed write remains retryable; an error payload is sealed and requires a new probe to collect usable evidence.

The assembler parses the base AST, requires one direct QCAlgorithm class and ordinary supported callback signatures, then inserts telemetry at callback entry. Existing callback bodies and return values remain intact. Missing margin callbacks return the original requests; other missing callbacks do nothing after observation. Reject decorators, async/ambiguous classes, reserved identifier collisions, and unsupported signatures. Embed validated plan, standalone modules, and SHA256 provenance for base, plan and every generated file. Require a new output directory and compile all emitted source before writing. No cloud submission occurs in assembly.

## Evidence and acceptance

Local acceptance: validate plans; prove window boundaries, immutable independent phases, bounded payloads and retry/failure isolation; execute assembled synthetic callbacks and compare original order-event behavior and request identity; verify malformed sources rejected and manifest hashes. Run the full existing 430-test scope plus v091 tests. These tests verify instrumentation, not native ordering or margin causation.

Next cloud acceptance: use fresh matched baseline/probe identities and frozen dates/parameters. Require complete publication and exact order/cash/equity parity before interpreting diagnostics. Independently decode all receipts, reject missing/error/capacity payloads, and retain failed native runs. A timestamp in on_data does not establish position relative to the engine's margin scan. Pre-trigger claims need an actual engine-ordering trace or documented native ordering plus group composition. Sidecar feature parity, strict provider availability and funded economics stay separate open gates.

## Self-review before implementation

1. Rejected an automatic margin or IV fix: neither root cause is established.
2. Rejected naming an observation “pre-trigger”: callback timing does not prove scan ordering.
3. Rejected unbounded event capture: fixed 1–4 windows constrain runtime statistics.
4. Added failure isolation around the entire diagnostic path, including the transport.
5. Added AST validation and source identity: text-only replacements can silently modify the wrong class or lose existing callbacks.
6. Retained missing/error evidence as failure, never inferred success. Group membership API incompatibility will be visible and must be validated in QC cloud.
7. Avoided duplicating the entire axis engine under a new version: this release versions the diagnostic capability only; inherited feature artifacts retain their v090 identities.

Review disposition: implement this bounded scope. Cloud parity, native API compatibility and economic acceptance remain pending after local implementation.
