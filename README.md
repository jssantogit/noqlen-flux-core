# Noqlen Flux Core

Noqlen Flux Core is the future core for search, download, staging, validation, and handoff workflows in the Noqlen ecosystem.

This repository is in its initial bootstrap phase. It does not perform real downloads, imports, network calls, library writes, cleanup, or automatic deletion.

## Lineage

- Noqlen Forge Core is the architectural reference for service-first design, safety, docs, tests, and release hardening.
- The legacy `slsk` project is a reference and laboratory for search/download/staging ideas, not a direct base for Flux.
- Flux is a separate project and should not be treated as a continuation of `slsk`.

## Current Scope

- A minimal Python package named `noqlen_flux`.
- A public future CLI entry point named `noqlen-flux`.
- Safe stub commands only.

No operation currently touches a real music library or downloads music.
