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

Cleanup must be conservative. Automatic deletion should only apply to delete-eligible items with objective failures and clear retention policy. No auto-delete behavior is active in the bootstrap project.

## Path Safety

Future file operations must enforce path containment, symlink protection, and path traversal protection. Resolved paths must stay inside the intended Flux-controlled root before moves, writes, cleanup, or handoff.

Path traversal attempts that resolve outside the workspace are blocked. Symlinks that resolve outside the workspace are also blocked before Flux plans or applies directory operations.

Protected roots can be configured for service calls. Any target inside a protected root is rejected, and a workspace root that would contain a protected root is rejected. CLI environment support is intentionally minimal and only uses the `NOQLEN_FLUX_` prefix.

## MusicLab

MusicLab is confined to `workspace/musiclab`. It must never touch a real music library, personal music folders, download folders, device storage, or external provider state.

MusicLab tests and services must not use real network calls, real downloads, `slskd`, ffmpeg, transcode, quality inspection, cleanup, auto-delete, or handoff. Current fixtures are controlled fake JSON/text artifacts only.

MusicLab session and fixture identifiers are restricted to safe basename-like values. Path traversal such as `../session`, absolute paths, separators, and unsafe characters are rejected before planning or applying changes.

MusicLab applies the same workspace containment, symlink escape blocking, and protected-root checks as other Flux services. A symlink that would move MusicLab state outside the workspace is rejected before directory creation or fixture writing.

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
