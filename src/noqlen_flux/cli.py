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
from .services import CandidateScoringService, DoctorService, DownloadPlanningService, MusicLabService, ProviderService, QualityService, ReportService, SearchService, TransferPlanningService, WorkspaceService
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
