# 0.9.2 design and pre-implementation self-review

Date: 2026-11-07. Predecessor: 0.9.1 bounded margin probe. This release retains the v090 feature engine and versions only local diagnostic tooling. No other writer or new version was observed during inspection. No AGENTS.md applied in the workspace or its ancestors.

## Findings

1. Runtime receipts have length and chunks but no integrity marker. A failed/retried publication or manual export can supply incomplete/mixed chunks. No independent consumer currently establishes receipt integrity or usability.
2. The assembler finds callback functions but ignores assignments to the same names. Adding a missing callback can overwrite a native lambda/alias/property. Multiple inheritance may also hide inherited behavior. Tabs and method docstrings are not preserved correctly by space-only entry insertion.
3. MarginProbe retains its caller's mutable plan; later mutation can bypass validation and alter an already constructed probe.

## Design

Preserve v091 and saved evidence. Create v092 modules with independent generated filenames/manifest version. Keep snapshots, windows and native account requests unchanged. Add a SHA256 receipt marker, invalidate it before any data write and publish the digest last. A successful immutable observation seals only after the digest write succeeds. Failed publication remains retryable. Each prefix uses 16 chunks, length and digest: at most 72 runtime statistics for four checkpoints. Hashes establish internal consistency, not origin authenticity or atomic external publication.

Add a standalone decoder. Require all exact chunks, valid bounded length, complete digest and canonical padding. Reject malformed JSON, nonfinite account data, unknown/incomplete snapshot shapes, error and capacity payloads, phase/time mismatch and observations outside the specified window. Return structured valid payloads; raise ValueError for invalid evidence. The decoder must run on exported statistics without QuantConnect installed. Add a CLI for independent inspection using explicit statistics and plan paths. Reject a whole planned evidence set if any checkpoint is missing; never silently accept partial capture.

Conservatively require a single direct QCAlgorithm base and reject callback-name bindings outside supported direct synchronous methods, including class assignments and nested control-flow bindings. Reject callback generators. Preserve method docstrings and use the existing source indentation for inserted hooks. Refuse generated identifier collisions. Existing callback bodies and native return values remain unchanged. Validate and deep-copy the plan at probe construction, normalize timestamp type errors into ValueError, and retain diagnostic exception isolation.

## Acceptance and self-review

Regression tests must demonstrate mixed-chunk/tamper rejection, interrupted publication and retry, snapshot/API error and capacity rejection, missing checkpoint rejection, time/phase/finite-data validation, caller plan mutation isolation, callback assignment/multiple-inheritance/generator rejection, tab indentation and method docstring preservation, and executable native return/request parity. Assemble the frozen official funded source, compile it, verify all file/base hashes, and run inherited suites.

Self-review disposition before implementation: proceed. A checksum alone cannot prove a QC origin or native scan ordering; document this limit. Validation must not trust arbitrary extra JSON fields as proof. Reject unsupported source rather than attempt semantic inference. Generated source remains unsubmitted. No changes to strategy funding, solver, risk management, live services or provider requests are justified. Cloud API compatibility, exact cloud account parity, native margin causation, IV historical cause, provider/feature coverage and economic acceptance remain open.
