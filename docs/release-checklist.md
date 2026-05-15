# Noqlen Flux Core — MVP Release Hardening Checklist

> **Status**: MVP Core Locked  
> **Version**: 0.1.0  
> **Last Audit**: Bloco F (Cleanup + Hardening)  
> **Pending Structural Work**: NativeSoulseekProvider (future adapter only)

---

## 1. Provider Backend

- [x] `slskd` is the initial backend provider (adapter-only)
- [x] `NativeSoulseekProvider` is a future pendency — NOT a current blocker
- [x] Core is provider-agnostic: all services depend on interfaces, not concrete providers
- [x] No central service imports `slskd`
- [x] Provider health and capabilities are introspectable

## 2. Quality Pipeline

- [x] Quality analysis is evidence, not action
- [x] `QualityGrade`: EXCELLENT, MEDIUM, BAD, UNKNOWN
- [x] Quality never writes, deletes, or modifies files
- [x] Spectral analysis is heuristic-only, never objective failure alone
- [x] Cutoff/lowpass signals are heuristic warnings, never cause BAD grade
- [x] Advanced quality confidence is evidence, never a decision
- [x] Transcode detection is suspicion, not a routing action

## 3. Routing Pipeline

- [x] Routing decisions are evidence, not action
- [x] `RoutingOutcome`: APPROVED, QUARANTINE, REJECTED, REVIEW, DELETE_ELIGIBLE, UNKNOWN
- [x] DELETE_ELIGIBLE is a flag only — NEVER triggers automatic deletion
- [x] Heuristic warnings route to REVIEW or QUARANTINE, never REJECTED/DELETE_ELIGIBLE
- [x] Objective failures route to REJECTED, never DELETE_ELIGIBLE
- [x] Routing never writes, deletes, or modifies files

## 4. Staging Pipeline

- [x] Staging plans are planned-only by default
- [x] `StagingExecutionPolicy.allow_delete` is `False`
- [x] NO real deletes exist in staging execution
- [x] Copy-on-apply within workspace is allowed (opt-in via --apply)
- [x] Move is blocked by default in staging execution policy

## 5. Cleanup Pipeline (NEW — Bloco F)

- [x] Cleanup planning is planned-only (CleanupPlanningService)
- [x] Cleanup execution is conservative and opt-in (CleanupExecutionService)
- [x] `CleanupExecutionPolicy.allow_delete` is `False` by default
- [x] Allowed operations (workspace-only):
  - Remove expired temporary reports
  - Remove staging temp files
  - Move rejected items to trash/rejected-retained
  - Clean invalid manifests
  - Clean incomplete artifacts
- [x] Prohibited by default:
  - Delete real library
  - Delete outside workspace
  - Delete approved/import-ready
  - Delete quarantine without retention policy
  - Delete rejected without apply + policy + confirmation
- [x] Hard delete requires ALL of: `--apply`, `policy.allow_delete=True`, target in workspace, retention expired, explicit confirmation, structured report
- [x] Dry-run is the default mode

## 6. Auto-Cleanup (NEW — Bloco F)

- [x] Auto-cleanup is opt-in (`AutoCleanupPolicy.enabled=False`)
- [x] Never runs by default
- [x] Conservative preset: only safe cleanup actions (remove temp, clean invalid/incomplete)
- [x] Workspace-only: never touches files outside workspace
- [x] Never touches real music library
- [x] Policy-driven: requires explicit `AutoCleanupPolicy` configuration
- [x] Requires report generation

## 7. Handoff Pipeline

- [x] Handoff manifest is a contract, not a file operation
- [x] Handoff apply bridge is controlled, file-based
- [x] Manifest validation prevents invalid handoffs
- [x] Only approved items with forge_ready=True can be handed off

## 8. MusicLab

- [x] MusicLab is a proving ground
- [x] Scoring calibration pass rate: 100% (all baseline scenarios passing)
- [x] Quality calibration pass rate: 100% (all baseline scenarios passing)
- [x] MVP E2E scenarios: 12 mandatory scenarios covering full pipeline
- [x] False-positive guard scenarios: 7 critical guard scenarios
- [x] No real audio used in MusicLab
- [x] No real downloads executed
- [x] All fixtures are synthetic (SyntheticProbeProfile)
- [x] Destructive action detection is enforced

## 9. Safety Protections

- [x] Dry-run is default everywhere
- [x] `--apply` must be explicit
- [x] Path containment: all file operations confined to workspace root
- [x] Symlink escape blocked
- [x] Absolute paths blocked
- [x] Traversal markers blocked
- [x] Protected roots blocked
- [x] Workspace-only enforcement
- [x] Approved/import-ready items never auto-cleaned
- [x] Real music library never touched

## 10. Test Coverage

- [x] 1216 tests passing (1216/1216)
- [x] Pipeline boundaries tested: search→score→download→transfer→quality→routing→staging→cleanup→handoff
- [x] Provider boundaries tested: slskd isolation enforced
- [x] Cleanup models tested: enums, serialization, path safety, domain separation
- [x] Cleanup service tested: default policy, decision logic, multipart plans, boundary checks
- [x] No real providers in tests
- [x] No real network in tests
- [x] No real filesystem mutations outside tmp_path

## 11. Code Quality

- [x] No references to Sonivra
- [x] No `slsk_auto` patterns
- [x] No versioned workflow files (.opencode/, .skills/)
- [x] No versioned audit reports
- [x] No secrets, tokens, or credentials
- [x] No personal paths
- [x] No raw provider payloads
- [x] No raw audio fingerprints
- [x] No complete lyrics
- [x] All docs in English
- [x] CLI help coherent
- [x] All existing commands continue working

## 12. Pending Structural Work

| Item | Status | Blocker? |
|------|--------|----------|
| NativeSoulseekProvider | Pending | No — slskd adapter is sufficient for MVP |
| Forge integration (real) | Pending | No — handoff bridge provides file-based contract |
| Auto-import | Pending (opt-in only) | No |
| Real downloads | Pending | No — all download planning exists, execution is gated |
| UI/Mobile | Out of scope | No |
| Anchor | Out of scope | No |

## 13. Release Readiness Assessment

| Criteria | Status |
|----------|--------|
| All 12 MVP E2E scenarios pass | Pass |
| All false-positive guard scenarios pass | Pass |
| All 1216 tests pass | Pass |
| Dry-run is default | Confirmed |
| No destructive action by default | Confirmed |
| Cleanup is conservative | Confirmed |
| Auto-cleanup is opt-in | Confirmed |
| Delete is blocked by default | Confirmed |
| Workspace safety enforced | Confirmed |
| No Sonivra references | Confirmed |
| No secrets/personal paths | Confirmed |

### MVP Core Status: **LOCKED — Ready for Final Audit**

The MVP core is considered feature-complete and hardened. The only pending structural work (NativeSoulseekProvider) does not block release.
