# Handoff

Flux should hand off validated items to Noqlen Forge through a future file-based manifest contract.

The manifest should describe staged items, validation decisions, quality summary, source-independent metadata, and safe paths needed for the next workflow. Forge integration is not implemented in this bootstrap repository.

## Privacy Boundary

Manifests and structured results must not include secrets, unnecessary personal paths, full lyrics, raw fingerprints, private raw payloads, API keys, tokens, cookies, or provider response dumps.

Paths should be limited to the minimum required for local workflow execution and should prefer Flux-controlled staging roots over personal library locations.

## Contract Direction

Flux is responsible for search, download coordination, staging, validation, quarantine/rejected decisions, cleanup policy, and producing a safe handoff artifact. Forge remains responsible for library management and metadata workflows after an explicit handoff boundary.
