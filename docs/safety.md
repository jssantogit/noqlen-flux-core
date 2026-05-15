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

## Search Providers

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

Quality analysis is currently contracts-only. `QualityService` does not perform real audio analysis, use ffmpeg, perform transcode detection, measure loudness, detect clipping, or run low-pass analysis. It accepts structured fake data and returns simulated `QualityResult` objects.

Future real audio analysis must operate inside an isolated workspace. It must not touch a real music library, personal music folders, or download folders. All file operations must be confined to the Flux workspace root with path containment and symlink protection.

`QualityGrade` is a post-download quality classification (`excellent`, `medium`, `bad`, `unknown`). It is NOT `CandidateRisk`. `CandidateRisk` is a pre-download risk signal. The two must remain separate: scoring does not import quality, and quality does not import scoring.

Heuristic warnings such as low-pass suspicion, clipping suspicion, or transcode suspicion must remain informational until MusicLab calibration establishes strong thresholds. They must not cause file deletion, movement, quarantine, or rejection by themselves.

Objective failures can inform future routing decisions but do not execute delete, quarantine, or rejection in this commit. `QualityResult` does not contain `RoutingDecision`. A future routing layer will combine `CandidateRisk`, `QualityGrade`, workspace policy, and user calibration.

Automated quality tests must use fake data, temporary directories, or controlled fixtures only. They must not use real audio files, network access, ffmpeg, transcode tools, or personal filesystem paths.

Quality contracts must not expose:

- Complete lyrics.
- Raw audio fingerprints.
- Raw provider payloads.
- Secrets, tokens, or credentials.
- Unnecessary personal absolute paths.

`QualityProfile` is versioned so MusicLab can calibrate thresholds before any real provider or audio analysis is active. The default profile declares `stage: post-download` and `status: contracts-only`.

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
