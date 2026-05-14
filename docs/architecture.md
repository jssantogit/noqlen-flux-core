# Architecture

Noqlen Flux Core starts as a service-first Python core. Reusable services should own workflow behavior, safety checks, planning, validation, and structured results. The CLI should remain a thin adapter that parses arguments, calls services, and renders output.

Flux is separate from Noqlen Forge Core. Forge is the reference for architecture, safety, documentation, tests, and release discipline, but Flux has a different domain: search, download coordination, staging, validation, quarantine/rejected handling, cleanup policy, and handoff.

Flux is not a direct continuation of the legacy `slsk` project. The legacy project is useful as a read-only reference for search and staging lessons, but Flux should avoid inheriting terminal coupling, local path assumptions, or provider-specific implementation shape.

Future UI, controller, bridge, or mobile layers must not contain heavy workflow logic. They should call stable service APIs and consume structured results or manifest files.

The bootstrap repository intentionally has no network integration, `slskd` integration, database, auto-import, watch list, or real cleanup behavior.

## Result Contracts

Flux services return structured `FluxResult` objects composed of statuses, steps, warnings, errors, artifacts, planned changes, applied changes, summaries, and timestamps. These contracts are serializable with safe `to_dict()` and `to_json()` methods so future controllers can consume data without scraping terminal output.

## Service Boundary

Services must not depend on `argparse`, terminal formatting, `print()`, `input()`, Rich, Click, or UI concerns. They should express workflow state through result objects and keep side-effect policy explicit.

`WorkspaceService` owns workspace inspection, dry-run planning, apply-mode directory creation, and path safety enforcement. It returns `FluxResult`, `StepResult`, `PlannedChange`, `AppliedChange`, warnings, and errors instead of terminal output.

`ReportService` owns report preview and writing. It builds JSON or text reports from `FluxResult` objects, returns planned or applied changes, and exposes report files as service artifacts. Report generation belongs to core services, not to the CLI.

## Reports And Artifacts

Reports are audit artifacts derived from structured results: operation status, summary, steps, warnings, errors, planned changes, applied changes, and artifacts. The report module provides deterministic-enough JSON for tests and simple human-readable text for inspection.

Report documents avoid raw provider payloads and sensitive fields by relying on safe result serialization and report-level path sanitization. They are intended for traceability of dry-run/apply decisions before future MusicLab, scoring, quality, or provider integrations exist.

## CLI Adapter

The CLI remains a thin adapter. It parses command-line arguments, calls services, renders human-readable output, and maps `Status` values to process exit codes.

Workspace CLI commands are adapters over `WorkspaceService`: `workspace inspect PATH` inspects the layout, while `workspace init PATH --dry-run` plans missing directories and `workspace init PATH --apply` creates them after service-level safety checks.

Report CLI commands are adapters over `ReportService`: `report demo --workspace PATH --format json --dry-run` previews a report artifact, while `--apply` writes it inside `PATH/reports`. The CLI does not assemble report content or bypass service safety checks.

## Future Controllers

Future Android, UI, local API, or controller layers should call the same services directly. They should use structured results and future manifest contracts instead of duplicating workflow logic or depending on CLI text.
