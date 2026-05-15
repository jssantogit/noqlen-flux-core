# Handoff

Flux should hand off validated items to Noqlen Forge through a file-based manifest contract.

The manifest describes staged items, validation decisions, quality summary, source-independent metadata, and safe paths needed for the next workflow. Forge integration is not implemented in this bootstrap repository.

## Privacy Boundary

Manifests and structured results must not include secrets, unnecessary personal paths, full lyrics, raw fingerprints, private raw payloads, API keys, tokens, cookies, or provider response dumps.

Paths should be limited to the minimum required for local workflow execution and should prefer Flux-controlled staging roots over personal library locations.

## Contract Direction

Flux is responsible for search, download coordination, staging, validation, quarantine/rejected decisions, cleanup policy, and producing a safe handoff artifact. Forge remains responsible for library management and metadata workflows after an explicit handoff boundary.

## Manifest Version

The handoff manifest is versioned from the start. The initial version is `1` (`HANDOFF_MANIFEST_VERSION = 1`). Future versions must maintain backward compatibility or provide a clear migration path.

## Manifest Structure

A `HandoffManifest` contains:

- `handoff_version` — integer version number (currently 1).
- `source` — identification of the Flux instance that generated the manifest (name, optional version, optional job_id, created_at timestamp).
- `items` — list of `HandoffItem` entries, each representing a staged item with its status, path, and optional references to candidate, quality, and routing data.
- `reports` — list of `HandoffReportRef` entries pointing to related report artifacts.
- `warnings` — list of warning messages from the handoff process.
- `errors` — list of error messages from the handoff process.
- `metadata` — safe metadata about the handoff process.

Each `HandoffItem` contains:

- `item_id` — unique identifier for the item.
- `item_type` — type of item: `track`, `album`, or `unknown`.
- `status` — current status: `approved`, `quarantine`, `rejected`, `review`, `delete_eligible`, or `unknown`.
- `path` — `HandoffPathRef` with relative path and optional workspace area.
- `forge_ready` — indicates whether the item is ready for handoff to Forge. Only set to `true` when status is `approved`, staging is `approved`, routing is `approved`, grade is not `bad` or `unknown`, and no objective failures exist.
- `query_metadata` — optional safe metadata about the original search query.
- `candidate` — optional `HandoffCandidateRef` with candidate identification and scoring info.
- `quality` — optional `HandoffQualityRef` with quality grade and finding counts.
- `routing` — optional `HandoffRoutingRef` with routing outcome and action type.
- `reports` — list of `HandoffReportRef` entries specific to this item.
- `warnings` — list of warning messages.
- `errors` — list of error messages.
- `metadata` — safe metadata.

## Handoff Apply Bridge

The handoff apply bridge is a controlled, file-based, opt-in boundary for Flux → Forge handoff. It operates on existing manifest files and produces apply reports.

### Apply Flow

1. Flux generates a manifest via `handoff demo --apply` to `workspace/manifests/`.
2. The manifest is validated with `handoff validate --manifest`.
3. The apply bridge reads the manifest and checks each item for Forge readiness:
   - Only items with `status: approved` can be handed off.
   - Items with unknown type are skipped.
   - Items failing validation are blocked.
4. The bridge produces a `HandoffApplyReport` with applied/blocked/skipped counts.
5. On `--apply`, the report is written to `workspace/reports/`.

### Guard Rules

- Non-approved items (quarantine, rejected, review, delete_eligible) are blocked.
- Corrupt/decode_failure scenarios produce blocked handoff items.
- Qobuz-like cutoff with decode_ok is not blocked.
- Lowpass suspicion alone does not block handoff.
- Good-category scenarios produce forge_ready items when fully approved.
- Delete-eligible staging blocks handoff.

### Key Properties

- **File-based**: Works exclusively on manifest files in workspace. No direct Forge integration.
- **Workspace-only**: All operations confined to workspace root.
- **Dry-run default**: `--apply` must be explicit.
- **No delete**: No destructive operations.
- **No import**: No automatic import into Forge.
- **No slskd**: No provider dependencies in the bridge.
- **Opt-in**: Bridge must be explicitly invoked.

## Forbidden Fields

The following fields are explicitly forbidden in manifest metadata:

- `full_lyrics` / `lyrics` — complete lyrics must never appear in manifests.
- `fingerprint` / `raw_fingerprint` — raw audio fingerprints must never appear in manifests.
- `raw_provider_payload` / `provider_payload` — raw provider responses must never appear in manifests.
- `secret` / `token` / `password` / `authorization` / `cookie` / `private` — secrets and credentials must never appear in manifests.

Any attempt to include these fields in manifest metadata will raise a validation error.

## Future Flux -> Forge Flow

The intended future flow is:

1. Flux searches, downloads (via provider), validates, routes, and stages items.
2. Flux generates a `HandoffManifest` with safe, versioned, and auditable data.
3. The manifest is written to `workspace/manifests/` as a JSON file.
4. The manifest is validated and the apply bridge produces a `HandoffApplyReport`.
5. Forge reads the manifest and apply report to perform metadata correction, enrichment, import orchestration, and library organization.
6. Forge does not download; Flux does not correct final library metadata.

The handoff apply bridge is implemented as a controlled, file-based boundary. Forge integration beyond the manifest contract is not implemented in this bootstrap repository. The `HandoffApplyBridge` class and `forge_ready` field on `HandoffItem` provide the contractual foundation for future Forge consumption.

## CLI Usage

Preview a demo handoff manifest without writing a file:

```bash
noqlen-flux handoff demo --workspace ./flux-workspace --dry-run
```

Apply mode must be explicit before a manifest is written:

```bash
noqlen-flux handoff demo --workspace ./flux-workspace --apply
```

Validate a demo manifest:

```bash
noqlen-flux handoff validate --workspace ./flux-workspace --demo
```

Validate an existing manifest file:

```bash
noqlen-flux handoff validate --workspace ./flux-workspace --manifest manifests/handoff-xxx.json
```

Preview handoff apply (dry-run, no file writes):

```bash
noqlen-flux handoff apply --workspace ./flux-workspace --manifest manifests/handoff-xxx.json --dry-run
```

Execute handoff apply bridge (writes report to workspace/reports/):

```bash
noqlen-flux handoff apply --workspace ./flux-workspace --manifest manifests/handoff-xxx.json --apply
```

Manifest files are confined to `workspace/manifests/`. Apply reports are confined to `workspace/reports/`. No network calls, downloads, imports, cleanup, or music library writes are performed.
