# Architecture

Noqlen Flux Core starts as a service-first Python core. Reusable services should own workflow behavior, safety checks, planning, validation, and structured results. The CLI should remain a thin adapter that parses arguments, calls services, and renders output.

Flux is separate from Noqlen Forge Core. Forge is the reference for architecture, safety, documentation, tests, and release discipline, but Flux has a different domain: search, download coordination, staging, validation, quarantine/rejected handling, cleanup policy, and handoff.

Flux is not a direct continuation of the legacy `slsk` project. The legacy project is useful as a read-only reference for search and staging lessons, but Flux should avoid inheriting terminal coupling, local path assumptions, or provider-specific implementation shape.

Future UI, controller, bridge, or mobile layers must not contain heavy workflow logic. They should call stable service APIs and consume structured results or manifest files.

The bootstrap repository intentionally has no network integration, `slskd` integration, database, auto-import, watch list, or real cleanup behavior.
