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
- `query_metadata` — optional safe metadata about the original search query.
- `candidate` — optional `HandoffCandidateRef` with candidate identification and scoring info.
- `quality` — optional `HandoffQualityRef` with quality grade and finding counts.
- `routing` — optional `HandoffRoutingRef` with routing outcome and action type.
- `reports` — list of `HandoffReportRef` entries specific to this item.
- `warnings` — list of warning messages.
- `errors` — list of error messages.
- `metadata` — safe metadata.

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
4. Forge reads the manifest and performs metadata correction, enrichment, import orchestration, and library organization.
5. Forge does not download; Flux does not correct final library metadata.

This integration is not implemented in this commit. The manifest contract is the foundation for that future boundary.

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

Manifest files are confined to `workspace/manifests` and do not perform network calls, downloads, imports, cleanup, or music library writes.
