from __future__ import annotations

import argparse

from . import __version__
from .config import config_from_env
from .downloads import DownloadConstraint, DownloadIntent, DownloadRequest
from .providers.fake import FakeSearchProvider
from .providers.fake_transfer import FakeTransferProvider
from .providers.status import ProviderAvailability, ProviderKind
from .reports import ReportFormat
from .results import FluxResult, Status
from .search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from .services import CandidateScoringService, CleanupPlanningService, DoctorService, DownloadPlanningService, HandoffManifestService, MusicLabService, ProviderService, QualityService, ReportService, RoutingDecisionService, SafeFileOperationService, SearchService, StagingExecutionService, StagingPlanService, TransferPlanningService, WorkspaceService
from .transfers import TransferPriority


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noqlen-flux",
        description="Noqlen Flux Core bootstrap CLI. No real download or library operation is implemented.",
    )
    parser.add_argument("--version", action="version", version=f"noqlen-flux {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    doctor = subparsers.add_parser("doctor", help="Show safe bootstrap status")
    doctor.set_defaults(func=run_doctor)

    workspace = subparsers.add_parser("workspace", help="Inspect or initialize a safe Flux workspace")
    workspace_subparsers = workspace.add_subparsers(dest="workspace_command")

    workspace_inspect = workspace_subparsers.add_parser("inspect", help="Inspect a Flux workspace layout")
    workspace_inspect.add_argument("path", help="Workspace root path")
    workspace_inspect.set_defaults(func=run_workspace_inspect)

    workspace_init = workspace_subparsers.add_parser("init", help="Plan or create Flux workspace directories")
    workspace_init.add_argument("path", help="Workspace root path")
    mode = workspace_init.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan changes without creating directories")
    mode.add_argument("--apply", action="store_true", help="Create missing workspace directories")
    workspace_init.set_defaults(func=run_workspace_init)

    report = subparsers.add_parser("report", help="Plan or write safe report artifacts")
    report_subparsers = report.add_subparsers(dest="report_command")

    report_demo = report_subparsers.add_parser("demo", help="Generate a safe demo report result")
    report_demo.add_argument("--workspace", required=True, help="Workspace root path")
    report_demo.add_argument("--format", choices=[item.value for item in ReportFormat], default=ReportFormat.JSON.value)
    report_mode = report_demo.add_mutually_exclusive_group()
    report_mode.add_argument("--dry-run", action="store_true", help="Plan report writing without creating a file")
    report_mode.add_argument("--apply", action="store_true", help="Write the report inside workspace/reports")
    report_demo.set_defaults(func=run_report_demo)

    search = subparsers.add_parser("search", help="Run safe provider-backed search flows")
    search_subparsers = search.add_subparsers(dest="search_provider")
    search_fake = search_subparsers.add_parser("fake", help="Search an in-memory fake provider")
    search_fake_subparsers = search_fake.add_subparsers(dest="search_kind")

    search_fake_track = search_fake_subparsers.add_parser("track", help="Search a fake track candidate")
    search_fake_track.add_argument("--artist", required=True, help="Artist name")
    search_fake_track.add_argument("--title", required=True, help="Track title")
    search_fake_track.add_argument("--limit", type=int, help="Optional positive result limit")
    search_fake_track.add_argument("--score", action="store_true", help="Include explainable pre-download scoring")
    search_fake_track.set_defaults(func=run_search_fake_track)

    search_fake_album = search_fake_subparsers.add_parser("album", help="Search a fake album candidate")
    search_fake_album.add_argument("--artist", required=True, help="Artist name")
    search_fake_album.add_argument("--album", required=True, help="Album title")
    search_fake_album.add_argument("--limit", type=int, help="Optional positive result limit")
    search_fake_album.add_argument("--score", action="store_true", help="Include explainable pre-download scoring")
    search_fake_album.set_defaults(func=run_search_fake_album)

    musiclab = subparsers.add_parser("musiclab", help="Inspect or initialize isolated MusicLab calibration state")
    musiclab_subparsers = musiclab.add_subparsers(dest="musiclab_command")

    musiclab_inspect = musiclab_subparsers.add_parser("inspect", help="Inspect MusicLab layout without creating files")
    musiclab_inspect.add_argument("--workspace", required=True, help="Workspace root path")
    musiclab_inspect.set_defaults(func=run_musiclab_inspect)

    musiclab_init = musiclab_subparsers.add_parser("init", help="Plan or create MusicLab directories")
    musiclab_init.add_argument("--workspace", required=True, help="Workspace root path")
    musiclab_init_mode = musiclab_init.add_mutually_exclusive_group()
    musiclab_init_mode.add_argument("--dry-run", action="store_true", help="Plan changes without creating directories")
    musiclab_init_mode.add_argument("--apply", action="store_true", help="Create missing MusicLab directories")
    musiclab_init.set_defaults(func=run_musiclab_init)

    musiclab_session = musiclab_subparsers.add_parser("session", help="Manage isolated MusicLab sessions")
    musiclab_session_subparsers = musiclab_session.add_subparsers(dest="musiclab_session_command")
    musiclab_session_create = musiclab_session_subparsers.add_parser("create", help="Plan or create a MusicLab session")
    musiclab_session_create.add_argument("--workspace", required=True, help="Workspace root path")
    musiclab_session_create.add_argument("--session", dest="session_id", help="Optional safe session id")
    musiclab_session_create.add_argument("--purpose", help="Optional session purpose")
    musiclab_session_mode = musiclab_session_create.add_mutually_exclusive_group()
    musiclab_session_mode.add_argument("--dry-run", action="store_true", help="Plan changes without creating directories")
    musiclab_session_mode.add_argument("--apply", action="store_true", help="Create the session directories")
    musiclab_session_create.set_defaults(func=run_musiclab_session_create)

    musiclab_fixture = musiclab_subparsers.add_parser("fixture", help="Manage controlled fake MusicLab fixtures")
    musiclab_fixture_subparsers = musiclab_fixture.add_subparsers(dest="musiclab_fixture_command")
    musiclab_fixture_create = musiclab_fixture_subparsers.add_parser("create", help="Plan or write a fake MusicLab fixture")
    musiclab_fixture_create.add_argument("--workspace", required=True, help="Workspace root path")
    musiclab_fixture_create.add_argument("--session", required=True, dest="session_id", help="Safe MusicLab session id")
    musiclab_fixture_create.add_argument("--fixture-id", required=True, help="Safe fixture id")
    musiclab_fixture_create.add_argument("--kind", required=True, help="Safe fixture kind")
    musiclab_fixture_mode = musiclab_fixture_create.add_mutually_exclusive_group()
    musiclab_fixture_mode.add_argument("--dry-run", action="store_true", help="Plan changes without writing a file")
    musiclab_fixture_mode.add_argument("--apply", action="store_true", help="Write the fake fixture")
    musiclab_fixture_create.set_defaults(func=run_musiclab_fixture_create)

    download = subparsers.add_parser("download", help="Plan safe download operations")
    download_subparsers = download.add_subparsers(dest="download_command")

    download_plan = download_subparsers.add_parser("plan", help="Plan a download without executing it")
    download_plan_subparsers = download_plan.add_subparsers(dest="download_plan_provider")

    download_plan_fake = download_plan_subparsers.add_parser("fake", help="Plan a download from a fake provider")
    download_plan_fake_subparsers = download_plan_fake.add_subparsers(dest="download_plan_kind")

    download_plan_fake_track = download_plan_fake_subparsers.add_parser("track", help="Plan a fake track download")
    download_plan_fake_track.add_argument("--artist", required=True, help="Artist name")
    download_plan_fake_track.add_argument("--title", required=True, help="Track title")
    download_plan_fake_track.add_argument("--score", action="store_true", help="Include pre-download scoring")
    download_plan_fake_track.add_argument("--score-min", type=float, help="Minimum score required to plan")
    download_plan_fake_track.add_argument("--max-files", type=int, help="Maximum files allowed")
    download_plan_fake_track.add_argument("--max-total-bytes", type=int, help="Maximum total bytes allowed")
    download_plan_fake_track.add_argument("--allow-locked", action="store_true", help="Allow locked files")
    download_plan_fake_track.set_defaults(func=run_download_plan_fake_track)

    download_plan_fake_album = download_plan_fake_subparsers.add_parser("album", help="Plan a fake album download")
    download_plan_fake_album.add_argument("--artist", required=True, help="Artist name")
    download_plan_fake_album.add_argument("--album", required=True, help="Album title")
    download_plan_fake_album.add_argument("--score", action="store_true", help="Include pre-download scoring")
    download_plan_fake_album.add_argument("--score-min", type=float, help="Minimum score required to plan")
    download_plan_fake_album.add_argument("--max-files", type=int, help="Maximum files allowed")
    download_plan_fake_album.add_argument("--max-total-bytes", type=int, help="Maximum total bytes allowed")
    download_plan_fake_album.add_argument("--allow-locked", action="store_true", help="Allow locked files")
    download_plan_fake_album.set_defaults(func=run_download_plan_fake_album)

    transfer = subparsers.add_parser("transfer", help="Plan safe transfer/queue operations")
    transfer_subparsers = transfer.add_subparsers(dest="transfer_command")

    transfer_plan = transfer_subparsers.add_parser("plan", help="Plan a transfer queue without executing it")
    transfer_plan_subparsers = transfer_plan.add_subparsers(dest="transfer_plan_provider")

    transfer_plan_fake = transfer_plan_subparsers.add_parser("fake", help="Plan a transfer from a fake provider")
    transfer_plan_fake_subparsers = transfer_plan_fake.add_subparsers(dest="transfer_plan_kind")

    transfer_plan_fake_track = transfer_plan_fake_subparsers.add_parser("track", help="Plan a fake track transfer")
    transfer_plan_fake_track.add_argument("--artist", required=True, help="Artist name")
    transfer_plan_fake_track.add_argument("--title", required=True, help="Track title")
    transfer_plan_fake_track.add_argument("--score", action="store_true", help="Include pre-download scoring")
    transfer_plan_fake_track.add_argument("--priority", choices=[item.value for item in TransferPriority], default=TransferPriority.NORMAL.value)
    transfer_plan_fake_track.set_defaults(func=run_transfer_plan_fake_track)

    transfer_plan_fake_album = transfer_plan_fake_subparsers.add_parser("album", help="Plan a fake album transfer")
    transfer_plan_fake_album.add_argument("--artist", required=True, help="Artist name")
    transfer_plan_fake_album.add_argument("--album", required=True, help="Album title")
    transfer_plan_fake_album.add_argument("--score", action="store_true", help="Include pre-download scoring")
    transfer_plan_fake_album.add_argument("--priority", choices=[item.value for item in TransferPriority], default=TransferPriority.NORMAL.value)
    transfer_plan_fake_album.set_defaults(func=run_transfer_plan_fake_album)

    provider = subparsers.add_parser("provider", help="Inspect provider health and capabilities")
    provider_subparsers = provider.add_subparsers(dest="provider_command")

    provider_inspect = provider_subparsers.add_parser("inspect", help="Inspect provider health and capabilities")
    provider_inspect.add_argument("provider_kind", choices=["fake", "fake-transfer"], help="Provider to inspect")
    provider_inspect.set_defaults(func=run_provider_inspect)

    provider_health = provider_subparsers.add_parser("health", help="Check provider health status")
    provider_health.add_argument("provider_kind", choices=["fake", "fake-transfer"], help="Provider to check")
    provider_health.set_defaults(func=run_provider_health)

    quality = subparsers.add_parser("quality", help="Inspect post-download quality (contracts-only, no real audio analysis)")
    quality_subparsers = quality.add_subparsers(dest="quality_command")

    quality_fake = quality_subparsers.add_parser("fake", help="Generate a fake quality result for testing")
    quality_fake.add_argument("grade", choices=["excellent", "medium", "bad", "unknown"], help="Fake quality grade to simulate")
    quality_fake.add_argument("--item-id", default="fake-item-1", help="Optional item id")
    quality_fake.set_defaults(func=run_quality_fake)

    routing = subparsers.add_parser("routing", help="Plan post-download routing decisions (planned-only, no execution)")
    routing_subparsers = routing.add_subparsers(dest="routing_command")

    routing_fake = routing_subparsers.add_parser("fake", help="Route a fake quality result through routing policy")
    routing_fake.add_argument("scenario", choices=["excellent", "medium", "bad-objective", "bad-heuristic", "unknown"], help="Routing scenario to simulate")
    routing_fake.add_argument("--item-id", default="fake-item-1", help="Optional item id")
    routing_fake.set_defaults(func=run_routing_fake)

    staging = subparsers.add_parser("staging", help="Plan or execute safe staging operations")
    staging_subparsers = staging.add_subparsers(dest="staging_command")

    staging_fake = staging_subparsers.add_parser("fake", help="Plan staging for a fake routing outcome")
    staging_fake.add_argument("outcome", choices=["approved", "quarantine", "rejected", "delete-eligible", "review"], help="Fake routing outcome to stage")
    staging_fake.add_argument("--item-id", default="fake-item-1", help="Optional item id")
    staging_fake.set_defaults(func=run_staging_fake)

    staging_execute = staging_subparsers.add_parser("execute", help="Execute a staging plan within workspace boundary")
    staging_execute.add_argument("scenario", choices=["fake-approved", "fake-quarantine", "fake-rejected", "fake-delete-eligible", "fake-review"], help="Fake staging scenario to execute")
    staging_execute.add_argument("--workspace", required=True, help="Workspace root path")
    staging_execute_mode = staging_execute.add_mutually_exclusive_group()
    staging_execute_mode.add_argument("--dry-run", action="store_true", help="Plan staging execution without altering filesystem")
    staging_execute_mode.add_argument("--apply", action="store_true", help="Execute staging operations within workspace")
    staging_execute.set_defaults(func=run_staging_execute)

    fileops = subparsers.add_parser("fileops", help="Plan or execute safe filesystem operations")
    fileops_subparsers = fileops.add_subparsers(dest="fileops_command")

    fileops_demo = fileops_subparsers.add_parser("demo", help="Demonstrate safe file operations within workspace")
    fileops_demo.add_argument("--workspace", required=True, help="Workspace root path")
    fileops_demo_mode = fileops_demo.add_mutually_exclusive_group()
    fileops_demo_mode.add_argument("--dry-run", action="store_true", help="Plan operations without executing them")
    fileops_demo_mode.add_argument("--apply", action="store_true", help="Execute planned operations within workspace")
    fileops_demo.set_defaults(func=run_fileops_demo)

    handoff = subparsers.add_parser("handoff", help="Generate safe handoff manifests for future Forge integration")
    handoff_subparsers = handoff.add_subparsers(dest="handoff_command")

    handoff_demo = handoff_subparsers.add_parser("demo", help="Generate a safe demo handoff manifest")
    handoff_demo.add_argument("--workspace", required=True, help="Workspace root path")
    handoff_demo_mode = handoff_demo.add_mutually_exclusive_group()
    handoff_demo_mode.add_argument("--dry-run", action="store_true", help="Preview manifest without writing a file")
    handoff_demo_mode.add_argument("--apply", action="store_true", help="Write the manifest inside workspace/manifests")
    handoff_demo.set_defaults(func=run_handoff_demo)

    handoff_validate = handoff_subparsers.add_parser("validate", help="Validate a demo handoff manifest")
    handoff_validate.add_argument("--workspace", required=True, help="Workspace root path")
    handoff_validate.add_argument("--demo", action="store_true", help="Validate a demo manifest")
    handoff_validate.set_defaults(func=run_handoff_validate)

    cleanup = subparsers.add_parser("cleanup", help="Plan safe cleanup operations (planned-only, no execution)")
    cleanup_subparsers = cleanup.add_subparsers(dest="cleanup_command")

    cleanup_plan = cleanup_subparsers.add_parser("plan", help="Plan cleanup without executing it")
    cleanup_plan_subparsers = cleanup_plan.add_subparsers(dest="cleanup_plan_source")

    cleanup_plan_fake = cleanup_plan_subparsers.add_parser("fake", help="Plan cleanup from fake candidates")
    cleanup_plan_fake.add_argument("--workspace", help="Optional workspace root path")
    cleanup_plan_fake.add_argument("--allow-delete-planning", action="store_true", help="Allow delete planning in policy")
    cleanup_plan_fake.add_argument("--min-age-days", type=int, help="Minimum age in days for cleanup candidates")
    cleanup_plan_fake_mode = cleanup_plan_fake.add_mutually_exclusive_group()
    cleanup_plan_fake_mode.add_argument("--dry-run", action="store_true", help="Plan cleanup without executing it (default)")
    cleanup_plan_fake_mode.add_argument("--apply", action="store_true", help="Apply mode is not supported for cleanup planning")
    cleanup_plan_fake.set_defaults(func=run_cleanup_plan_fake)

    return parser


def run_doctor(_args: argparse.Namespace) -> int:
    result = DoctorService().run()
    print(_render_result(result))
    return _exit_code(result.status)


def run_workspace_inspect(args: argparse.Namespace) -> int:
    result = WorkspaceService().inspect_workspace(config_from_env(args.path, dry_run=True))
    print(_render_result(result))
    return _exit_code(result.status)


def run_workspace_init(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    result = WorkspaceService().ensure_workspace(config_from_env(args.path, dry_run=dry_run), dry_run=dry_run)
    print(_render_result(result))
    return _exit_code(result.status)


def run_report_demo(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    service = ReportService()
    config = config_from_env(args.workspace, dry_run=dry_run)
    source = service.demo_result()
    if dry_run:
        result = service.preview_report(config, source, args.format)
    else:
        result = service.write_report(config, source, args.format)
    print(_render_result(result))
    return _exit_code(result.status)


def run_search_fake_track(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title, limit=args.limit)
    result = SearchService().search(query, _demo_fake_provider(), _scoring_service(args))
    print(_render_result(result))
    return _exit_code(result.status)


def run_search_fake_album(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.ALBUM, artist=args.artist, album=args.album, limit=args.limit)
    result = SearchService().search(query, _demo_fake_provider(), _scoring_service(args))
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_inspect(args: argparse.Namespace) -> int:
    result = MusicLabService().inspect_lab(config_from_env(args.workspace, dry_run=True))
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_init(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    result = MusicLabService().init_lab(config_from_env(args.workspace, dry_run=dry_run), dry_run=dry_run)
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_session_create(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    result = MusicLabService().create_session(
        config_from_env(args.workspace, dry_run=dry_run),
        session_id=args.session_id,
        purpose=args.purpose,
        dry_run=dry_run,
    )
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_fixture_create(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    result = MusicLabService().create_fake_fixture(
        config_from_env(args.workspace, dry_run=dry_run),
        session_id=args.session_id,
        fixture_id=args.fixture_id,
        kind=args.kind,
        dry_run=dry_run,
    )
    print(_render_result(result))
    return _exit_code(result.status)


def run_download_plan_fake_track(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title)
    provider = _demo_fake_provider()
    provider_result = provider.search(query)
    if not provider_result.candidates:
        result = DownloadPlanningService().result(
            status=Status.FAILED,
            error="no candidates found",
        )
        print(_render_result(result))
        return 1
    candidate = provider_result.candidates[0]
    score = None
    if args.score:
        score = CandidateScoringService().score_candidate(query, candidate)
    constraints = DownloadConstraint(
        allow_locked=getattr(args, "allow_locked", False),
        require_score_min=getattr(args, "score_min", None),
        max_files=getattr(args, "max_files", None),
        max_total_bytes=getattr(args, "max_total_bytes", None),
    )
    request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.TRACK,
        query=f"{args.artist} - {args.title}",
        score=score,
        constraints=constraints,
    )
    result = DownloadPlanningService().plan_download(request)
    print(_render_result(result))
    return _exit_code(result.status)


def run_download_plan_fake_album(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.ALBUM, artist=args.artist, album=args.album)
    provider = _demo_fake_provider()
    provider_result = provider.search(query)
    if not provider_result.candidates:
        result = DownloadPlanningService().result(
            status=Status.FAILED,
            error="no candidates found",
        )
        print(_render_result(result))
        return 1
    candidate = provider_result.candidates[0]
    score = None
    if args.score:
        score = CandidateScoringService().score_candidate(query, candidate)
    constraints = DownloadConstraint(
        allow_locked=getattr(args, "allow_locked", False),
        require_score_min=getattr(args, "score_min", None),
        max_files=getattr(args, "max_files", None),
        max_total_bytes=getattr(args, "max_total_bytes", None),
    )
    request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.ALBUM,
        query=f"{args.artist} - {args.album}",
        score=score,
        constraints=constraints,
    )
    result = DownloadPlanningService().plan_download(request)
    print(_render_result(result))
    return _exit_code(result.status)


def run_transfer_plan_fake_track(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title)
    provider = _demo_fake_provider()
    provider_result = provider.search(query)
    if not provider_result.candidates:
        result = TransferPlanningService().result(
            status=Status.FAILED,
            error="no candidates found",
        )
        print(_render_result(result))
        return 1
    candidate = provider_result.candidates[0]
    score = None
    if args.score:
        score = CandidateScoringService().score_candidate(query, candidate)
    download_request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.TRACK,
        query=f"{args.artist} - {args.title}",
        score=score,
    )
    download_plan_result = DownloadPlanningService().plan_download(download_request)
    if download_plan_result.status == Status.FAILED:
        print(_render_result(download_plan_result))
        return 1
    download_plan = _extract_download_plan(download_plan_result)
    priority = TransferPriority(args.priority)
    result = TransferPlanningService().plan_queue(download_plan, priority=priority)
    print(_render_result(result))
    return _exit_code(result.status)


def run_transfer_plan_fake_album(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.ALBUM, artist=args.artist, album=args.album)
    provider = _demo_fake_provider()
    provider_result = provider.search(query)
    if not provider_result.candidates:
        result = TransferPlanningService().result(
            status=Status.FAILED,
            error="no candidates found",
        )
        print(_render_result(result))
        return 1
    candidate = provider_result.candidates[0]
    score = None
    if args.score:
        score = CandidateScoringService().score_candidate(query, candidate)
    download_request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.ALBUM,
        query=f"{args.artist} - {args.album}",
        score=score,
    )
    download_plan_result = DownloadPlanningService().plan_download(download_request)
    if download_plan_result.status == Status.FAILED:
        print(_render_result(download_plan_result))
        return 1
    download_plan = _extract_download_plan(download_plan_result)
    priority = TransferPriority(args.priority)
    result = TransferPlanningService().plan_queue(download_plan, priority=priority)
    print(_render_result(result))
    return _exit_code(result.status)


def run_provider_inspect(args: argparse.Namespace) -> int:
    provider = _resolve_provider(args.provider_kind)
    result = ProviderService().inspect_provider(provider)
    print(_render_result(result))
    return _exit_code(result.status)


def run_provider_health(args: argparse.Namespace) -> int:
    provider = _resolve_provider(args.provider_kind)
    result = ProviderService().check_provider_health(provider)
    print(_render_result(result))
    return _exit_code(result.status)


def run_quality_fake(args: argparse.Namespace) -> int:
    result = QualityService().evaluate_fake_quality(
        item_id=args.item_id,
        grade=args.grade,
    )
    print(_render_result(result))
    return _exit_code(result.status)


def run_routing_fake(args: argparse.Namespace) -> int:
    from noqlen_flux.quality import QualityFinding, QualityFindingKind, QualityFindingSeverity, QualityGrade, QualityResult

    grade = {
        "excellent": QualityGrade.EXCELLENT,
        "medium": QualityGrade.MEDIUM,
        "bad-objective": QualityGrade.BAD,
        "bad-heuristic": QualityGrade.BAD,
        "unknown": QualityGrade.UNKNOWN,
    }[args.scenario]

    findings: list[dict[str, Any]] = []
    if args.scenario == "bad-objective":
        findings = [
            {
                "code": "decode-fail",
                "message": "File fails decode validation.",
                "kind": "objective_failure",
                "severity": "error",
            }
        ]
    elif args.scenario == "bad-heuristic":
        findings = [
            {
                "code": "low-pass-suspicion",
                "message": "Low-pass filter suggests transcode.",
                "kind": "heuristic_warning",
                "severity": "warning",
            }
        ]
    elif args.scenario == "medium":
        findings = [
            {
                "code": "clipping-suspicion",
                "message": "Possible clipping detected.",
                "kind": "heuristic_warning",
                "severity": "warning",
            }
        ]

    quality_result = QualityService().evaluate_fake_quality(
        item_id=args.item_id,
        grade=grade.value,
        findings=findings,
    )
    qr = QualityResult(
        item_id=args.item_id,
        grade=grade,
        objective_failures=[
            QualityFinding(
                code="decode-fail",
                message="File fails decode validation.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        ] if args.scenario == "bad-objective" else [],
        heuristic_warnings=[
            QualityFinding(
                code="low-pass-suspicion",
                message="Low-pass filter suggests transcode.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
            )
        ] if args.scenario == "bad-heuristic" else [],
    )
    result = RoutingDecisionService().plan_routing([qr])
    print(_render_result(result))
    return _exit_code(result.status)


def run_staging_fake(args: argparse.Namespace) -> int:
    import uuid

    from noqlen_flux.routing import RoutingActionType, RoutingDecision, RoutingOutcome, RoutingPlan

    outcome_map = {
        "approved": RoutingOutcome.APPROVED,
        "quarantine": RoutingOutcome.QUARANTINE,
        "rejected": RoutingOutcome.REJECTED,
        "delete-eligible": RoutingOutcome.DELETE_ELIGIBLE,
        "review": RoutingOutcome.REVIEW,
    }
    outcome = outcome_map[args.outcome]

    decision = RoutingDecision(
        item_id=args.item_id,
        outcome=outcome,
        action_type=RoutingActionType.PLAN_ONLY,
    )

    routing_plan = RoutingPlan(
        plan_id=str(uuid.uuid4()),
        decisions=[decision],
    )

    result = StagingPlanService().plan_staging(routing_plan)
    print(_render_result(result))
    return _exit_code(result.status)


def run_staging_execute(args: argparse.Namespace) -> int:
    import uuid

    from noqlen_flux.config import config_from_env
    from noqlen_flux.routing import RoutingActionType, RoutingDecision, RoutingOutcome, RoutingPlan
    from noqlen_flux.services.staging import StagingPlanService
    from noqlen_flux.staging import (
        DEFAULT_STAGING_EXECUTION_POLICY,
        StagingActionType,
        StagingArea,
        StagingItem,
        StagingPlan,
    )

    dry_run = not args.apply
    config = config_from_env(args.workspace, dry_run=dry_run)

    scenario_area_map = {
        "fake-approved": StagingArea.APPROVED,
        "fake-quarantine": StagingArea.QUARANTINE,
        "fake-rejected": StagingArea.REJECTED,
        "fake-delete-eligible": StagingArea.DELETE_ELIGIBLE,
        "fake-review": StagingArea.REVIEW,
    }
    area = scenario_area_map[args.scenario]

    item_id = f"demo-{area.value}-item"
    source_relative = f"incoming/{item_id}.txt"
    target_relative = f"{area.value}/{item_id}.txt"

    if area == StagingArea.DELETE_ELIGIBLE:
        action_type = StagingActionType.MARK_DELETE_ELIGIBLE
    else:
        action_type = StagingActionType.COPY

    staging_item = StagingItem(
        item_id=item_id,
        routing_outcome=area.value,
        source_relative_path=source_relative,
        target_area=area,
        target_relative_path=target_relative,
        action_type=action_type,
        metadata={"scenario": args.scenario, "mode": "dry-run" if dry_run else "apply"},
    )

    staging_plan = StagingPlan(
        plan_id=str(uuid.uuid4()),
        items=[staging_item],
        metadata={"scenario": args.scenario},
    )

    if dry_run:
        result = StagingExecutionService().execute_staging_plan(staging_plan, config, dry_run=True)
    else:
        incoming_dir = config.workspace_root / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        demo_file = incoming_dir / f"{item_id}.txt"
        if not demo_file.exists():
            demo_file.write_text(f"Fake demo content for {item_id}\n")

        result = StagingExecutionService().execute_staging_plan(staging_plan, config, dry_run=False)

    print(_render_result(result))
    return _exit_code(result.status)


def run_fileops_demo(args: argparse.Namespace) -> int:
    import uuid

    from noqlen_flux.config import config_from_env
    from noqlen_flux.fileops import FileOperation, FileOperationPlan, FileOperationType
    from noqlen_flux.services import SafeFileOperationService

    dry_run = not args.apply
    config = config_from_env(args.workspace, dry_run=dry_run)

    operations = [
        FileOperation(
            operation_id=f"demo-mkdir-{uuid.uuid4().hex[:8]}",
            operation_type=FileOperationType.MKDIR,
            target_relative_path="incoming",
            reason="Demo: create incoming directory",
        ),
        FileOperation(
            operation_id=f"demo-mkdir-{uuid.uuid4().hex[:8]}",
            operation_type=FileOperationType.MKDIR,
            target_relative_path="approved",
            reason="Demo: create approved directory",
        ),
    ]

    plan = FileOperationPlan(
        plan_id=f"demo-plan-{uuid.uuid4().hex[:8]}",
        operations=operations,
    )

    result = SafeFileOperationService().execute_plan(plan, config, dry_run=dry_run)
    print(_render_result(result))
    return _exit_code(result.status)


def run_handoff_demo(args: argparse.Namespace) -> int:
    from noqlen_flux.config import config_from_env
    from noqlen_flux.services import HandoffManifestService

    dry_run = not args.apply
    config = config_from_env(args.workspace, dry_run=dry_run)
    service = HandoffManifestService()

    manifest = service.demo_manifest()

    if dry_run:
        result = service.preview_manifest(config, manifest)
    else:
        result = service.write_manifest(config, manifest, dry_run=False)

    print(_render_result(result))
    return _exit_code(result.status)


def run_handoff_validate(args: argparse.Namespace) -> int:
    from noqlen_flux.services import HandoffManifestService

    service = HandoffManifestService()
    manifest = service.demo_manifest()
    validation = service.validate_manifest(manifest)

    status_label = "valid" if validation.valid else "invalid"
    lines = [f"Noqlen Flux Core handoff: {status_label}"]
    lines.append(f"Validation: {len(validation.issues)} issue(s), {len(validation.warnings)} warning(s), {len(validation.errors)} error(s)")
    for issue in validation.issues:
        lines.append(f"  [{issue.severity}] {issue.code}: {issue.message}")
    print("\n".join(lines))
    return 0 if validation.valid else 1


def run_cleanup_plan_fake(args: argparse.Namespace) -> int:
    from noqlen_flux.cleanup import CleanupPolicy, build_fake_cleanup_candidates
    from noqlen_flux.services import CleanupPlanningService

    if getattr(args, "apply", False):
        result = CleanupPlanningService().result(
            status=Status.FAILED,
            error="Apply mode is not supported for cleanup planning. Cleanup is planned-only at this stage.",
        )
        print(_render_result(result))
        return 1

    candidates = build_fake_cleanup_candidates()

    policy_kwargs: dict[str, Any] = {
        "name": "cli_cleanup_v1",
        "version": "1",
        "description": "CLI cleanup planning policy.",
    }
    if getattr(args, "allow_delete_planning", False):
        policy_kwargs["allow_delete_planning"] = True
    if getattr(args, "min_age_days", None) is not None:
        policy_kwargs["min_age_days"] = args.min_age_days

    policy = CleanupPolicy(**policy_kwargs)

    result = CleanupPlanningService().plan_cleanup(candidates, policy=policy)
    print(_render_result(result))
    return _exit_code(result.status)


def _resolve_provider(kind: str):
    if kind == "fake":
        return FakeSearchProvider(
            _demo_candidates(),
            name="fake",
            kind=ProviderKind.FAKE,
            availability=ProviderAvailability.AVAILABLE,
        )
    if kind == "fake-transfer":
        return FakeTransferProvider(
            name="fake-transfer",
            kind=ProviderKind.FAKE,
            availability=ProviderAvailability.AVAILABLE,
        )
    raise ValueError(f"unknown provider kind: {kind}")


def _extract_download_plan(result: FluxResult):
    from noqlen_flux.downloads import DownloadItem, DownloadPlan

    summary = result.summary
    items = []
    for change in result.planned_changes:
        items.append(
            DownloadItem(
                item_id=change.metadata.get("item_id", ""),
                candidate_id=summary.get("candidate_id", ""),
                filename=change.metadata.get("filename", ""),
                target_relative_path=change.target,
            )
        )
    return DownloadPlan(
        plan_id=summary.get("plan_id", ""),
        request_id=summary.get("request_id", ""),
        candidate_id=summary.get("candidate_id", ""),
        intent=DownloadIntent(summary.get("intent", "track")),
        items=items,
        target_relative_root=summary.get("target_relative_root"),
        total_size_bytes=summary.get("total_size_bytes"),
        warnings=summary.get("warnings", []),
        blocked=summary.get("blocked", False),
        block_reasons=summary.get("block_reasons", []),
    )


def _render_result(result: FluxResult) -> str:
    lines = [f"Noqlen Flux Core {result.operation}: {result.status.value}"]
    lines.extend(step.message for step in result.steps if step.message)
    lines.extend(f"planned: {change.action} {change.target}" for change in result.planned_changes)
    lines.extend(f"applied: {change.action} {change.target}" for change in result.applied_changes)
    lines.extend(f"error: {error.code}: {error.message}" for error in result.errors)
    lines.extend(f"score: {score['candidate_id']} total={score['total']}/{score['max_score']} risk={score['risk']}" for score in result.summary.get("scores", []))
    blocked = result.summary.get("blocked")
    if blocked:
        lines.extend(f"blocked: {reason}" for reason in result.summary.get("block_reasons", []))
    item_count = result.summary.get("item_count")
    if item_count is not None:
        lines.append(f"items: {item_count}")
    queue_id = result.summary.get("queue_id")
    if queue_id is not None:
        lines.append(f"queue: {queue_id}")
    state = result.summary.get("state")
    if state is not None:
        lines.append(f"state: {state}")
    grade = result.summary.get("grade")
    if grade is not None:
        lines.append(f"grade: {grade}")
    confidence = result.summary.get("confidence")
    if confidence is not None:
        lines.append(f"confidence: {confidence}")
    decision_count = result.summary.get("decision_count")
    if decision_count is not None:
        lines.append(f"decisions: {decision_count}")
    approved_count = result.summary.get("approved_count")
    if approved_count is not None:
        lines.append(f"approved: {approved_count}")
    quarantine_count = result.summary.get("quarantine_count")
    if quarantine_count is not None:
        lines.append(f"quarantine: {quarantine_count}")
    rejected_count = result.summary.get("rejected_count")
    if rejected_count is not None:
        lines.append(f"rejected: {rejected_count}")
    review_count = result.summary.get("review_count")
    if review_count is not None:
        lines.append(f"review: {review_count}")
    if result.operation == "staging":
        staging_item_count = result.summary.get("item_count")
        if staging_item_count is not None:
            lines.append(f"staging items: {staging_item_count}")
        staging_approved = result.summary.get("approved_count")
        if staging_approved is not None:
            lines.append(f"staging approved: {staging_approved}")
        staging_quarantine = result.summary.get("quarantine_count")
        if staging_quarantine is not None:
            lines.append(f"staging quarantine: {staging_quarantine}")
        staging_rejected = result.summary.get("rejected_count")
        if staging_rejected is not None:
            lines.append(f"staging rejected: {staging_rejected}")
        staging_delete = result.summary.get("delete_eligible_count")
        if staging_delete is not None:
            lines.append(f"staging delete-eligible: {staging_delete}")
        staging_review = result.summary.get("review_count")
        if staging_review is not None:
            lines.append(f"staging review: {staging_review}")
    if result.operation == "fileops":
        op_count = result.summary.get("operation_count")
        if op_count is not None:
            lines.append(f"operations: {op_count}")
        mode = result.summary.get("mode")
        if mode is not None:
            lines.append(f"mode: {mode}")
        applied_count = result.summary.get("applied_count")
        if applied_count is not None:
            lines.append(f"applied: {applied_count}")
        planned_count = result.summary.get("planned_count")
        if planned_count is not None:
            lines.append(f"planned: {planned_count}")
        skipped_count = result.summary.get("skipped_count")
        if skipped_count is not None:
            lines.append(f"skipped: {skipped_count}")
        blocked_count = result.summary.get("blocked_count")
        if blocked_count is not None:
            lines.append(f"blocked: {blocked_count}")
        failed_count = result.summary.get("failed_count")
        if failed_count is not None:
            lines.append(f"failed: {failed_count}")
    if result.operation == "staging-execution":
        total_items = result.summary.get("total_items")
        if total_items is not None:
            lines.append(f"items: {total_items}")
        mode = result.summary.get("mode")
        if mode is not None:
            lines.append(f"mode: {mode}")
        applied_count = result.summary.get("applied_count")
        if applied_count is not None:
            lines.append(f"applied: {applied_count}")
        planned_count = result.summary.get("planned_count")
        if planned_count is not None:
            lines.append(f"planned: {planned_count}")
        skipped_count = result.summary.get("skipped_count")
        if skipped_count is not None:
            lines.append(f"skipped: {skipped_count}")
        blocked_count = result.summary.get("blocked_count")
        if blocked_count is not None:
            lines.append(f"blocked: {blocked_count}")
        failed_count = result.summary.get("failed_count")
        if failed_count is not None:
            lines.append(f"failed: {failed_count}")
    if result.operation == "handoff":
        handoff_version = result.summary.get("handoff_version")
        if handoff_version is not None:
            lines.append(f"handoff_version: {handoff_version}")
        manifest_filename = result.summary.get("manifest_filename")
        if manifest_filename is not None:
            lines.append(f"manifest: {manifest_filename}")
        dry_run_flag = result.summary.get("dry_run")
        if dry_run_flag is not None:
            lines.append(f"dry_run: {dry_run_flag}")
        applied_changes = result.summary.get("applied_changes")
        if applied_changes is not None:
            lines.append(f"applied: {applied_changes}")
        planned_changes = result.summary.get("planned_changes")
        if planned_changes is not None:
            lines.append(f"planned: {planned_changes}")
    if result.operation == "cleanup":
        candidate_count = result.summary.get("candidate_count")
        if candidate_count is not None:
            lines.append(f"candidates: {candidate_count}")
        keep_count = result.summary.get("keep_count")
        if keep_count is not None:
            lines.append(f"keep: {keep_count}")
        review_count = result.summary.get("review_count")
        if review_count is not None:
            lines.append(f"review: {review_count}")
        mark_delete = result.summary.get("mark_delete_eligible_count")
        if mark_delete is not None:
            lines.append(f"mark-delete-eligible: {mark_delete}")
        plan_delete = result.summary.get("plan_delete_count")
        if plan_delete is not None:
            lines.append(f"plan-delete: {plan_delete}")
        none_count = result.summary.get("none_count")
        if none_count is not None:
            lines.append(f"none: {none_count}")
        total_bytes = result.summary.get("total_planned_bytes")
        if total_bytes is not None:
            lines.append(f"planned-bytes: {total_bytes}")
    return "\n".join(lines)


def _scoring_service(args: argparse.Namespace) -> CandidateScoringService | None:
    if getattr(args, "score", False):
        return CandidateScoringService()
    return None


def _demo_fake_provider() -> FakeSearchProvider:
    return FakeSearchProvider(_demo_candidates())


def _demo_candidates() -> list[SearchCandidate]:
    return [
        SearchCandidate(
            candidate_id="fake-track-example",
            provider="fake",
            username="fake-user",
            directory="Example Artist/Example Track",
            artist="Example Artist",
            title="Example Track",
            raw_score=1.0,
            files=[CandidateFile(filename="Example Track.flac", extension="flac", size_bytes=12345678)],
        ),
        SearchCandidate(
            candidate_id="fake-album-example",
            provider="fake",
            username="fake-user",
            directory="Example Artist/Example Album",
            artist="Example Artist",
            album="Example Album",
            raw_score=1.0,
            files=[
                CandidateFile(filename="01 Example Album Intro.flac", extension="flac", size_bytes=1111111),
                CandidateFile(filename="02 Example Album Track.flac", extension="flac", size_bytes=2222222),
            ],
        ),
    ]


def _exit_code(status: Status) -> int:
    if status == Status.FAILED:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
