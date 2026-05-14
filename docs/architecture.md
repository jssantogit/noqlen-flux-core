# Architecture

Noqlen Flux Core starts as a service-first Python core. Reusable services should own workflow behavior, safety checks, planning, validation, and structured results. The CLI should remain a thin adapter that parses arguments, calls services, and renders output.

Flux is separate from Noqlen Forge Core. Forge is the reference for architecture, safety, documentation, tests, and release discipline, but Flux has a different domain: search, download coordination, staging, validation, quarantine/rejected handling, cleanup policy, and handoff.

Flux is not a direct continuation of the legacy `slsk` project. The legacy project is useful as a read-only reference for search and staging lessons, but Flux should avoid inheriting terminal coupling, local path assumptions, or provider-specific implementation shape.

Future UI, controller, bridge, or mobile layers must not contain heavy workflow logic. They should call stable service APIs and consume structured results or manifest files.

The bootstrap repository intentionally has no network integration, `slskd` integration, database, auto-import, watch list, or real cleanup behavior.

## Search Domain Models

Flux owns generic search models in the core domain: `SearchKind`, `SearchQuery`, `CandidateFile`, `SearchCandidate`, `SearchProviderResult`, and `ProviderHealth`. These names describe Flux concepts, not internal names from any external provider.

Locked files are represented at candidate-file level before any download workflow exists. This lets future planning and UI layers expose lock state without downloading or mutating files.

Conceptual placeholders such as `DownloadRequest`, `TransferStatus`, and `DownloadArtifact` define the future provider/core boundary without implementing download, queues, transfers, or artifacts on disk.

## Provider Boundary

Provider adapters implement the generic `SearchProvider` contract: `name`, `search(query)`, and `health()`. Core services depend on this contract only. They must not import `slskd`, native Soulseek code, terminal UI code, or provider-specific payloads.

The in-memory fake provider is the first adapter. It exists to test search flow offline, including warnings, controlled errors, timeouts, locked files, and album folders with multiple files. It performs no network calls and does not touch the filesystem.

A future `slskd` adapter should live under `providers/slskd` or an equivalent isolated module and translate external data into Flux-owned models. A future `NativeSoulseekProvider` should be able to implement the same contract and replace `slskd` without deep core changes.

## Candidate Scoring

Candidate scoring is a separate core domain from providers. Providers return `SearchCandidate` objects; `CandidateScoringService` scores those candidates with Flux-owned models such as `CandidateScore`, `ScoreComponent`, `ScoreReason`, `ScorePenalty`, `ScoringProfile`, and `ScoringResult`.

Scoring is explainable and calibrable. Every score should be backed by components, reasons, penalties, warnings, and a profile such as `default_v1`, so future MusicLab calibration can tune weights and thresholds without coupling core services to any provider implementation.

`CandidateRisk` is a pre-download risk signal, not a `QualityGrade`. It can highlight weak textual matches, locked files, missing file declarations, or suspicious pre-download terms, but it does not measure real audio quality and must not perform final routing, approval, rejection, quarantine, cleanup, or deletion.

The core remains provider-neutral. A future `slskd` provider or `NativeSoulseekProvider` must translate provider output into `SearchCandidate`; scoring must continue to depend on Flux models rather than external provider internals.

## Download Planning

Download planning is a separate core domain that transforms scored `SearchCandidate` objects into structured `DownloadPlan` objects. It does not execute transfers, create files, access the network, or interact with any real provider.

The flow is: `SearchProvider` returns `SearchCandidate` → `CandidateScoringService` produces `CandidateScore` → `DownloadPlanningService` creates `DownloadPlan`.

Download planning owns these models: `DownloadIntent`, `DownloadItem`, `DownloadConstraint`, `DownloadRequest`, `DownloadPlan`, and `DownloadPlanArtifact`. All models are Flux-owned and do not depend on any provider-specific names or internals.

`DownloadPlanningService` applies constraints such as `max_files`, `max_total_bytes`, `allow_locked`, `require_score_min`, and `allowed_extensions`. It blocks plans when candidates have no files, all files are locked with `allow_locked=false`, scores fall below the minimum, extensions are not permitted, or file/size limits are exceeded.

Plans use `PlannedChange` objects, not `AppliedChange`. Download planning is inherently a dry-run operation. Real execution will come in a separate future layer.

A future `slskd` adapter and a future `NativeSoulseekProvider` must both be compatible with this planning layer. The service accepts `SearchCandidate` and `CandidateScore` from the Flux domain and returns `DownloadPlan` without knowing which provider produced the candidate.

## Quality Analysis And Routing (Future)

Post-download quality analysis and routing will be separate layers from pre-download scoring:

- `QualityResult` — structured result from audio file inspection (ffmpeg, transcode analysis, spectrogram heuristics, decode health, clipping, low-pass detection).
- `QualityFinding` — individual observations such as spectral cutoffs, codec artifacts, or declared-vs-actual mismatches.
- `QualityGrade` — summary classification: `excellent` / `medium` / `bad`. This is NOT `CandidateRisk`.
- `RoutingDecision` — a separate service layer that combines `CandidateRisk`, `QualityGrade`, workspace policy, and user calibration to produce decisions: `approved` / `quarantine` / `rejected` / `delete_eligible`.
- `calibration_profile` — MusicLab sessions that tune scoring weights, quality heuristics, and routing thresholds against controlled fixtures before any real provider or download behavior is active.

Pre-download scoring (`CandidateScore`, `CandidateRisk`) must not grow into audio quality or routing decisions. The separation must remain: providers → scoring (pre-download) → download/transfer → quality (post-download) → routing (combined decision).

## Result Contracts

Flux services return structured `FluxResult` objects composed of statuses, steps, warnings, errors, artifacts, planned changes, applied changes, summaries, and timestamps. These contracts are serializable with safe `to_dict()` and `to_json()` methods so future controllers can consume data without scraping terminal output.

## Service Boundary

Services must not depend on `argparse`, terminal formatting, `print()`, `input()`, Rich, Click, or UI concerns. They should express workflow state through result objects and keep side-effect policy explicit.

`WorkspaceService` owns workspace inspection, dry-run planning, apply-mode directory creation, and path safety enforcement. It returns `FluxResult`, `StepResult`, `PlannedChange`, `AppliedChange`, warnings, and errors instead of terminal output.

`ReportService` owns report preview and writing. It builds JSON or text reports from `FluxResult` objects, returns planned or applied changes, and exposes report files as service artifacts. Report generation belongs to core services, not to the CLI.

`MusicLabService` owns the isolated calibration lab under `workspace/musiclab`. It validates the lab layout, plans or creates MusicLab directories, creates safe sessions, and writes only controlled fake fixtures. It returns `FluxResult`, `StepResult`, `PlannedChange`, `AppliedChange`, and `Artifact` objects; it does not print, parse CLI arguments, access providers, create audio, call the network, or touch a real music library.

`SearchService` owns the service-first search flow. It accepts a `SearchQuery` and any `SearchProvider`, calls the provider contract, and returns a `FluxResult` with steps, warnings, errors, summary data, and logical candidate artifacts. It does not download, create files, score quality, access the network, or know whether the provider is fake, `slskd`, or native Soulseek.

`CandidateScoringService` owns pre-download candidate scoring. It accepts `SearchQuery` and `SearchCandidate` data, returns structured scores, and can be invoked by `SearchService` only as an optional collaborator. It does not call providers, download files, create files, inspect audio, or know anything about `slskd`.

`DownloadPlanningService` owns download planning. It accepts `DownloadRequest` built from `SearchCandidate` and optional `CandidateScore`, applies `DownloadConstraint` rules, and returns a `FluxResult` with `PlannedChange` objects. It does not download files, create files, access the network, call providers, or know about `slskd`. It does not decide quality, routing, quarantine, or deletion. Plans are inherently dry-run; real execution will come in a separate future layer.

## MusicLab

MusicLab is the foundation for future scoring, quality, routing, quarantine/rejected, cleanup, and handoff calibration. Those workflows should be calibrated against isolated sessions and fake or generated fixtures before any real provider, download, staging, or handoff behavior exists.

MusicLab is service-first. The CLI only invokes `MusicLabService` and renders the returned structured result. Future controllers should do the same instead of duplicating calibration logic or bypassing safety checks.

## Reports And Artifacts

Reports are audit artifacts derived from structured results: operation status, summary, steps, warnings, errors, planned changes, applied changes, and artifacts. The report module provides deterministic-enough JSON for tests and simple human-readable text for inspection.

Report documents avoid raw provider payloads and sensitive fields by relying on safe result serialization and report-level path sanitization. They are intended for traceability of dry-run/apply decisions before future MusicLab, scoring, quality, or provider integrations exist.

## CLI Adapter

The CLI remains a thin adapter. It parses command-line arguments, calls services, renders human-readable output, and maps `Status` values to process exit codes.

Workspace CLI commands are adapters over `WorkspaceService`: `workspace inspect PATH` inspects the layout, while `workspace init PATH --dry-run` plans missing directories and `workspace init PATH --apply` creates them after service-level safety checks.

Report CLI commands are adapters over `ReportService`: `report demo --workspace PATH --format json --dry-run` previews a report artifact, while `--apply` writes it inside `PATH/reports`. The CLI does not assemble report content or bypass service safety checks.

MusicLab CLI commands are adapters over `MusicLabService`: `musiclab inspect`, `musiclab init`, `musiclab session create`, and `musiclab fixture create` parse arguments, call the service, render the result, and choose the process exit code. Default behavior remains dry-run unless `--apply` is explicit.

Search CLI commands are adapters over `SearchService`: `search fake track` and `search fake album` build `SearchQuery` objects, instantiate only the safe in-memory fake provider, optionally attach `CandidateScoringService` for `--score`, render the returned `FluxResult`, and choose the process exit code. The CLI does not implement provider logic, scoring logic, or download behavior.

Download planning CLI commands are adapters over `DownloadPlanningService`: `download plan fake track` and `download plan fake album` build `SearchQuery` objects, use the fake provider, optionally score the candidate, build a `DownloadRequest` with constraints, call `DownloadPlanningService`, and render the returned `FluxResult`. The CLI does not implement planning logic, download execution, or provider-specific behavior. All planning commands are dry-run by nature and have no `--apply` mode.

## Future Controllers

Future Android, UI, local API, or controller layers should call the same services directly. They should use structured results and future manifest contracts instead of duplicating workflow logic or depending on CLI text.
