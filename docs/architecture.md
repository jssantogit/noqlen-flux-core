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

Provider adapters implement the generic `SearchProvider` and `TransferProvider` contracts through a shared `BaseProvider` interface: `name`, `capabilities()`, and `health()`. Core services depend on these contracts only. They must not import `slskd`, native Soulseek code, terminal UI code, or provider-specific payloads.

The in-memory fake providers are the first adapters. They exist to test search and transfer flow offline, including warnings, controlled errors, timeouts, locked files, and album folders with multiple files. They perform no network calls and do not touch the filesystem.

A future `slskd` adapter should live under `providers/slskd` or an equivalent isolated module and translate external data into Flux-owned models. A future `NativeSoulseekProvider` must be able to implement the same contract and replace `slskd` without deep core changes.

## Provider Health And Capabilities

Flux owns generic provider status models that describe availability, capabilities, and operational state without referencing any specific backend:

- `ProviderKind` — classifies the provider type: `fake`, `lab`, `external`, `native`, `unknown`.
- `ProviderCapability` — declares what a provider can do: `search`, `download_planning`, `queue_planning`, `transfer_status`, `health`, `artifacts`.
- `ProviderAvailability` — describes operational state: `available`, `degraded`, `unavailable`, `unknown`.
- `ProviderHealth` — combines kind, availability, capabilities, warnings, errors, and safe metadata into a single health snapshot.
- `ProviderStatus` — wraps `ProviderHealth` with optional transfer/queue counts and a timestamp.
- `ProviderCapabilityReport` — lists supported and unsupported capabilities for a given provider.

Core services ask generic providers for `health()` and `capabilities()`. The returned `ProviderHealth` and capability lists are Flux-owned models. A future `slskd` adapter must map its backend status into `ProviderHealth`. A future `NativeSoulseekProvider` must implement the same contract.

`ProviderService` provides service-level inspection, health checks, and capability validation. It accepts any `BaseProvider`, calls the generic contracts, and returns `FluxResult` with structured steps, warnings, errors, and logical artifacts. It does not access the network, download files, create files, or know about `slskd`.

Search providers implement `SearchProvider` (a `BaseProvider` subclass): `name`, `capabilities()`, `health()`, and `search(query)`. Transfer providers implement `TransferProvider` (also a `BaseProvider` subclass): `name`, `capabilities()`, `health()`, `plan_queue(request)`, and `get_status(queue_item_id)`.

The fake providers declare their capabilities and return consistent `ProviderHealth` with `ProviderKind.FAKE`. They support simulating `available`, `degraded`, and `unavailable` states for testing.

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

## Transfer And Queue Planning

Transfer and queue planning is a separate core domain that transforms `DownloadPlan` objects into structured `QueuePlan` objects with `TransferItem`, `QueueItem`, and `TransferStatus` contracts. It does not execute transfers, create files, access the network, or interact with any real provider.

The flow is: `SearchProvider` → `SearchCandidate` → `CandidateScoringService` → `CandidateScore` → `DownloadPlanningService` → `DownloadPlan` → `TransferPlanningService` → `QueuePlan`.

Transfer/queue planning owns these models: `TransferState`, `QueueState`, `TransferPriority`, `TransferItem`, `TransferRequest`, `QueueItem`, `QueuePlan`, `TransferStatus`, and `TransferArtifact`. All models are Flux-owned and do not depend on any provider-specific names or internals.

`TransferPlanningService` converts `DownloadItem` objects into `TransferItem` and `QueueItem` objects, respects locked file information from the download plan, and generates warnings for locked items. It blocks queue plans when the download plan is blocked or has no items.

Queue plans use `PlannedChange` objects, not `AppliedChange`. Transfer planning is inherently a dry-run operation. Real execution will come in a separate future layer with an isolated transfer provider.

A future `slskd` adapter and a future `NativeSoulseekProvider` must both implement the `TransferProvider` contract (`name`, `health()`, `plan_queue()`, `get_status()`) without requiring core changes. The `TransferProvider` contract is generic and provider-neutral.

`TransferPlanningService` does not download files, create files, access the network, call providers, or know about `slskd`. It does not decide quality, routing, quarantine, or deletion. Plans are inherently dry-run; real execution will come in a separate future layer with a provider adapter.

## Quality Analysis Foundation

Post-download quality analysis is a separate core domain from pre-download scoring and download/transfer planning. This commit introduces the contracts and fake simulation layer for future audio file inspection.

Flux owns these quality models:

- `QualityGrade` — post-download quality classification: `excellent`, `medium`, `bad`, `unknown`. This is NOT `CandidateRisk`. `CandidateRisk` is a pre-download risk signal; `QualityGrade` represents analysis of the actual downloaded file.
- `QualityFindingSeverity` — severity of individual findings: `info`, `warning`, `error`.
- `QualityFindingKind` — type of finding: `objective_failure`, `heuristic_warning`, `diagnostic`, `metadata_signal`, `unknown`.
- `QualityFinding` — individual observation with code, message, kind, severity, optional confidence, and safe metadata.
- `QualityProfile` — versioned calibration profile with name, version, description, thresholds, and safe metadata. MusicLab will calibrate thresholds before any real provider or audio analysis is active.
- `QualityResult` — structured result from file inspection: item_id, optional relative_path, grade, findings, objective_failures, heuristic_warnings, diagnostics, confidence, profile, warnings, errors, and safe metadata.
- `QualitySummary` — aggregate counts across multiple results: total_items, excellent_count, medium_count, bad_count, unknown_count, warning_count, error_count.

`QualityService` provides service-level fake quality evaluation and summarization. It accepts structured fake data and returns `FluxResult` with steps, warnings, errors, and logical quality artifacts. It does not access the network, download files, create files, read audio, use ffmpeg, perform transcode analysis, or know about `slskd`.

Quality analysis does not perform routing, quarantine, rejection, or deletion. `QualityResult` does not contain `RoutingDecision`. A future routing layer will combine `CandidateRisk`, `QualityGrade`, workspace policy, and user calibration to produce decisions: `approved` / `quarantine` / `rejected` / `delete_eligible`.

Heuristic warnings (such as low-pass suspicion, clipping suspicion, or transcode suspicion) must not cause destructive file operations. They are informational until MusicLab calibration establishes strong thresholds. Objective failures can inform future routing but do not execute delete in this commit.

The separation must remain: providers → scoring (pre-download) → download/transfer → quality (post-download) → routing (combined decision). `CandidateScoringService` does not import `QualityService`. `QualityService` does not import `CandidateScoringService`.

## Routing Decision Foundation

Post-download routing decision is a separate core domain from both pre-download scoring and post-download quality analysis. This commit introduces the contracts and fake simulation layer for future file routing actions.

Flux owns these routing models:

- `RoutingOutcome` — planned routing decision: `approved`, `quarantine`, `rejected`, `delete_eligible`, `review`, `unknown`.
- `RoutingActionType` — planned action type: `plan_only`, `move_to_approved`, `move_to_quarantine`, `move_to_rejected`, `mark_delete_eligible`, `none`. All actions are planned-only at this stage; no real file movement occurs.
- `RoutingReason` — individual reason for a routing decision with code, message, severity, source (`quality_grade`, `quality_finding`, `policy_rule`), and safe metadata.
- `RoutingPolicy` — versioned policy with name, version, description, `allow_delete_eligible` (default false), `heuristic_warnings_route_to_review_or_quarantine` (default true), `objective_failures_route_to_rejected` (default true), and safe metadata.
- `RoutingDecision` — structured decision for a single item: item_id, outcome, action_type, reasons, warnings, errors, confidence, policy, and safe metadata.
- `RoutingPlan` — aggregate plan with plan_id, decisions, planned_changes, warnings, errors, and safe metadata.

`RoutingDecisionService` provides service-level routing evaluation and planning. It accepts `QualityResult` objects and returns `RoutingDecision` or `FluxResult` with `PlannedChange` objects. It does not access the network, move files, delete files, create files, or know about `slskd`.

Routing decision logic:

- `QualityGrade` excellent → `approved`, action `plan_only`.
- `QualityGrade` medium with no findings → `approved`, action `plan_only`.
- `QualityGrade` medium with heuristic warnings → `review` (per policy), action `plan_only`.
- `QualityGrade` medium with objective failure → `review`, action `plan_only`.
- `QualityGrade` bad with objective failure → `rejected` (per policy), or `delete_eligible` only if `allow_delete_eligible` is true in the policy. Action is always `plan_only`.
- `QualityGrade` bad with only heuristic warnings → `quarantine`, action `plan_only`. Heuristic warnings never generate `delete_eligible`.
- `QualityGrade` unknown → `review`, action `plan_only`.

Heuristic warnings must never cause `delete_eligible` outcome. Objective failures can inform `rejected` or `delete_eligible` future actions, but only through explicit policy configuration. All routing decisions are planned-only; no real file movement, deletion, or quarantine occurs in this commit.

The separation must remain: providers → scoring (pre-download) → download/transfer → quality (post-download) → routing (planned decision). `CandidateScoringService` does not import `RoutingDecisionService`. `QualityService` does not execute `RoutingDecisionService` automatically. `RoutingDecisionService` consumes `QualityResult` but does not alter it.

## Staging Plan Foundation

Post-download staging plan is a separate core domain from routing decision. `RoutingDecision` decides the conceptual destination; `StagingPlan` prepares the planned filesystem change. A future executor will apply real changes only with explicit `--apply` mode and safety checks.

Flux owns these staging models:

- `StagingArea` — planned filesystem destination: `incoming`, `approved`, `quarantine`, `rejected`, `delete_eligible`, `review`, `unknown`.
- `StagingActionType` — planned action type: `plan_only`, `move`, `copy`, `mark_delete_eligible`, `none`. All actions are planned-only at this stage; no real file movement, copy, or deletion occurs.
- `StagingItem` — structured staging entry for a single item: item_id, routing_outcome, optional source_relative_path, target_area, optional target_relative_path, action_type, warnings, errors, and safe metadata.
- `StagingPlan` — aggregate plan with plan_id, items, planned_changes, warnings, errors, and safe metadata.
- `StagingPolicy` — versioned policy with name, version, description, `allow_delete_eligible` (default false), `allow_real_moves` (default false), `quarantine_heuristic_warnings` (default true), and safe metadata.

`StagingPlanService` provides service-level staging evaluation and planning. It accepts `RoutingPlan` or `RoutingDecision` objects and returns `StagingItem` or `FluxResult` with `PlannedChange` objects. It does not access the network, move files, delete files, create files, copy files, or know about `slskd`.

Staging plan logic:

- `RoutingOutcome` approved → `StagingArea` approved, action `plan_only`.
- `RoutingOutcome` quarantine → `StagingArea` quarantine, action `plan_only`.
- `RoutingOutcome` rejected → `StagingArea` rejected, action `plan_only`.
- `RoutingOutcome` delete_eligible → `StagingArea` delete_eligible only if policy allows; otherwise converts to rejected with a clear warning. Action is always `plan_only`.
- `RoutingOutcome` review → `StagingArea` review by default, or quarantine if policy disables review. Action is always `plan_only`.
- `RoutingOutcome` unknown → `StagingArea` unknown, action `none`, with warning.

`delete_eligible` is not deletion. It means the item is eligible for future deletion pending explicit policy approval and apply-mode execution. No real delete, move, copy, or quarantine occurs in this commit.

Source and target relative paths are validated for safety: absolute paths and path traversal markers are blocked. Real filesystem validation will come in a future executor layer.

The separation must remain: providers → scoring (pre-download) → download/transfer → quality (post-download) → routing (planned decision) → staging (planned filesystem change). `RoutingDecisionService` does not execute `StagingPlanService` automatically. `StagingPlanService` consumes `RoutingPlan`/`RoutingDecision` but does not alter quality, scoring, or routing results.

## Quality Analysis And Routing (Future)

Post-download quality analysis and routing will continue to evolve as separate layers from pre-download scoring:

- `QualityResult` — structured result from audio file inspection (ffmpeg, transcode analysis, spectrogram heuristics, decode health, clipping, low-pass detection).
- `QualityFinding` — individual observations such as spectral cutoffs, codec artifacts, or declared-vs-actual mismatches.
- `QualityGrade` — summary classification: `excellent` / `medium` / `bad`. This is NOT `CandidateRisk`.
- `RoutingDecision` — a separate service layer that combines `CandidateRisk`, `QualityGrade`, workspace policy, and user calibration to produce decisions: `approved` / `quarantine` / `rejected` / `delete_eligible`.
- `StagingPlan` — a separate service layer that translates `RoutingDecision` outcomes into planned filesystem changes: target area, relative path, and planned action.
- `calibration_profile` — MusicLab sessions that tune scoring weights, quality heuristics, and routing thresholds against controlled fixtures before any real provider or download behavior is active.
- `StagingExecutor` — a future layer that applies real filesystem changes (move, copy, mark) only with explicit `--apply` mode and safety checks.

Pre-download scoring (`CandidateScore`, `CandidateRisk`) must not grow into audio quality, routing, or staging decisions. The separation must remain: providers → scoring (pre-download) → download/transfer → quality (post-download) → routing (planned decision) → staging (planned filesystem change) → executor (real execution).

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

`TransferPlanningService` owns transfer/queue planning. It accepts `DownloadPlan` from the download planning domain, converts `DownloadItem` objects into `TransferItem` and `QueueItem` objects, and returns a `FluxResult` with `PlannedChange` objects. It does not download files, create files, access the network, call providers, or know about `slskd`. It does not decide quality, routing, quarantine, or deletion. Queue plans are inherently dry-run; real execution will come in a separate future layer with an isolated `TransferProvider` adapter.

`ProviderService` owns provider inspection, health checks, and capability validation. It accepts any `BaseProvider`, calls `health()` and `capabilities()`, and returns `FluxResult` with structured steps, warnings, errors, and logical artifacts. It does not access the network, download files, create files, or know about `slskd`.

`QualityService` owns post-download quality evaluation and summarization. It accepts structured fake data (item_id, optional relative_path, grade, findings, profile) and returns `FluxResult` with steps, warnings, errors, and logical quality artifacts. It does not download files, create files, access the network, read audio, use ffmpeg, perform transcode analysis, call providers, or know about `slskd`. It does not decide routing, quarantine, rejection, or deletion. Quality analysis is inherently contracts-only at this stage; real audio inspection will come in a separate future layer.

`RoutingDecisionService` owns post-download routing decision planning. It accepts `QualityResult` objects and optional `RoutingPolicy`, returns `RoutingDecision` or `FluxResult` with `PlannedChange` objects. It does not download files, create files, access the network, move files, delete files, call providers, or know about `slskd`. It does not execute real routing actions; all decisions are planned-only. Real execution will come in a separate future layer with explicit apply mode and safety checks.

`StagingPlanService` owns post-download staging plan preparation. It accepts `RoutingPlan` or `RoutingDecision` objects and optional `StagingPolicy`, returns `StagingItem` or `FluxResult` with `PlannedChange` objects. It does not download files, create files, access the network, move files, delete files, copy files, call providers, or know about `slskd`. It does not execute real staging actions; all changes are planned-only. Real execution will come in a separate future executor layer with explicit apply mode and safety checks.

## File Operation Executor Foundation

File operation execution is a separate core domain from staging plan. `StagingPlan` describes the intention; `FileOperationPlan` describes the concrete filesystem operations that can be performed. `SafeFileOperationService` applies operations only with explicit policy configuration and `--apply` mode.

Flux owns these file operation models:

- `FileOperationType` — operation type: `copy`, `move`, `mark`, `mkdir`, `none`.
- `FileOperationState` — operation state: `planned`, `skipped`, `applied`, `failed`, `blocked`.
- `FileOperation` — single operation with operation_id, operation_type, optional source_relative_path, optional target_relative_path, reason, and safe metadata.
- `FileOperationPlan` — aggregate plan with plan_id, operations, warnings, errors, and safe metadata.
- `FileOperationResult` — execution result for a single operation: operation_id, operation_type, state, optional source/target paths, message, warnings, errors, and safe metadata.
- `FileExecutionPolicy` — versioned policy with name, version, description, `allow_move` (default false), `allow_copy` (default true), `allow_mkdir` (default true), `allow_delete` (default false), `allow_overwrite` (default false), and safe metadata.

`SafeFileOperationService` provides service-level file operation planning and execution. It accepts `StagingPlan` or `FileOperationPlan` objects and returns `FluxResult` with `PlannedChange` and `AppliedChange` objects. It does not access the network, delete files, or know about `slskd`.

File operation execution logic:

- Dry-run (default): no files are created, moved, copied, or deleted. Returns `PlannedChange` with state `planned`, `skipped`, or `blocked`.
- Apply mode (explicit `--apply`): operations are executed within the workspace boundary only. Mkdir, copy, and move are allowed per policy. Overwrite is blocked by default. Source must exist for copy/move. Symlink escape is blocked. Absolute paths and path traversal are blocked. Protected roots are blocked. Returns `AppliedChange` for successfully applied operations.
- Delete is not implemented in this commit. `mark` operations only flag items as delete-eligible without touching the filesystem.

`StagingPlan` to `FileOperationPlan` conversion:

- `StagingActionType.move` → `FileOperationType.move`, applied only if `policy.allow_move=true`.
- `StagingActionType.copy` → `FileOperationType.copy`, applied only if `policy.allow_copy=true`.
- `StagingActionType.mark_delete_eligible` → `FileOperationType.mark`, no real delete.
- `StagingActionType.plan_only` / `none` → `FileOperationType.none` or skipped.

The separation must remain: staging (planned intention) → fileops (concrete operations) → executor (real execution). `StagingPlanService` does not execute `SafeFileOperationService` automatically. `SafeFileOperationService` consumes `StagingPlan`/`FileOperationPlan` but does not alter staging or routing results.

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

Transfer planning CLI commands are adapters over `TransferPlanningService`: `transfer plan fake track` and `transfer plan fake album` build `SearchQuery` objects, use the fake provider, optionally score the candidate, build a `DownloadRequest`, call `DownloadPlanningService` to get a `DownloadPlan`, then call `TransferPlanningService` to get a `QueuePlan`, and render the returned `FluxResult`. The CLI does not implement planning logic, transfer execution, or provider-specific behavior. All planning commands are dry-run by nature and have no `--apply` mode.

Quality CLI commands are adapters over `QualityService`: `quality fake excellent`, `quality fake medium`, `quality fake bad`, and `quality fake unknown` simulate post-download quality results with fake data, call `QualityService`, render the returned `FluxResult`, and choose the process exit code. The CLI does not implement quality analysis logic, read audio files, or perform real inspection. All quality commands are contracts-only and have no `--apply` mode.

Routing CLI commands are adapters over `RoutingDecisionService`: `routing fake excellent`, `routing fake medium`, `routing fake bad-objective`, `routing fake bad-heuristic`, and `routing fake unknown` simulate post-download routing decisions from fake quality results, call `RoutingDecisionService`, render the returned `FluxResult`, and choose the process exit code. The CLI does not implement routing logic, move files, delete files, or perform real routing. All routing commands are planned-only and have no `--apply` mode.

Staging CLI commands are adapters over `StagingPlanService`: `staging fake approved`, `staging fake quarantine`, `staging fake rejected`, `staging fake delete-eligible`, and `staging fake review` simulate post-download staging plans from fake routing decisions, call `StagingPlanService`, render the returned `FluxResult`, and choose the process exit code. The CLI does not implement staging logic, move files, delete files, copy files, or perform real staging. All staging commands are planned-only and have no `--apply` mode.

Fileops CLI commands are adapters over `SafeFileOperationService`: `fileops demo --workspace PATH --dry-run` plans safe filesystem operations without executing them, while `fileops demo --workspace PATH --apply` executes mkdir/copy/move operations within the workspace boundary per policy. The CLI does not implement file operation logic, delete files, or perform operations outside the workspace. Default behavior is dry-run; `--apply` must be explicit.

## Future Controllers

Future Android, UI, local API, or controller layers should call the same services directly. They should use structured results and future manifest contracts instead of duplicating workflow logic or depending on CLI text.
