# Safety

Flux must default to conservative behavior.

## Execution Modes

Write-capable workflows should support dry-run and apply modes. Dry-run should be the default where an operation could move, delete, download, import, or mutate files. Apply should be explicit and gated by safety checks.

Workspace initialization follows this rule. `noqlen-flux workspace init PATH --dry-run` reports planned directory creation without writing to disk. `noqlen-flux workspace init PATH --apply` is required before Flux creates missing workspace directories.

Report writing follows the same rule. `noqlen-flux report demo --workspace PATH --format json --dry-run` previews the report artifact without writing, and `--apply` is required before a file is created.

MusicLab follows the same rule. `musiclab init`, `musiclab session create`, and `musiclab fixture create` default to planning only; `--apply` must be explicit before any directory or fake fixture file is created.

## Workspace Root

The workspace root is the Flux-controlled boundary for staging and generated state. It is normalized with `pathlib` before use. Future workflows must operate inside this root unless a separate safety boundary is explicitly designed.

The initial workspace layout contains these automatic directories:

- `incoming`
- `approved`
- `quarantine`
- `rejected`
- `reports`
- `manifests`
- `cache`
- `tmp`

## Staging

Downloads should stage into controlled Flux-owned directories before any handoff. Automated staging must avoid writing directly into a real music library.

`staging apply` is dry-run by default. `--apply` is required before any filesystem change, and the service-level apply path requires explicit routing apply and staging execution policies. The apply workflow uses `SafeFileOperationService` and stays inside the Flux workspace.

Staging destinations are conservative:

- `approved` goes to `workspace/approved/import-ready`.
- `quarantine` goes to `workspace/quarantine` only when policy allows it.
- `rejected` goes to `workspace/rejected` and never deletes.
- `review` remains manual under `workspace/review/manual` and does not automatically copy or move.
- `delete_eligible` is a marker only; real delete and auto-delete do not exist.

Every staging apply/dry-run returns a structured safety report with policy names, planned/applied/skipped/blocked/failed counts, warnings, errors, and explicit safety checks. Reports use structured Flux metadata and must not include secrets, raw provider payloads, lyrics, raw fingerprints, or real library paths.

## Quarantine And Rejected

Suspicious, incomplete, unsupported, or policy-failing items should be isolated into quarantine or rejected areas rather than imported. Quarantine is for reviewable uncertainty. Rejected is for objective failures that remain excluded from handoff.

## Cleanup

Cleanup planning does not delete anything. `CleanupPlanningService` evaluates `CleanupCandidate` objects against a `CleanupPolicy` and produces a `CleanupPlan` with `PlannedChange` entries. No file is deleted, moved, copied, or created.

`delete_eligible` is not deletion. It means the item is eligible for future deletion pending explicit policy approval and apply-mode execution.

`plan_delete` is only a planned decision. It does not execute any filesystem operation. It is expressed as a `PlannedChange`, never an `AppliedChange`.

`auto_delete_enabled` exists only as a policy field and never executes any deletion. Auto-delete does not exist in this commit. Future auto-delete would require a separate executor layer, explicit policy, reports, limits, workspace safety, and explicit apply.

Heuristic findings must never cause automatic deletion. Heuristic-only candidates are routed to `review`, never `plan_delete`, regardless of policy configuration.

Objective failures can inform cleanup planning but still as a plan only. `mark_delete_eligible` is a planned decision, not an execution.

Absolute paths and path traversal markers are blocked in `CleanupCandidate.relative_path`. No candidate can reference a path outside the workspace boundary.

Automated cleanup tests must use fake candidates, temporary directories, or controlled fixtures only. They must not use real music files, network access, or personal filesystem paths.

## Path Safety

Future file operations must enforce path containment, symlink protection, and path traversal protection. Resolved paths must stay inside the intended Flux-controlled root before moves, writes, cleanup, or handoff.

Path traversal attempts that resolve outside the workspace are blocked. Symlinks that resolve outside the workspace are also blocked before Flux plans or applies directory operations.

Protected roots can be configured for service calls. Any target inside a protected root is rejected, and a workspace root that would contain a protected root is rejected. CLI environment support is intentionally minimal and only uses the `NOQLEN_FLUX_` prefix.

## MusicLab

MusicLab is confined to `workspace/musiclab`. It must never touch a real music library, personal music folders, download folders, device storage, or external provider state.

MusicLab tests and services must not use real network calls, real downloads, `slskd`, ffmpeg, transcode, quality inspection, cleanup, auto-delete, or handoff. Current fixtures are controlled fake JSON/text artifacts only.

MusicLab session and fixture identifiers are restricted to safe basename-like values. Path traversal such as `../session`, absolute paths, separators, and unsafe characters are rejected before planning or applying changes.

MusicLab applies the same workspace containment, symlink escape blocking, and protected-root checks as other Flux services. A symlink that would move MusicLab state outside the workspace is rejected before directory creation or fixture writing.

### MusicLab Scoring Calibration

Scoring calibration fixtures must not use real music library paths. All candidates are fake and constructed in memory.

Scoring calibration is non-destructive. It does not write files, alter scoring thresholds, adjust profiles, or decide routing/download/staging/delete.

Suspicious terms produce risk and warnings, not quality, routing, or delete decisions. `CandidateRisk` is a pre-download signal, not a `QualityGrade`.

False-positive tests are required for suspicious-term matching. Terms like "alive", "olive", "premix", and "delivery" must not trigger false suspicious-term penalties when they appear as exact words in candidate metadata.

### MusicLab Score Baselines

Score baselines provide versioned, tolerance-aware regression detection for scoring. Safety guarantees:

- **No threshold alteration**: Baselines detect regression and suggest review; they never auto-adjust weights or thresholds.
- **No training**: Calibration reports are evidence for human review, not automated model updates.
- **No real providers**: All baseline evaluation uses fake candidates in memory. No network, no slskd, no real providers.
- **No file writes**: Score baseline reports are in-memory only. No filesystem access outside workspace.
- **No destructive actions**: Score baselines evaluate `CandidateScore` only. They do not route, stage, delete, or handoff.
- **No secrets in reports**: Reports use safe serialization with redacted metadata.
- **CandidateRisk vs QualityGrade separation strictly enforced**: Score pre-download is separate from quality post-download.
- **Forbidden code detection**: Baselines detect unexpected penalties (e.g., source-profile-suspicious, lowpass-quality-penalty) and flag them as forbidden.

Score baseline packs cover: good candidates, bad candidates, false-positive guards, provider anomalies, quality-aware preview, album integrity, and source profiles.

### MusicLab Quality Calibration

Quality calibration fixtures must not use real music library paths. All findings are fake and constructed in memory.

Quality calibration is non-destructive. It does not write files, alter quality thresholds, adjust profiles, or decide routing/download/staging/delete.

Heuristic warnings such as low-pass, clipping, loudness, transcode suspicion must not delete or route automatically. They remain informational until MusicLab calibration establishes strong thresholds.

Objective failures can inform future routing but still as a plan only. They do not execute delete, quarantine, or rejection in this commit.

Fake quality cases must not contain raw fingerprints, lyrics, provider payloads, or personal paths.

Quality calibration does not call `RoutingDecisionService`, `StagingPlanService`, `CleanupPlanningService`, or `SafeFileOperationService`. It does not access the network, use ffmpeg, read audio, or depend on any real provider.

`CandidateRisk` remains separate from `QualityGrade`. `QualityGrade` remains separate from `RoutingDecision`.

## Provider Health And Capabilities

Health and status checks must not perform downloads, create files, or access the network on their own. `ProviderService` calls only the generic `health()` and `capabilities()` contracts on providers and returns structured results.

Provider status must not expose secrets, tokens, credentials, private paths, or raw backend payloads. `ProviderHealth.metadata` is safe metadata only; sensitive keys are redacted during serialization.

Automated tests must use fake providers. Real network health checks belong only in provider adapters and must be separately tested and sandboxed in a future layer.

`ProviderHealth` and `ProviderStatus` are Flux-owned models. A future `slskd` adapter must translate its backend status into these models without leaking internal slskd structures. A future `NativeSoulseekProvider` must implement the same contract.

## Slskd Adapter

The `SlskdProvider` adapter under `providers/slskd.py` is an external adapter, not Flux core.

- Slskd adapter tests must use fake payloads and `FakeSlskdClient` only. No real slskd network access is permitted in automated tests.
- slskd search network access is disabled by default (`allow_network=false`). Real search requires explicit opt-in.
- Bounded polling is required: `max_poll_attempts` limits the number of state checks. No infinite loops are permitted.
- `SlskdProviderConfig.api_key` is redacted in `to_dict()` and `__repr__()`. It must never appear in logs, artifacts, or test output.
- API keys must be provided via environment variable (`--api-key-env`), not as literal CLI arguments.
- `SlskdPayloadMapper` must not expose raw provider payloads in `SearchCandidate`, `CandidateFile`, or `SearchProviderResult` metadata.
- No raw provider payload, secrets, private paths, lyrics, or fingerprints should leak through the adapter.
- Core services must not import `providers.slskd`. They depend on generic contracts only.
- Without an injected client and without `allow_network`, `SlskdProvider` returns `UNAVAILABLE` with "network access disabled".
- `SlskdHttpClient` uses only `urllib.request` (standard library). It supports health checks and search operations. Search endpoint paths must be confirmed against the actual slskd version before production use.
- Client errors during polling, start, or response retrieval produce controlled `SearchProviderResult.errors`, not raw exceptions.
- Network errors from `SlskdHttpClient` do not leak tokens, headers, or raw response content.
- Search never downloads files, creates files, or writes to the filesystem.
- Download, queue, and transfer are not implemented in this adapter.

### Slskd Search CLI

The `search slskd` CLI commands provide a preview of search results without downloading or writing files.

- slskd search CLI is offline/no-network by default.
- Real network search requires explicit `--allow-network`.
- API key should come from environment variable via `--api-key-env`, never as a literal argument.
- Search preview never downloads files.
- Search preview never writes files or touches the filesystem.
- Tests must use offline/fake clients; no real network access in automated tests.
- The CLI is the only layer that instantiates `SlskdProvider`; core services remain provider-agnostic.
- Output must not contain raw provider payloads, API keys, tokens, headers, or personal absolute paths.

### Slskd Download Planning CLI

The `download plan slskd` CLI commands transform slskd search results into download plans without executing any transfer.

- slskd download planning CLI is offline/no-network by default.
- Real network search requires explicit `--allow-network`.
- Download planning never downloads files.
- Download planning never writes files.
- API key should come from environment variable via `--api-key-env`, never as a literal argument.
- Tests must use offline/fake clients; no real network access in automated tests.
- `DownloadPlanningService` does not know about slskd; it operates on Flux `SearchCandidate` and `DownloadRequest` models only.
- Output must not contain raw provider payloads, API keys, tokens, headers, or personal absolute paths.

### Slskd Transfer Planning CLI

The `transfer plan slskd` CLI commands transform slskd search results into download plans and then into queue/transfer plans without executing any transfer.

- slskd transfer planning CLI is offline/no-network by default.
- Real network search requires explicit `--allow-network`.
- Transfer planning never downloads files.
- Transfer planning never enqueues real provider tasks.
- Transfer planning never writes files.
- Transfer planning never initiates real transfers.
- API key should come from environment variable via `--api-key-env`, never as a literal argument.
- Tests must use offline/fake clients; no real network access in automated tests.
- `DownloadPlanningService` does not know about slskd; it operates on Flux models only.
- `TransferPlanningService` does not know about slskd; it operates on Flux `DownloadPlan` models only.
- Output must not contain raw provider payloads, API keys, tokens, headers, or personal absolute paths.

## Transfer Status Polling

Transfer status polling provides opt-in status checks for queued transfers. Default mode is offline (fake client only). Real network polling requires explicit `--allow-network`.

Polling safety guarantees:
- Default offline mode prevents accidental network access.
- Real network access requires `--allow-network`, `--url`, `--api-key-env`, and `--transfer-id`.
- API key must come from environment variable (`--api-key-env`), never as a literal argument.
- API keys are redacted in all outputs (to_dict, repr, error messages).
- Raw provider payloads never leak into Flux `TransferStatus` models.
- Polling is bounded (single call per invocation). No infinite polling loops.
- Status responses do not expose secrets, tokens, credentials, private paths, or backend internals.
- `TransferStatus` objects must not contain raw provider payloads or sensitive data.
- Tests use fake clients only; no real network access in automated tests.
- Transfer status is not quality. It describes transfer lifecycle state only.

## Download Artifact Registration

Download artifact registration creates safe, model-based records of completed downloads. It does not read files, compute checksums, or analyze audio.

Registration safety guarantees:
- `DownloadArtifactRegistration` is a Flux model with safe serialization. Sensitive metadata keys are redacted.
- Path safety: blocks absolute paths, path traversal (`..`), dot-only segments (`.`), and unsafe markers.
- No file reading: registration never opens or reads download files.
- No checksum computation: no SHA, MD5, or other hash computation.
- No audio analysis: never calls ffmpeg, transcode detection, or audio inspection.
- No Forge integration: does not call Forge, create manifests, or perform import.
- No network access: `ArtifactRegistrationService` does not import or call any provider.
- Dry-run is the default; apply mode generates logical `Artifact` entries without touching the filesystem.
- Registration metadata must not contain secrets, tokens, credentials, full lyrics, audio fingerprints, or raw provider payloads.

## Download Workspace Safety

Download workspace safety ensures download paths remain confined within the Flux workspace boundary and do not escape to external directories, protected roots, or real music libraries.

Workspace safety guarantees:
- Downloads must stay inside the Flux workspace root.
- Absolute paths are blocked (e.g., `/etc/passwd`, `/home/user/Music`).
- Path traversal markers are blocked (`~`, `$`, `{`, `}`, `..`).
- Dot-only segments are blocked (`./`).
- Symlinks that resolve outside the workspace are blocked.
- Protected roots are blocked. Paths cannot be inside a protected root.
- Real music library paths are blocked (absolute paths to music directories).
- Dry-run is the default; directory creation requires explicit apply.
- No network access: `DownloadWorkspaceService` does not import or call any provider.
- No music library interaction: download output is confined to the workspace.
- Tests use `tmp_path` only; no real filesystem or personal paths.
- `DownloadWorkspaceService` does not perform quality analysis, staging, cleanup, or handoff.

Automated search tests must use fake providers or controlled fixtures. Real network access, real `slskd`, native Soulseek sessions, credentials, live provider APIs, and real downloads are prohibited in automated search tests.

Search is discovery only. It must not download files, create files, write reports, mutate workspaces, stage transfers, import music, or touch any real music library.

Provider-specific payloads must be translated into Flux-owned models before they reach services. `slskd` must not be imported by central services and must remain isolated in a future provider adapter module.

Locked files must be modeled and visible on `CandidateFile` before any future download workflow decides how to handle them.

## Candidate Scoring

Pre-download scoring is advisory only. It must not delete, move, reject, approve, quarantine, import, clean up, or route files by itself.

Scoring must not download files, create files, call real providers, inspect audio, measure real sound quality, use `slskd`, or touch any real music library. It scores only Flux-owned `SearchCandidate` data already returned by a provider contract.

Heuristics such as exact textual matches, locked file visibility, declared bitrate, declared extension, and suspicious filename or folder terms produce risk signals, warnings, reasons, and penalties. They are not final quality decisions.

Automated scoring tests must use fake providers, fake candidates, or controlled fixtures only. They must not use network access, credentials, real downloads, real provider sessions, or personal filesystem paths.

## Download Planning

Download planning is inherently a dry-run operation. It does not download files, create files, access the network, call providers, or interact with any real provider including `slskd`.

Plans are expressed as `DownloadPlan` objects with `PlannedChange` entries, not `AppliedChange`. No file system mutation occurs during planning. Real execution will come in a separate future layer.

Locked files must block items or generate warnings according to the `allow_locked` constraint. When `allow_locked` is false and all files are locked, the plan is blocked. When `allow_locked` is true, locked files are included with a clear warning.

Scoring is not quality. A `require_score_min` constraint blocks plans when the candidate score falls below the threshold, but this is a pre-download risk signal, not a post-download quality decision.

Planning is not routing. `DownloadPlanningService` does not decide approval, rejection, quarantine, or deletion. It only determines whether a download can be planned given the candidate data and constraints.

No test uses real network access or a real music library. All tests use fake providers, fake candidates, temporary directories, or controlled fixtures.

## Transfer And Queue Planning

Transfer planning is inherently a dry-run operation. It does not download files, create files, access the network, call providers, or interact with any real provider including `slskd`.

Queue plans are expressed as `QueuePlan` objects with `PlannedChange` entries, not `AppliedChange`. No file system mutation occurs during planning. Real execution will come in a separate future layer with an isolated `TransferProvider` adapter.

`TransferPlanningService` does not decide approval, rejection, quarantine, or deletion. It only determines whether a transfer can be planned given the download plan data and item states.

Locked items generate visible warnings in the queue plan. The service respects locked file information from the download plan without making quality or routing decisions.

`TransferStatus` objects must not contain secrets, credentials, or personal absolute paths. Provider-specific payloads must not leak into the core transfer domain.

The `TransferProvider` contract is generic and provider-neutral. A future `SlskdProvider` or `NativeSoulseekProvider` must implement the same contract without requiring core changes. Provider-specific payloads must be translated into Flux-owned models before they reach services.

No test uses real network access or a real music library. All tests use fake providers, fake candidates, temporary directories, or controlled fixtures.

## Quality Analysis

Quality analysis now supports an initial real audio probing layer via opt-in fake or ffprobe backends.

`AudioProbeService` and `FakeProbeBackend`/`FfmpegProbeBackend` provide:
- Fake backend (default for dry-run and tests): simulates audio properties without real files.
- ffprobe backend (opt-in): calls `ffprobe` via `subprocess.run()` with timeout. ffprobe must be installed separately.
- All probes are confined to the workspace root. Path traversal, symlink escape, and protected roots are blocked.
- Dry-run is the default. Apply mode requires explicit `--apply`.

`QualityService.probe_to_quality_result()` bridges probe findings to quality findings:
- `objective_failure` → `QualityFindingKind.OBJECTIVE_FAILURE`
- `heuristic_warning` → `QualityFindingKind.HEURISTIC_WARNING`
- Probe findings are never reclassified across the boundary.
- The bridge does not execute routing, staging, cleanup, or handoff.

`QualityService.inspect_file()` validates path safety, runs the probe, and bridges to `QualityResult`. Dry-run is the default.

Tests use mock `subprocess.run()`; no real ffprobe/ffmpeg is required. All audio probe tests use fake backends or mocked subprocess calls.
- Unnecessary personal absolute paths.

`QualityProfile` is versioned so MusicLab can calibrate thresholds before any real provider or audio analysis is active. The default profile declares `stage: post-download` and `status: contracts-only`.

## Spectral Analysis Safety

`SpectralAnalysisService` provides controlled spectral analysis with full safety guarantees:

- **Backend abstraction**: `SpectralBackend` (ABC) with `FakeSpectralBackend`. All real analysis backends are opt-in.
- **Workspace containment**: All spectral analysis operations confined to workspace root. Path traversal and symlink escape are blocked.
- **Dry-run default**: Apply mode requires explicit invocation. No file writes in dry-run.
- **No real audio in tests**: All tests use `FakeSpectralBackend`. No real audio files, no ffmpeg, no network.
- **Subprocess safety**: If future real backends use subprocess, they must have short timeouts and be mockable.
- **No decision execution**: Spectral analysis produces evidence only. It does not route, stage, quarantine, delete, or handoff automatically.

Critical signal classifications (enforced by `SpectralPolicy`):
- Cutoff/lowpass → `heuristic_warning` (never `objective_failure`)
- Fake bit depth/sample rate → `heuristic_warning`
- Upsampled/downsampled → `heuristic_warning`
- Transcode signature → `heuristic_warning`
- Container/codec mismatch → `heuristic_warning`
- Clipping/loudness/noise floor → `review_signal`
- `never_objective_on_heuristic: true` — heuristic signals cannot become objective failures

## Transcode Detection Safety

`TranscodeDetection` produces structured detection results from spectral profiles:

- `is_lowpass_cutoff_isolated()` — ensures cutoff/lowpass alone is never flagged as transcode.
- `lowpass_cutoff_guard()` — returns guard data documenting what must and must not happen for isolated cutoff/lowpass.
- Fake FLAC with container mismatch → review candidate, never delete.
- Qobuz-like 9.4 kHz cutoff + decode OK → NOT probable transcode.
- Lowpass only → NOT probable transcode.
- Source profile alone does not decide transcode detection.
- Detection results are evidence only — no routing, staging, or destructive action is automated.

## Advanced Quality Confidence Scoring Safety

`QualityService.score_confidence()` produces structured confidence output without executing actions:

- Confidence scoring is advisory only — it does not trigger routing, staging, or delete.
- `advised_review` and `advised_block` are guidance flags, not decisions.
- `QualityResult` now includes `evidence_summary` and `review_signals` for audit trail.
- `QualityResult` is separated from `RoutingDecision` and `StagingPlan`.
- No automatic quality-to-action pipeline exists in this commit.

## Routing Decisions

Routing decisions are currently planned-only. `RoutingDecisionService` does not move, copy, delete, quarantine, or reject any files. It accepts `QualityResult` objects and returns `RoutingDecision` or `FluxResult` with `PlannedChange` entries, never `AppliedChange`.

`RoutingOutcome` values (`approved`, `quarantine`, `rejected`, `delete_eligible`, `review`, `unknown`) represent planned decisions, not executed actions. `delete_eligible` does not mean deletion has occurred; it means the item is eligible for future deletion pending explicit policy approval and apply-mode execution.

Future real routing execution must require explicit `--apply` mode with safety checks. It must not touch a real music library, personal music folders, or download folders. All file operations must be confined to the Flux workspace root with path containment and symlink protection.

`RoutingDecision` is separate from both `CandidateRisk` and `QualityGrade`. `CandidateRisk` is a pre-download risk signal. `QualityGrade` is a post-download quality classification. `RoutingDecision` is a planned routing action that combines quality signals with policy configuration. The three must remain separate: scoring does not import routing, quality does not execute routing automatically, and routing does not alter quality results.

Heuristic warnings must never cause `delete_eligible` outcome. They may route to `review` or `quarantine` depending on policy configuration. Objective failures can inform `rejected` or `delete_eligible` outcomes, but only through explicit `RoutingPolicy` configuration with `allow_delete_eligible` set to true.

Automated routing tests must use fake quality data, temporary directories, or controlled fixtures only. They must not use real audio files, network access, file movement tools, or personal filesystem paths.

Routing contracts must not expose:

- Complete lyrics.
- Raw audio fingerprints.
- Raw provider payloads.
- Secrets, tokens, or credentials.
- Unnecessary personal absolute paths.

`RoutingPolicy` is versioned so MusicLab can calibrate routing thresholds before any real provider or file execution is active. The default policy declares `stage: post-download`, `status: contracts-only`, and `allow_delete_eligible: false`.

## Staging Plans

Staging plans are currently planned-only. `StagingPlanService` does not move, copy, delete, quarantine, or reject any files. It accepts `RoutingPlan` or `RoutingDecision` objects and returns `StagingItem` or `FluxResult` with `PlannedChange` entries, never `AppliedChange`.

`StagingArea` values (`incoming`, `approved`, `quarantine`, `rejected`, `delete_eligible`, `review`, `unknown`) represent planned destinations, not executed actions. `delete_eligible` does not mean deletion has occurred; it means the item is eligible for future deletion pending explicit policy approval and apply-mode execution.

`StagingActionType` values (`plan_only`, `move`, `copy`, `mark_delete_eligible`, `none`) are all treated as `plan_only` in `StagingPlanService`. No real move, copy, or delete operation is performed by the planning service.

## Staging Execution

Staging execution connects `StagingPlan` with `SafeFileOperationService` to allow controlled execution of staging plans within the workspace. Dry-run is the default: no directories are created, no files are created, copied, moved, or deleted. Apply mode requires an explicit `--apply` flag.

Delete does not exist in this commit. `StagingExecutionPolicy.allow_delete` is always false and has no effect. `mark_delete_eligible` generates mark operations only, never delete.

Overwrite is blocked by default. When `allow_overwrite=false` (the default), any operation targeting an existing path is blocked with a warning. Move is blocked by default unless `allow_move=true` is set in an explicit policy. Copy is allowed by default but still subject to workspace boundary and path safety checks.

All operations must stay within the workspace root. Path traversal (`..`), absolute paths, symlink escape, and protected roots are blocked before any operation is planned or applied. Source paths that are symlinks resolving outside the workspace are rejected. Target paths that would escape the workspace via symlink are rejected.

`StagingExecutionService` returns `PlannedChange` objects in dry-run mode, never `AppliedChange`. Apply mode returns `AppliedChange` only for operations that were actually executed.

`StagingExecutionPolicy` controls staging execution behavior:
- `allow_copy` (default true) — copy operations are allowed within the workspace.
- `allow_move` (default false) — move operations are blocked unless explicitly allowed.
- `allow_delete` (default false) — delete does not exist; this flag has no effect.
- `allow_overwrite` (default false) — overwrite is blocked by default.
- `create_workspace_dirs` (default true) — staging directories are created automatically if needed.

Automated staging execution tests must use temporary directories, fake fixtures, or controlled workspace layouts only. They must not use real music files, network access, or personal filesystem paths.

## File Operations

File operations are governed by `SafeFileOperationService` and `FileExecutionPolicy`. Dry-run is the default: no files are created, moved, copied, or deleted. Apply mode requires an explicit `--apply` flag.

Delete does not exist in this commit. `FileOperationType` has no delete variant. `mark` operations only flag items as delete-eligible without touching the filesystem. `FileExecutionPolicy.allow_delete` is always false and has no effect.

Overwrite is blocked by default. When `allow_overwrite=false` (the default), any operation targeting an existing path is blocked with a warning. Move is blocked by default unless `allow_move=true` is set in an explicit policy. Copy and mkdir are allowed by default but still subject to workspace boundary and path safety checks.

All operations must stay within the workspace root. Path traversal (`..`), absolute paths, symlink escape, and protected roots are blocked before any operation is planned or applied. Source paths that are symlinks resolving outside the workspace are rejected. Target paths that would escape the workspace via symlink are rejected.

`FileOperationResult` states:
- `planned` — operation would execute in apply mode (dry-run only).
- `skipped` — operation was unnecessary (e.g., directory already exists).
- `applied` — operation was successfully executed (apply mode only).
- `blocked` — operation was prevented by policy or safety check.
- `failed` — operation could not be executed (e.g., source not found).

Dry-run returns `PlannedChange` objects, never `AppliedChange`. Apply mode returns `AppliedChange` only for operations that were actually executed.

Automated file operation tests must use temporary directories, fake fixtures, or controlled workspace layouts only. They must not use real music files, network access, or personal filesystem paths.

`FileExecutionPolicy` is versioned so MusicLab can calibrate execution thresholds before any real provider or handoff behavior is active. The default policy declares `stage: post-download`, `status: contracts-only`, `allow_move: false`, `allow_delete: false`, and `allow_overwrite: false`.

## Handoff Manifest

Handoff manifests are generated by `HandoffManifestService` and written only under `workspace/manifests`. Manifest filenames are restricted to safe basename-only values, and traversal such as `../manifest.json` is rejected. A `manifests` symlink that resolves outside the workspace is rejected before writing.

Manifest content must remain audit-safe:

- No secrets or credentials.
- No raw provider payloads.
- No unnecessary personal absolute paths.
- No complete lyrics or `full_lyrics` fields.
- No raw audio fingerprints.
- No real download or music library side effects.

Paths in manifests must be relative to the workspace when possible. Absolute paths and path traversal markers are blocked during validation.

Dry-run is the default for manifest generation and preview. Apply mode requires an explicit `--apply` flag before any manifest file is written.

## Handoff Apply Bridge

The `HandoffApplyBridge` provides a controlled, file-based, opt-in boundary for Flux → Forge handoff. Safety guarantees:

- **Workspace-only**: All operations confined to workspace root.
- **File-based**: Operates on existing manifest files; no direct Forge import.
- **Dry-run default**: `--apply` must be explicit.
- **No delete**: No destructive operations.
- **No Forge import**: Bridge does not import, call, or depend on Forge.
- **No slskd**: No provider dependencies.
- **No network**: No HTTP requests or external connections.
- **Opt-in**: The bridge must be explicitly invoked; manifests are never auto-applied.
- **Report confinement**: Apply reports are written only to `workspace/reports/`.
- **Guard rules**: Only `approved` items with valid paths can be handed off. Items with unknown type, quarantine, rejected, or delete_eligible status are blocked.

### Forge Ready Gate

Items are marked `forge_ready: true` only when:
- Status is `approved`
- Staging is `approved`
- Routing is `approved`
- Grade is not `bad` or `unknown`
- No objective failures exist
- Decode is confirmed okay

Corrupt files, decode failures, rejected items, and quarantine items are automatically blocked from handoff. Lowpass suspicion and transcode suspicion alone do not block handoff permanently.

Automated handoff tests must use temporary directories, fake fixtures, or controlled workspace layouts only. They must not use real music files, network access, or personal filesystem paths.

## Reports

Reports are written only under `workspace/reports`. Report filenames are restricted to safe basename-only values, and traversal such as `../report.json` is rejected. A `reports` symlink that resolves outside the workspace is rejected before writing.

Report content must remain audit-safe:

- No secrets or credentials.
- No raw provider payloads.
- No unnecessary personal absolute paths.
- No complete lyrics.
- No raw fingerprints.
- No real download or music library side effects.

## Tests

Automated tests must not use a real music library. Tests must not perform real downloads, call real download services, require private credentials, or depend on personal filesystem paths.

Workspace and safety tests use temporary directories only. Tests must not use real music directories, personal download folders, or device storage paths.
