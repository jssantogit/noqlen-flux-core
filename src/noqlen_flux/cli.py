from __future__ import annotations

import argparse
import os
from typing import Any

from . import __version__
from .config import config_from_env
from .downloads import DownloadConstraint, DownloadIntent, DownloadRequest
from .providers.fake import FakeSearchProvider
from .providers.fake_queue_execution import FakeQueueExecutionProvider
from .providers.fake_transfer import FakeTransferProvider
from .providers.status import ProviderAvailability, ProviderKind
from .reports import ReportFormat
from .results import FluxError, FluxResult, Status
from .scoring import CandidateScore
from .search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from .services import ArtifactRegistrationService, CandidateScoringService, CleanupPlanningService, DoctorService, DownloadPlanningService, HandoffManifestService, MusicLabService, ProviderService, QualityService, ReportService, RoutingDecisionService, SafeFileOperationService, SearchService, StagingExecutionService, StagingPlanService, TransferExecutionService, TransferPlanningService, WorkspaceService
from .transfers import TransferExecutionMode, TransferPriority


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

    search_slskd = search_subparsers.add_parser("slskd", help="Search via slskd provider (offline by default)")
    search_slskd_subparsers = search_slskd.add_subparsers(dest="search_kind")

    search_slskd_track = search_slskd_subparsers.add_parser("track", help="Search a track via slskd")
    search_slskd_track.add_argument("--artist", required=True, help="Artist name")
    search_slskd_track.add_argument("--title", required=True, help="Track title")
    search_slskd_track.add_argument("--limit", type=int, help="Optional positive result limit")
    search_slskd_track.add_argument("--score", action="store_true", help="Include explainable pre-download scoring")
    search_slskd_track.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    search_slskd_track.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    search_slskd_track.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    search_slskd_track.add_argument("--allow-network", action="store_true", help="Allow network access for real search")
    search_slskd_track.add_argument("--timeout", type=int, help="HTTP timeout in seconds (default 5)")
    search_slskd_track.add_argument("--max-polls", type=int, help="Maximum poll attempts (default 10)")
    search_slskd_track.set_defaults(func=run_search_slskd_track)

    search_slskd_album = search_slskd_subparsers.add_parser("album", help="Search an album via slskd")
    search_slskd_album.add_argument("--artist", required=True, help="Artist name")
    search_slskd_album.add_argument("--album", required=True, help="Album title")
    search_slskd_album.add_argument("--limit", type=int, help="Optional positive result limit")
    search_slskd_album.add_argument("--score", action="store_true", help="Include explainable pre-download scoring")
    search_slskd_album.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    search_slskd_album.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    search_slskd_album.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    search_slskd_album.add_argument("--allow-network", action="store_true", help="Allow network access for real search")
    search_slskd_album.add_argument("--timeout", type=int, help="HTTP timeout in seconds (default 5)")
    search_slskd_album.add_argument("--max-polls", type=int, help="Maximum poll attempts (default 10)")
    search_slskd_album.set_defaults(func=run_search_slskd_album)

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

    musiclab_scoring = musiclab_subparsers.add_parser("scoring", help="Run scoring calibration in MusicLab")
    musiclab_scoring_subparsers = musiclab_scoring.add_subparsers(dest="musiclab_scoring_command")
    musiclab_scoring_run = musiclab_scoring_subparsers.add_parser("run", help="Run scoring calibration against default fake dataset")
    musiclab_scoring_run.set_defaults(func=run_musiclab_scoring_run)

    musiclab_quality = musiclab_subparsers.add_parser("quality", help="Run quality calibration in MusicLab")
    musiclab_quality_subparsers = musiclab_quality.add_subparsers(dest="musiclab_quality_command")
    musiclab_quality_run = musiclab_quality_subparsers.add_parser("run", help="Run quality calibration against default fake dataset")
    musiclab_quality_run.set_defaults(func=run_musiclab_quality_run)

    musiclab_scenario = musiclab_subparsers.add_parser("scenario", help="Run real-world scenario engine")
    musiclab_scenario_subparsers = musiclab_scenario.add_subparsers(dest="musiclab_scenario_command")

    musiclab_scenario_list = musiclab_scenario_subparsers.add_parser("list", help="List all available MusicLab scenarios")
    musiclab_scenario_list.set_defaults(func=run_musiclab_scenario_list)

    musiclab_scenario_run = musiclab_scenario_subparsers.add_parser("run", help="Run a single MusicLab scenario")
    musiclab_scenario_run.add_argument("--scenario", required=True, help="Scenario ID to run")
    musiclab_scenario_run.add_argument("--workspace", required=True, help="Workspace root path")
    musiclab_scenario_run.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode (default)")
    musiclab_scenario_run.set_defaults(func=run_musiclab_scenario_run)

    musiclab_scenario_run_pack = musiclab_scenario_subparsers.add_parser("run-pack", help="Run a MusicLab scenario pack")
    musiclab_scenario_run_pack.add_argument("--pack", required=True, help="Pack ID to run")
    musiclab_scenario_run_pack.add_argument("--workspace", required=True, help="Workspace root path")
    musiclab_scenario_run_pack.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode (default)")
    musiclab_scenario_run_pack.set_defaults(func=run_musiclab_scenario_run_pack)

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

    download_plan_slskd = download_plan_subparsers.add_parser("slskd", help="Plan a download from slskd search results (offline by default)")
    download_plan_slskd_subparsers = download_plan_slskd.add_subparsers(dest="download_plan_kind")

    download_plan_slskd_track = download_plan_slskd_subparsers.add_parser("track", help="Plan a slskd track download")
    download_plan_slskd_track.add_argument("--artist", required=True, help="Artist name")
    download_plan_slskd_track.add_argument("--title", required=True, help="Track title")
    download_plan_slskd_track.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    download_plan_slskd_track.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    download_plan_slskd_track.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    download_plan_slskd_track.add_argument("--allow-network", action="store_true", help="Allow network access for real search")
    download_plan_slskd_track.add_argument("--timeout", type=int, help="HTTP timeout in seconds (default 5)")
    download_plan_slskd_track.add_argument("--max-polls", type=int, help="Maximum poll attempts (default 10)")
    download_plan_slskd_track.add_argument("--score", action="store_true", help="Include pre-download scoring")
    download_plan_slskd_track.add_argument("--candidate-index", type=int, default=0, help="Select candidate by index (default 0)")
    download_plan_slskd_track.add_argument("--score-min", type=float, help="Minimum score required to plan")
    download_plan_slskd_track.add_argument("--max-files", type=int, help="Maximum files allowed")
    download_plan_slskd_track.add_argument("--max-total-bytes", type=int, help="Maximum total bytes allowed")
    download_plan_slskd_track.add_argument("--allow-locked", action="store_true", help="Allow locked files")
    download_plan_slskd_track.add_argument("--allowed-extension", action="append", help="Allowed file extension (repeatable)")
    download_plan_slskd_track.set_defaults(func=run_download_plan_slskd_track)

    download_plan_slskd_album = download_plan_slskd_subparsers.add_parser("album", help="Plan a slskd album download")
    download_plan_slskd_album.add_argument("--artist", required=True, help="Artist name")
    download_plan_slskd_album.add_argument("--album", required=True, help="Album title")
    download_plan_slskd_album.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    download_plan_slskd_album.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    download_plan_slskd_album.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    download_plan_slskd_album.add_argument("--allow-network", action="store_true", help="Allow network access for real search")
    download_plan_slskd_album.add_argument("--timeout", type=int, help="HTTP timeout in seconds (default 5)")
    download_plan_slskd_album.add_argument("--max-polls", type=int, help="Maximum poll attempts (default 10)")
    download_plan_slskd_album.add_argument("--score", action="store_true", help="Include pre-download scoring")
    download_plan_slskd_album.add_argument("--candidate-index", type=int, default=0, help="Select candidate by index (default 0)")
    download_plan_slskd_album.add_argument("--score-min", type=float, help="Minimum score required to plan")
    download_plan_slskd_album.add_argument("--max-files", type=int, help="Maximum files allowed")
    download_plan_slskd_album.add_argument("--max-total-bytes", type=int, help="Maximum total bytes allowed")
    download_plan_slskd_album.add_argument("--allow-locked", action="store_true", help="Allow locked files")
    download_plan_slskd_album.add_argument("--allowed-extension", action="append", help="Allowed file extension (repeatable)")
    download_plan_slskd_album.set_defaults(func=run_download_plan_slskd_album)

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

    transfer_plan_slskd = transfer_plan_subparsers.add_parser("slskd", help="Plan a transfer from slskd search results (offline by default)")
    transfer_plan_slskd_subparsers = transfer_plan_slskd.add_subparsers(dest="transfer_plan_kind")

    transfer_plan_slskd_track = transfer_plan_slskd_subparsers.add_parser("track", help="Plan a slskd track transfer")
    transfer_plan_slskd_track.add_argument("--artist", required=True, help="Artist name")
    transfer_plan_slskd_track.add_argument("--title", required=True, help="Track title")
    transfer_plan_slskd_track.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    transfer_plan_slskd_track.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    transfer_plan_slskd_track.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    transfer_plan_slskd_track.add_argument("--allow-network", action="store_true", help="Allow network access for real search")
    transfer_plan_slskd_track.add_argument("--timeout", type=int, help="HTTP timeout in seconds (default 5)")
    transfer_plan_slskd_track.add_argument("--max-polls", type=int, help="Maximum poll attempts (default 10)")
    transfer_plan_slskd_track.add_argument("--score", action="store_true", help="Include pre-download scoring")
    transfer_plan_slskd_track.add_argument("--candidate-index", type=int, default=0, help="Select candidate by index (default 0)")
    transfer_plan_slskd_track.add_argument("--score-min", type=float, help="Minimum score required to plan")
    transfer_plan_slskd_track.add_argument("--max-files", type=int, help="Maximum files allowed")
    transfer_plan_slskd_track.add_argument("--max-total-bytes", type=int, help="Maximum total bytes allowed")
    transfer_plan_slskd_track.add_argument("--allow-locked", action="store_true", help="Allow locked files")
    transfer_plan_slskd_track.add_argument("--allowed-extension", action="append", help="Allowed file extension (repeatable)")
    transfer_plan_slskd_track.add_argument("--priority", choices=[item.value for item in TransferPriority], default=TransferPriority.NORMAL.value)
    transfer_plan_slskd_track.set_defaults(func=run_transfer_plan_slskd_track)

    transfer_plan_slskd_album = transfer_plan_slskd_subparsers.add_parser("album", help="Plan a slskd album transfer")
    transfer_plan_slskd_album.add_argument("--artist", required=True, help="Artist name")
    transfer_plan_slskd_album.add_argument("--album", required=True, help="Album title")
    transfer_plan_slskd_album.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    transfer_plan_slskd_album.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    transfer_plan_slskd_album.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    transfer_plan_slskd_album.add_argument("--allow-network", action="store_true", help="Allow network access for real search")
    transfer_plan_slskd_album.add_argument("--timeout", type=int, help="HTTP timeout in seconds (default 5)")
    transfer_plan_slskd_album.add_argument("--max-polls", type=int, help="Maximum poll attempts (default 10)")
    transfer_plan_slskd_album.add_argument("--score", action="store_true", help="Include pre-download scoring")
    transfer_plan_slskd_album.add_argument("--candidate-index", type=int, default=0, help="Select candidate by index (default 0)")
    transfer_plan_slskd_album.add_argument("--score-min", type=float, help="Minimum score required to plan")
    transfer_plan_slskd_album.add_argument("--max-files", type=int, help="Maximum files allowed")
    transfer_plan_slskd_album.add_argument("--max-total-bytes", type=int, help="Maximum total bytes allowed")
    transfer_plan_slskd_album.add_argument("--allow-locked", action="store_true", help="Allow locked files")
    transfer_plan_slskd_album.add_argument("--allowed-extension", action="append", help="Allowed file extension (repeatable)")
    transfer_plan_slskd_album.add_argument("--priority", choices=[item.value for item in TransferPriority], default=TransferPriority.NORMAL.value)
    transfer_plan_slskd_album.set_defaults(func=run_transfer_plan_slskd_album)

    transfer_execute = transfer_subparsers.add_parser("execute", help="Execute a planned transfer queue via provider")
    transfer_execute_subparsers = transfer_execute.add_subparsers(dest="transfer_execute_provider")

    transfer_execute_fake = transfer_execute_subparsers.add_parser("fake", help="Execute a fake transfer queue")
    transfer_execute_fake.add_argument("--artist", required=True, help="Artist name")
    transfer_execute_fake.add_argument("--title", required=True, help="Track title")
    transfer_execute_fake.add_argument("--score", action="store_true", help="Include pre-download scoring")
    transfer_execute_fake.add_argument("--priority", choices=[item.value for item in TransferPriority], default=TransferPriority.NORMAL.value)
    transfer_execute_mode = transfer_execute_fake.add_mutually_exclusive_group()
    transfer_execute_mode.add_argument("--dry-run", action="store_true", help="Plan execution without submitting")
    transfer_execute_mode.add_argument("--apply", action="store_true", help="Submit to fake provider (in-memory)")
    transfer_execute_fake.set_defaults(func=run_transfer_execute_fake)

    transfer_execute_slskd = transfer_execute_subparsers.add_parser("slskd", help="Execute slskd queue submission (offline by default, real network opt-in)")
    transfer_execute_slskd.add_argument("--artist", required=True, help="Artist name")
    transfer_execute_slskd.add_argument("--title", required=True, help="Track title")
    transfer_execute_slskd.add_argument("--score", action="store_true", help="Include pre-download scoring")
    transfer_execute_slskd.add_argument("--priority", choices=[item.value for item in TransferPriority], default=TransferPriority.NORMAL.value)
    transfer_execute_slskd.add_argument("--locked", action="store_true", help="Simulate locked file scenario")
    transfer_execute_slskd.add_argument("--duplicate", action="store_true", help="Simulate duplicate scenario")
    transfer_execute_slskd.add_argument("--provider-error", action="store_true", help="Simulate provider error scenario")
    transfer_execute_slskd.add_argument("--unavailable", action="store_true", help="Simulate unavailable scenario")
    transfer_execute_slskd.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    transfer_execute_slskd.add_argument("--allow-network", action="store_true", help="Allow real network access for queue submission (opt-in)")
    transfer_execute_slskd.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    transfer_execute_slskd.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    transfer_execute_slskd_mode = transfer_execute_slskd.add_mutually_exclusive_group()
    transfer_execute_slskd_mode.add_argument("--dry-run", action="store_true", help="Preview execution without submitting (default)")
    transfer_execute_slskd_mode.add_argument("--apply", action="store_true", help="Submit queue to provider")
    transfer_execute_slskd.set_defaults(func=run_transfer_execute_slskd)

    transfer_status = transfer_subparsers.add_parser("status", help="Poll transfer status via provider")
    transfer_status_subparsers = transfer_status.add_subparsers(dest="transfer_status_provider")

    transfer_status_slskd = transfer_status_subparsers.add_parser("slskd", help="Poll slskd transfer status (offline by default, real network opt-in)")
    transfer_status_slskd.add_argument("--offline", action="store_true", help="Force offline mode (default)")
    transfer_status_slskd.add_argument("--allow-network", action="store_true", help="Allow real network access for transfer status polling (opt-in)")
    transfer_status_slskd.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    transfer_status_slskd.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    transfer_status_slskd.add_argument("--transfer-id", required=True, help="Transfer identifier to poll")
    transfer_status_slskd.add_argument("--queue-item-id", help="Optional queue item identifier")
    transfer_status_slskd.set_defaults(func=run_transfer_status_slskd)

    provider = subparsers.add_parser("provider", help="Inspect provider health and capabilities")
    provider_subparsers = provider.add_subparsers(dest="provider_command")

    provider_inspect = provider_subparsers.add_parser("inspect", help="Inspect provider health and capabilities")
    provider_inspect.add_argument("provider_kind", choices=["fake", "fake-transfer", "slskd"], help="Provider to inspect")
    provider_inspect.set_defaults(func=run_provider_inspect)

    provider_health = provider_subparsers.add_parser("health", help="Check provider health status")
    provider_health.add_argument("provider_kind", choices=["fake", "fake-transfer", "slskd"], help="Provider to check")
    provider_health.add_argument("--offline", action="store_true", help="Check health without network access (default for slskd)")
    provider_health.add_argument("--url", help="Slskd base URL (requires --allow-network)")
    provider_health.add_argument("--api-key-env", help="Environment variable name containing the slskd API key")
    provider_health.add_argument("--allow-network", action="store_true", help="Allow network access for slskd health check")
    provider_health.set_defaults(func=run_provider_health)

    quality = subparsers.add_parser("quality", help="Inspect post-download quality (contracts-only, no real audio analysis)")
    quality_subparsers = quality.add_subparsers(dest="quality_command")

    quality_fake = quality_subparsers.add_parser("fake", help="Generate a fake quality result for testing")
    quality_fake.add_argument("grade", choices=["excellent", "medium", "bad", "unknown"], help="Fake quality grade to simulate")
    quality_fake.add_argument("--item-id", default="fake-item-1", help="Optional item id")
    quality_fake.set_defaults(func=run_quality_fake)

    quality_inspect = quality_subparsers.add_parser("inspect", help="Inspect a file for quality using probe backend")
    quality_inspect.add_argument("--workspace", required=True, help="Workspace root path")
    quality_inspect.add_argument("--path", required=True, help="Relative path to file within workspace")
    quality_inspect.add_argument("--item-id", help="Optional item id")
    quality_inspect_mode = quality_inspect.add_mutually_exclusive_group()
    quality_inspect_mode.add_argument("--dry-run", action="store_true", help="Plan inspection without executing (default)")
    quality_inspect_mode.add_argument("--apply", action="store_true", help="Execute quality inspection and write report to workspace/reports")
    quality_inspect.set_defaults(func=run_quality_inspect)

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

    staging_apply = staging_subparsers.add_parser("apply", help="Apply staging plan within workspace boundary with safety policy")
    staging_apply.add_argument("scope", choices=["fake"], help="Provider scope (fake for testing)")
    staging_apply.add_argument("outcome", choices=["approved", "quarantine", "rejected", "delete-eligible", "review"], help="Routing outcome to stage and apply")
    staging_apply.add_argument("--workspace", required=True, help="Workspace root path")
    staging_apply.add_argument("--item-id", default=None, help="Optional item id")
    staging_apply_mode = staging_apply.add_mutually_exclusive_group()
    staging_apply_mode.add_argument("--dry-run", action="store_true", help="Plan staging apply without altering filesystem (default)")
    staging_apply_mode.add_argument("--apply", action="store_true", help="Execute staging apply within workspace")
    staging_apply.set_defaults(func=run_staging_apply)

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

    handoff_validate = handoff_subparsers.add_parser("validate", help="Validate a handoff manifest (demo or file-based)")
    handoff_validate.add_argument("--workspace", required=True, help="Workspace root path")
    handoff_validate_source = handoff_validate.add_mutually_exclusive_group(required=True)
    handoff_validate_source.add_argument("--demo", action="store_true", help="Validate a demo manifest")
    handoff_validate_source.add_argument("--manifest", help="Relative path to an existing manifest file inside workspace")
    handoff_validate.set_defaults(func=run_handoff_validate)

    handoff_apply = handoff_subparsers.add_parser("apply", help="Apply handoff manifest for Forge bridge (file-based, controlled)")
    handoff_apply.add_argument("--workspace", required=True, help="Workspace root path")
    handoff_apply.add_argument("--manifest", required=True, help="Relative path to manifest file inside workspace (e.g. manifests/handoff-xxx.json)")
    handoff_apply_mode = handoff_apply.add_mutually_exclusive_group(required=True)
    handoff_apply_mode.add_argument("--dry-run", action="store_true", help="Preview apply without executing")
    handoff_apply_mode.add_argument("--apply", action="store_true", help="Execute handoff apply bridge")
    handoff_apply.set_defaults(func=run_handoff_apply)

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


def run_search_slskd_track(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title, limit=args.limit)
    provider = _resolve_slskd_provider(args)
    result = SearchService().search(query, provider, _scoring_service(args))
    print(_render_result(result))
    return _exit_code(result.status)


def run_search_slskd_album(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.ALBUM, artist=args.artist, album=args.album, limit=args.limit)
    provider = _resolve_slskd_provider(args)
    result = SearchService().search(query, provider, _scoring_service(args))
    print(_render_result(result))
    return _exit_code(result.status)


def _resolve_slskd_provider(args: argparse.Namespace):
    """Instantiate SlskdProvider for CLI search commands.

    Network access is disabled by default. --allow-network is required
    for real search. API key must come from an environment variable.
    """
    from noqlen_flux.providers.slskd import SlskdProvider, SlskdProviderConfig

    allow_network = getattr(args, "allow_network", False)
    url = getattr(args, "url", None)
    api_key_env = getattr(args, "api_key_env", None)
    api_key = os.environ.get(api_key_env) if api_key_env else None
    timeout = getattr(args, "timeout", None) or 5
    max_polls = getattr(args, "max_polls", None) or 10

    config = SlskdProviderConfig(
        base_url=url,
        api_key=api_key,
        allow_network=allow_network,
        timeout_seconds=timeout,
        max_poll_attempts=max_polls,
    )
    return SlskdProvider(config=config)


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


def run_musiclab_scoring_run(_args: argparse.Namespace) -> int:
    from noqlen_flux.services import MusicLabScoringService

    result = MusicLabScoringService().run_calibration()
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_quality_run(_args: argparse.Namespace) -> int:
    from noqlen_flux.services import MusicLabQualityService

    result = MusicLabQualityService().run_calibration()
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_scenario_list(_args: argparse.Namespace) -> int:
    from noqlen_flux.services import MusicLabScenarioRunnerService

    result = MusicLabScenarioRunnerService().list_scenarios()
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_scenario_run(args: argparse.Namespace) -> int:
    from noqlen_flux.services import MusicLabScenarioRunnerService

    result = MusicLabScenarioRunnerService().run_scenario(
        scenario_id=args.scenario,
        workspace_root=args.workspace,
        dry_run=args.dry_run,
    )
    print(_render_result(result))
    return _exit_code(result.status)


def run_musiclab_scenario_run_pack(args: argparse.Namespace) -> int:
    from noqlen_flux.services import MusicLabScenarioRunnerService

    result = MusicLabScenarioRunnerService().run_pack(
        pack_id=args.pack,
        workspace_root=args.workspace,
        dry_run=args.dry_run,
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


def run_download_plan_slskd_track(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title)
    provider = _resolve_slskd_provider(args)
    search_result = SearchService().search(query, provider, _scoring_service(args))
    if search_result.status == Status.FAILED:
        print(_render_result(search_result))
        return 1
    candidates = search_result.summary.get("candidates", [])
    if not candidates:
        print(_render_result(search_result))
        print(_render_result(FluxResult(
            operation="download-planning",
            status=Status.FAILED,
            errors=[FluxError(code="no-candidates", message="no candidates found from slskd search")],
        )))
        return 1
    candidate_index = getattr(args, "candidate_index", 0) or 0
    if candidate_index < 0 or candidate_index >= len(candidates):
        print(_render_result(FluxResult(
            operation="download-planning",
            status=Status.FAILED,
            errors=[FluxError(code="candidate-index-out-of-range", message=f"candidate index {candidate_index} out of range (0-{len(candidates) - 1})")],
        )))
        return 1
    candidate_data = candidates[candidate_index]
    candidate = _candidate_from_dict(candidate_data)
    score = None
    if args.score:
        scores = search_result.summary.get("scores", [])
        if candidate_index < len(scores):
            score = _score_from_dict(scores[candidate_index])
    allowed_ext = getattr(args, "allowed_extension", None) or None
    allowed_extensions = set(allowed_ext) if allowed_ext else None
    constraints = DownloadConstraint(
        allow_locked=getattr(args, "allow_locked", False),
        require_score_min=getattr(args, "score_min", None),
        max_files=getattr(args, "max_files", None),
        max_total_bytes=getattr(args, "max_total_bytes", None),
        allowed_extensions=allowed_extensions,
    )
    request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.TRACK,
        query=f"{args.artist} - {args.title}",
        score=score,
        constraints=constraints,
    )
    result = DownloadPlanningService().plan_download(request)
    print(_render_result(search_result))
    print(_render_result(result))
    return _exit_code(result.status)


def run_download_plan_slskd_album(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.ALBUM, artist=args.artist, album=args.album)
    provider = _resolve_slskd_provider(args)
    search_result = SearchService().search(query, provider, _scoring_service(args))
    if search_result.status == Status.FAILED:
        print(_render_result(search_result))
        return 1
    candidates = search_result.summary.get("candidates", [])
    if not candidates:
        print(_render_result(search_result))
        print(_render_result(FluxResult(
            operation="download-planning",
            status=Status.FAILED,
            errors=[FluxError(code="no-candidates", message="no candidates found from slskd search")],
        )))
        return 1
    candidate_index = getattr(args, "candidate_index", 0) or 0
    if candidate_index < 0 or candidate_index >= len(candidates):
        print(_render_result(FluxResult(
            operation="download-planning",
            status=Status.FAILED,
            errors=[FluxError(code="candidate-index-out-of-range", message=f"candidate index {candidate_index} out of range (0-{len(candidates) - 1})")],
        )))
        return 1
    candidate_data = candidates[candidate_index]
    candidate = _candidate_from_dict(candidate_data)
    score = None
    if args.score:
        scores = search_result.summary.get("scores", [])
        if candidate_index < len(scores):
            score = _score_from_dict(scores[candidate_index])
    allowed_ext = getattr(args, "allowed_extension", None) or None
    allowed_extensions = set(allowed_ext) if allowed_ext else None
    constraints = DownloadConstraint(
        allow_locked=getattr(args, "allow_locked", False),
        require_score_min=getattr(args, "score_min", None),
        max_files=getattr(args, "max_files", None),
        max_total_bytes=getattr(args, "max_total_bytes", None),
        allowed_extensions=allowed_extensions,
    )
    request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.ALBUM,
        query=f"{args.artist} - {args.album}",
        score=score,
        constraints=constraints,
    )
    result = DownloadPlanningService().plan_download(request)
    print(_render_result(search_result))
    print(_render_result(result))
    return _exit_code(result.status)


def _candidate_from_dict(data: dict[str, Any]) -> SearchCandidate:
    files = [
        CandidateFile(
            filename=f["filename"],
            size_bytes=f.get("size_bytes"),
            declared_bitrate=f.get("declared_bitrate"),
            extension=f.get("extension"),
            duration_seconds=f.get("duration_seconds"),
            locked=f.get("locked", False),
            metadata=f.get("metadata", {}),
        )
        for f in data.get("files", [])
    ]
    return SearchCandidate(
        candidate_id=data["candidate_id"],
        provider=data.get("provider", "slskd"),
        username=data.get("username"),
        directory=data.get("directory"),
        artist=data.get("artist"),
        title=data.get("title"),
        album=data.get("album"),
        files=files,
        warnings=data.get("warnings", []),
        metadata=data.get("metadata", {}),
    )


def _score_from_dict(data: dict[str, Any]) -> CandidateScore:
    from noqlen_flux.scoring import CandidateRisk, ScoreComponent, ScorePenalty, ScoreReason

    components = [
        ScoreComponent(
            name=c["name"],
            score=c["score"],
            max_score=c["max_score"],
            reasons=[ScoreReason(**r) for r in c.get("reasons", [])],
            penalties=[ScorePenalty(**p) for p in c.get("penalties", [])],
        )
        for c in data.get("components", [])
    ]
    reasons = [ScoreReason(**r) for r in data.get("reasons", [])]
    penalties = [ScorePenalty(**p) for p in data.get("penalties", [])]
    return CandidateScore(
        candidate_id=data["candidate_id"],
        total=data["total"],
        max_score=data["max_score"],
        risk=CandidateRisk(data.get("risk", "low")),
        confidence=data.get("confidence", 0.0),
        components=components,
        reasons=reasons,
        penalties=penalties,
        warnings=data.get("warnings", []),
        metadata=data.get("metadata", {}),
    )


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


def run_transfer_plan_slskd_track(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title)
    provider = _resolve_slskd_provider(args)
    search_result = SearchService().search(query, provider, _scoring_service(args))
    if search_result.status == Status.FAILED:
        print(_render_result(search_result))
        return 1
    candidates = search_result.summary.get("candidates", [])
    if not candidates:
        print(_render_result(search_result))
        print(_render_result(FluxResult(
            operation="transfer-planning",
            status=Status.FAILED,
            errors=[FluxError(code="no-candidates", message="no candidates found from slskd search")],
        )))
        return 1
    candidate_index = getattr(args, "candidate_index", 0) or 0
    if candidate_index < 0 or candidate_index >= len(candidates):
        print(_render_result(FluxResult(
            operation="transfer-planning",
            status=Status.FAILED,
            errors=[FluxError(code="candidate-index-out-of-range", message=f"candidate index {candidate_index} out of range (0-{len(candidates) - 1})")],
        )))
        return 1
    candidate_data = candidates[candidate_index]
    candidate = _candidate_from_dict(candidate_data)
    score = None
    if args.score:
        scores = search_result.summary.get("scores", [])
        if candidate_index < len(scores):
            score = _score_from_dict(scores[candidate_index])
    allowed_ext = getattr(args, "allowed_extension", None) or None
    allowed_extensions = set(allowed_ext) if allowed_ext else None
    constraints = DownloadConstraint(
        allow_locked=getattr(args, "allow_locked", False),
        require_score_min=getattr(args, "score_min", None),
        max_files=getattr(args, "max_files", None),
        max_total_bytes=getattr(args, "max_total_bytes", None),
        allowed_extensions=allowed_extensions,
    )
    download_request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.TRACK,
        query=f"{args.artist} - {args.title}",
        score=score,
        constraints=constraints,
    )
    download_plan_result = DownloadPlanningService().plan_download(download_request)
    if download_plan_result.status == Status.FAILED:
        print(_render_result(search_result))
        print(_render_result(download_plan_result))
        return 1
    download_plan = _extract_download_plan(download_plan_result)
    priority = TransferPriority(args.priority)
    transfer_result = TransferPlanningService().plan_queue(download_plan, priority=priority)
    print(_render_result(search_result))
    print(_render_result(download_plan_result))
    print(_render_result(transfer_result))
    return _exit_code(transfer_result.status)


def run_transfer_plan_slskd_album(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.ALBUM, artist=args.artist, album=args.album)
    provider = _resolve_slskd_provider(args)
    search_result = SearchService().search(query, provider, _scoring_service(args))
    if search_result.status == Status.FAILED:
        print(_render_result(search_result))
        return 1
    candidates = search_result.summary.get("candidates", [])
    if not candidates:
        print(_render_result(search_result))
        print(_render_result(FluxResult(
            operation="transfer-planning",
            status=Status.FAILED,
            errors=[FluxError(code="no-candidates", message="no candidates found from slskd search")],
        )))
        return 1
    candidate_index = getattr(args, "candidate_index", 0) or 0
    if candidate_index < 0 or candidate_index >= len(candidates):
        print(_render_result(FluxResult(
            operation="transfer-planning",
            status=Status.FAILED,
            errors=[FluxError(code="candidate-index-out-of-range", message=f"candidate index {candidate_index} out of range (0-{len(candidates) - 1})")],
        )))
        return 1
    candidate_data = candidates[candidate_index]
    candidate = _candidate_from_dict(candidate_data)
    score = None
    if args.score:
        scores = search_result.summary.get("scores", [])
        if candidate_index < len(scores):
            score = _score_from_dict(scores[candidate_index])
    allowed_ext = getattr(args, "allowed_extension", None) or None
    allowed_extensions = set(allowed_ext) if allowed_ext else None
    constraints = DownloadConstraint(
        allow_locked=getattr(args, "allow_locked", False),
        require_score_min=getattr(args, "score_min", None),
        max_files=getattr(args, "max_files", None),
        max_total_bytes=getattr(args, "max_total_bytes", None),
        allowed_extensions=allowed_extensions,
    )
    download_request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.ALBUM,
        query=f"{args.artist} - {args.album}",
        score=score,
        constraints=constraints,
    )
    download_plan_result = DownloadPlanningService().plan_download(download_request)
    if download_plan_result.status == Status.FAILED:
        print(_render_result(search_result))
        print(_render_result(download_plan_result))
        return 1
    download_plan = _extract_download_plan(download_plan_result)
    priority = TransferPriority(args.priority)
    transfer_result = TransferPlanningService().plan_queue(download_plan, priority=priority)
    print(_render_result(search_result))
    print(_render_result(download_plan_result))
    print(_render_result(transfer_result))
    return _exit_code(transfer_result.status)


def run_transfer_execute_fake(args: argparse.Namespace) -> int:
    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title)
    provider = _demo_fake_provider()
    provider_result = provider.search(query)
    if not provider_result.candidates:
        result = TransferExecutionService().result(
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
    queue_plan_result = TransferPlanningService().plan_queue(download_plan, priority=priority)
    if queue_plan_result.status == Status.FAILED:
        print(_render_result(queue_plan_result))
        return 1
    queue_plan = _extract_queue_plan(queue_plan_result)

    mode = TransferExecutionMode.DRY_RUN
    if getattr(args, "apply", False):
        mode = TransferExecutionMode.APPLY

    allow_provider_queue = mode == TransferExecutionMode.APPLY
    exec_service = TransferExecutionService()
    request = exec_service.build_execution_request(
        queue_plan=queue_plan,
        mode=mode,
        allow_provider_queue=allow_provider_queue,
    )
    fake_exec_provider = FakeQueueExecutionProvider()
    result = exec_service.execute_queue(request, fake_exec_provider)
    print(_render_result(result))
    return _exit_code(result.status)


def run_transfer_execute_slskd(args: argparse.Namespace) -> int:
    """Execute slskd queue submission.

    Offline/fake mode is the default. Real network access requires
    --allow-network, --apply, --url, and --api-key-env.
    """
    from noqlen_flux.providers.slskd import FakeSlskdClient, SlskdHttpClient, SlskdProvider, SlskdProviderConfig

    query = SearchQuery(kind=SearchKind.TRACK, artist=args.artist, title=args.title)

    allow_network = getattr(args, "allow_network", False)
    is_apply = getattr(args, "apply", False)
    is_offline = getattr(args, "offline", False) or not allow_network

    queue_failures = getattr(args, "provider_error", False)
    queue_duplicate = getattr(args, "duplicate", False)
    queue_locked = getattr(args, "locked", False)
    queue_unavailable = getattr(args, "unavailable", False)

    if is_offline or not allow_network:
        provider = _build_offline_slskd_provider(
            queue_failures=queue_failures,
            queue_duplicate=queue_duplicate,
            queue_locked=queue_locked,
            queue_unavailable=queue_unavailable,
        )
    else:
        url = getattr(args, "url", None)
        api_key_env = getattr(args, "api_key_env", None)

        if not url:
            result = FluxResult(
                operation=TransferExecutionService.operation,
                status=Status.FAILED,
                errors=[FluxError(code="missing-url", message="real queue submission requires --url when --allow-network is set")],
            )
            print(_render_result(result))
            return 1

        if not api_key_env:
            result = FluxResult(
                operation=TransferExecutionService.operation,
                status=Status.FAILED,
                errors=[FluxError(code="missing-api-key-env", message="real queue submission requires --api-key-env when --allow-network is set")],
            )
            print(_render_result(result))
            return 1

        api_key = os.environ.get(api_key_env)
        if not api_key:
            result = FluxResult(
                operation=TransferExecutionService.operation,
                status=Status.FAILED,
                errors=[FluxError(code="empty-api-key", message=f"environment variable {api_key_env} is not set or empty")],
            )
            print(_render_result(result))
            return 1

        timeout = getattr(args, "timeout", None) or 5
        max_polls = getattr(args, "max_polls", None) or 10

        config = SlskdProviderConfig(
            base_url=url,
            api_key=api_key,
            allow_network=True,
            timeout_seconds=timeout,
            max_poll_attempts=max_polls,
        )
        provider = SlskdProvider(config=config)

    provider_result = provider.search(query)
    if not provider_result.candidates:
        result = TransferExecutionService().result(
            status=Status.FAILED,
            error="no candidates found from slskd search",
        )
        print(_render_result(result))
        return 1

    candidate = provider_result.candidates[0]
    if candidate.files:
        candidate = candidate._replace(files=[f._replace(locked=queue_locked) for f in candidate.files]) if hasattr(candidate, '_replace') else candidate

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
    queue_plan_result = TransferPlanningService().plan_queue(download_plan, priority=priority)
    if queue_plan_result.status == Status.FAILED:
        print(_render_result(queue_plan_result))
        return 1

    queue_plan = _extract_queue_plan(queue_plan_result)

    if queue_locked:
        from noqlen_flux.transfers import QueueItem as QI, TransferItem as TI, TransferState as TS
        locked_items = []
        for qi in queue_plan.items:
            if qi.transfer_item:
                ti = qi.transfer_item
                locked_ti = TI(
                    item_id=ti.item_id,
                    plan_id=ti.plan_id,
                    candidate_id=ti.candidate_id,
                    filename=ti.filename,
                    target_relative_path=ti.target_relative_path,
                    size_bytes=ti.size_bytes,
                    priority=ti.priority,
                    locked=True,
                    metadata=ti.metadata,
                )
                locked_items.append(QI(
                    queue_item_id=qi.queue_item_id,
                    transfer_item=locked_ti,
                    state=qi.state,
                    priority=qi.priority,
                    warnings=qi.warnings,
                    errors=qi.errors,
                    metadata=qi.metadata,
                ))
        queue_plan = queue_plan.__class__(
            queue_id=queue_plan.queue_id,
            request_id=queue_plan.request_id,
            state=queue_plan.state,
            items=locked_items,
            blocked=queue_plan.blocked,
            block_reasons=list(queue_plan.block_reasons),
            warnings=list(queue_plan.warnings),
            metadata=queue_plan.metadata,
        )

    mode = TransferExecutionMode.DRY_RUN
    if is_apply:
        mode = TransferExecutionMode.APPLY

    allow_provider_queue = mode == TransferExecutionMode.APPLY
    exec_service = TransferExecutionService()
    request = exec_service.build_execution_request(
        queue_plan=queue_plan,
        mode=mode,
        allow_provider_queue=allow_provider_queue,
        allow_locked=queue_locked,
    )
    result = exec_service.execute_queue(request, provider)
    print(_render_result(result))
    return _exit_code(result.status)


def run_transfer_status_slskd(args: argparse.Namespace) -> int:
    """Poll slskd transfer status.

    Offline/fake mode is the default. Real network access requires
    --allow-network, --url, and --api-key-env.
    """
    from noqlen_flux.providers.slskd import SlskdProvider, SlskdProviderConfig
    from noqlen_flux.results import FluxResult, Status, FluxError, FluxWarning, Artifact

    transfer_id = args.transfer_id
    queue_item_id = getattr(args, "queue_item_id", None)
    allow_network = getattr(args, "allow_network", False)

    if not allow_network:
        from noqlen_flux.providers.slskd import FakeSlskdClient

        transfer_state = "completed"
        fake_client = FakeSlskdClient(transfer_state=transfer_state)
        provider = SlskdProvider(client=fake_client)
    else:
        url = getattr(args, "url", None)
        api_key_env = getattr(args, "api_key_env", None)

        if not url:
            print(_render_result(FluxResult(
                operation="transfer-status",
                status=Status.FAILED,
                errors=[FluxError(code="missing-url", message="real transfer status requires --url when --allow-network is set")],
            )))
            return 1

        if not api_key_env:
            print(_render_result(FluxResult(
                operation="transfer-status",
                status=Status.FAILED,
                errors=[FluxError(code="missing-api-key-env", message="real transfer status requires --api-key-env when --allow-network is set")],
            )))
            return 1

        api_key = os.environ.get(api_key_env)
        if not api_key:
            print(_render_result(FluxResult(
                operation="transfer-status",
                status=Status.FAILED,
                errors=[FluxError(code="empty-api-key", message=f"environment variable {api_key_env} is not set or empty")],
            )))
            return 1

        config = SlskdProviderConfig(
            base_url=url,
            api_key=api_key,
            allow_network=True,
        )
        provider = SlskdProvider(config=config)

    status = provider.get_status(transfer_id, queue_item_id=queue_item_id)

    result = FluxResult(
        operation="transfer-status",
        status=Status.SUCCESS if not status.errors else Status.FAILED,
        summary={
            "transfer_id": status.transfer_id,
            "queue_item_id": status.queue_item_id,
            "state": status.state.value,
            "progress_percent": status.progress_percent,
            "bytes_transferred": status.bytes_transferred,
            "total_bytes": status.total_bytes,
        },
        warnings=[FluxWarning(code="status-warning", message=w) for w in status.warnings],
        errors=[FluxError(code="status-error", message=e) for e in status.errors],
        artifacts=[Artifact(kind="transfer-status", description=f"Transfer status: {status.state.value}")],
    )
    print(_render_result(result))
    return _exit_code(result.status)


def _build_offline_slskd_provider(
    *,
    queue_failures: bool = False,
    queue_duplicate: bool = False,
    queue_locked: bool = False,
    queue_unavailable: bool = False,
) -> SlskdProvider:
    from noqlen_flux.providers.slskd import FakeSlskdClient, SlskdProvider

    fake_client = FakeSlskdClient(
        responses=[{
            "responses": [{
                "username": "fake-user",
                "directory": "Example Artist/Example Album",
                "files": [{"filename": "Example Track.flac", "size": 12345678, "extension": "flac"}],
                "locked_files": [],
            }],
            "response_count": 1,
        }],
        queue_simulate_failures=queue_failures,
        queue_simulate_duplicate=queue_duplicate,
        queue_simulate_locked=queue_locked,
        queue_simulate_provider_unavailable=queue_unavailable,
    )
    return SlskdProvider(client=fake_client)


def run_provider_inspect(args: argparse.Namespace) -> int:
    provider = _resolve_provider(args.provider_kind)
    result = ProviderService().inspect_provider(provider)
    print(_render_result(result))
    return _exit_code(result.status)


def run_provider_health(args: argparse.Namespace) -> int:
    provider = _resolve_provider(args.provider_kind, args)
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


def run_quality_inspect(args: argparse.Namespace) -> int:
    """Inspect a file for quality using a probe backend.

    Defaults to dry-run with fake probe backend. --apply uses real ffprobe
    if available and writes report to workspace/reports.
    """
    from noqlen_flux.services.audio_probe import FakeProbeBackend, FfmpegProbeBackend
    from noqlen_flux.config import config_from_env
    from noqlen_flux.reports import ReportFormat
    from pathlib import Path

    dry_run = not getattr(args, "apply", False)
    item_id = getattr(args, "item_id", None) or Path(args.path).stem
    workspace = args.workspace

    if dry_run:
        backend = FakeProbeBackend(grade="excellent")
    else:
        backend = FfmpegProbeBackend()
        if not backend.is_available():
            from noqlen_flux.results import FluxResult, Status, FluxError
            print(_render_result(FluxResult(
                operation="quality",
                status=Status.FAILED,
                errors=[FluxError(
                    code="ffprobe-unavailable",
                    message="ffprobe/ffmpeg is not available. Install ffmpeg or use --dry-run for fake probe.",
                )],
            )))
            return 1

    result = QualityService().inspect_file(
        item_id=item_id,
        relative_path=args.path,
        workspace_root=workspace,
        backend=backend,
        dry_run=dry_run,
    )

    if not dry_run and result.status != Status.FAILED:
        report_result = ReportService().write_report(
            config_from_env(workspace, dry_run=False),
            result,
            ReportFormat.JSON,
        )
        result.steps.extend(report_result.steps)
        result.warnings.extend(report_result.warnings)
        result.errors.extend(report_result.errors)
        result.artifacts.extend(report_result.artifacts)
        result.applied_changes.extend(report_result.applied_changes)
        if report_result.status == Status.FAILED:
            result.status = Status.FAILED
        result.summary["report"] = report_result.summary

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


def run_staging_apply(args: argparse.Namespace) -> int:
    import uuid

    from noqlen_flux.config import config_from_env
    from noqlen_flux.routing import (
        DEFAULT_ROUTING_APPLY_POLICY,
        DEFAULT_ROUTING_POLICY,
        RoutingActionType,
        RoutingDecision,
        RoutingOutcome,
        RoutingPlan,
    )
    from noqlen_flux.services.staging import StagingPlanService
    from noqlen_flux.staging import (
        DEFAULT_STAGING_EXECUTION_POLICY,
        StagingActionType,
        StagingArea,
        StagingExecutionPolicy,
        StagingItem,
        StagingPlan,
    )

    dry_run = not args.apply
    config = config_from_env(args.workspace, dry_run=dry_run)

    outcome_map = {
        "approved": RoutingOutcome.APPROVED,
        "quarantine": RoutingOutcome.QUARANTINE,
        "rejected": RoutingOutcome.REJECTED,
        "delete-eligible": RoutingOutcome.DELETE_ELIGIBLE,
        "review": RoutingOutcome.REVIEW,
    }
    outcome = outcome_map[args.outcome]
    item_id = args.item_id or f"apply-{outcome.value}-item"

    decision = RoutingDecision(
        item_id=item_id,
        outcome=outcome,
        action_type=RoutingActionType.PLAN_ONLY,
        policy=DEFAULT_ROUTING_POLICY,
        metadata={"scenario": args.outcome, "source": "cli-staging-apply"},
    )

    routing_plan = RoutingPlan(
        plan_id=str(uuid.uuid4()),
        decisions=[decision],
        metadata={"scenario": args.outcome},
    )

    staging_result = StagingPlanService().plan_staging(routing_plan)
    if staging_result.status == Status.FAILED:
        print(_render_result(staging_result))
        return _exit_code(staging_result.status)

    staging_plan_dict = staging_result.summary.get("staging_plan", {})
    items_data = staging_plan_dict.get("items", [])

    staging_items: list[StagingItem] = []
    for item_data in items_data:
        source_relative = f"incoming/{item_data['item_id']}.txt"
        target_relative = item_data.get("target_relative_path") or f"{item_data['target_area']}/{item_data['item_id']}.txt"

        area = StagingArea(item_data.get("target_area", "unknown"))
        if area == StagingArea.DELETE_ELIGIBLE:
            action_type = StagingActionType.MARK_DELETE_ELIGIBLE
        elif area == StagingArea.REVIEW:
            action_type = StagingActionType.PLAN_ONLY
            source_relative = None
        else:
            action_type = StagingActionType.COPY

        staging_item = StagingItem(
            item_id=item_data["item_id"],
            routing_outcome=item_data.get("routing_outcome", outcome.value),
            source_relative_path=source_relative,
            target_area=area,
            target_relative_path=target_relative,
            action_type=action_type,
            metadata={"scenario": args.outcome, "mode": "dry-run" if dry_run else "apply"},
        )
        staging_items.append(staging_item)

    staging_plan = StagingPlan(
        plan_id=str(uuid.uuid4()),
        items=staging_items,
        metadata={"scenario": args.outcome},
    )

    exec_service = StagingExecutionService()

    if dry_run:
        result = exec_service.apply_staging(
            staging_plan, config,
            apply_policy=DEFAULT_ROUTING_APPLY_POLICY,
            staging_policy=DEFAULT_STAGING_EXECUTION_POLICY,
        )
    else:
        incoming_dir = config.workspace_root / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        demo_file = incoming_dir / f"{item_id}.txt"
        if not demo_file.exists():
            demo_file.write_text(f"Fake demo content for {item_id}\n")

        result = exec_service.apply_staging(
            staging_plan, config,
            apply_policy=DEFAULT_ROUTING_APPLY_POLICY,
            staging_policy=DEFAULT_STAGING_EXECUTION_POLICY,
        )

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

    if args.manifest:
        from .config import config_from_env
        config = config_from_env(args.workspace, dry_run=True)
        result = service.load_manifest_from_file(
            config.workspace_root,
            args.manifest,
            protected_roots=config.protected_roots,
        )
        if result.status == Status.FAILED:
            print(_render_result(result))
            return _exit_code(result.status)
        manifest_data = result.summary.get("manifest", {})
        items_raw = manifest_data.get("items", [])
        items: list[Any] = []
        for item_data in items_raw:
            try:
                from .services.handoff import _parse_handoff_item
                items.append(_parse_handoff_item(item_data))
            except (KeyError, ValueError):
                continue
        manifest = service.build_manifest(items=items)
        validation = service.validate_manifest(manifest)
    else:
        manifest = service.demo_manifest()
        validation = service.validate_manifest(manifest)

    status_label = "valid" if validation.valid else "invalid"
    lines = [f"Noqlen Flux Core handoff: {status_label}"]
    lines.append(f"Validation: {len(validation.issues)} issue(s), {len(validation.warnings)} warning(s), {len(validation.errors)} error(s)")
    for issue in validation.issues:
        lines.append(f"  [{issue.severity}] {issue.code}: {issue.message}")
    print("\n".join(lines))
    return 0 if validation.valid else 1


def run_handoff_apply(args: argparse.Namespace) -> int:
    from noqlen_flux.config import config_from_env
    from noqlen_flux.services import HandoffManifestService

    dry_run = not args.apply
    config = config_from_env(args.workspace, dry_run=dry_run)
    service = HandoffManifestService()

    result = service.apply_manifest(config, args.manifest, dry_run=dry_run)
    print(_render_result(result))
    return _exit_code(result.status)


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


def _resolve_provider(kind: str, args: argparse.Namespace | None = None):
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
    if kind == "slskd":
        from noqlen_flux.providers.slskd import SlskdProvider, SlskdProviderConfig

        allow_network = getattr(args, "allow_network", False) if args else False
        url = getattr(args, "url", None) if args else None
        api_key_env = getattr(args, "api_key_env", None) if args else None
        api_key = os.environ.get(api_key_env) if api_key_env else None

        config = SlskdProviderConfig(
            base_url=url,
            api_key=api_key,
            allow_network=allow_network,
        )
        return SlskdProvider(config=config)

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


def _extract_queue_plan(result: FluxResult):
    from noqlen_flux.transfers import QueueItem, QueuePlan, QueueState, TransferItem, TransferState

    summary = result.summary
    items = []
    for change in result.planned_changes:
        transfer_item = TransferItem(
            item_id=change.metadata.get("transfer_item_id", ""),
            plan_id=summary.get("plan_id", summary.get("queue_id", "")),
            candidate_id=summary.get("candidate_id", ""),
            filename=change.metadata.get("filename", ""),
            target_relative_path=change.target,
        )
        items.append(
            QueueItem(
                queue_item_id=change.metadata.get("queue_item_id", ""),
                transfer_item=transfer_item,
                state=TransferState.PLANNED,
            )
        )
    return QueuePlan(
        queue_id=summary.get("queue_id", ""),
        request_id=summary.get("request_id", ""),
        state=QueueState(summary.get("state", "ready")),
        items=items,
        blocked=summary.get("blocked", False),
        block_reasons=summary.get("block_reasons", []),
        warnings=summary.get("warnings", []),
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
        safety_report = result.summary.get("safety_report")
        if safety_report is not None:
            lines.append(f"safety_report: {safety_report.get('report_id', '?')}")
            lines.append(f"safety_mode: {safety_report.get('mode', '?')}")
            safety_notes = safety_report.get("notes", [])
            for note in safety_notes:
                lines.append(f"  safety: {note}")
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
    if result.operation == "search" and result.summary.get("provider") == "slskd":
        response_count = result.summary.get("response_count")
        if response_count is not None:
            lines.append(f"responses: {response_count}")
        timeout_flag = result.summary.get("timeout_reached")
        if timeout_flag:
            lines.append("timeout: poll limit reached")
        candidates = result.summary.get("candidates", [])
        for c in candidates:
            lines.append(f"  candidate: {c.get('candidate_id', '?')}")
            if c.get("username"):
                lines.append(f"    user: {c['username']}")
            if c.get("directory"):
                lines.append(f"    dir: {c['directory']}")
            files = c.get("files", [])
            locked_count = sum(1 for f in files if f.get("locked"))
            lines.append(f"    files: {len(files)} ({locked_count} locked)")
            for f in files:
                lock_tag = " [locked]" if f.get("locked") else ""
                parts = [f"      {f.get('filename', '?')}"]
                if f.get("extension"):
                    parts[-1] += f" .{f['extension']}"
                if f.get("size_bytes") is not None:
                    parts.append(f"size={f['size_bytes']}")
                if f.get("declared_bitrate") is not None:
                    parts.append(f"bitrate={f['declared_bitrate']}")
                if f.get("duration_seconds") is not None:
                    parts.append(f"duration={f['duration_seconds']}s")
                parts[-1] += lock_tag
                lines.append("".join(parts))
    if result.operation == "download-planning" and result.summary.get("intent"):
        lines.append(f"intent: {result.summary['intent']}")
        candidate_id = result.summary.get("candidate_id")
        if candidate_id:
            lines.append(f"candidate: {candidate_id}")
        item_count = result.summary.get("item_count")
        if item_count is not None:
            lines.append(f"planned items: {item_count}")
        total_size = result.summary.get("total_size_bytes")
        if total_size is not None:
            lines.append(f"total size: {total_size} bytes")
        target_root = result.summary.get("target_relative_root")
        if target_root:
            lines.append(f"target: {target_root}")
        plan_warnings = result.summary.get("warnings", [])
        for w in plan_warnings:
            lines.append(f"  plan warning: {w}")
    if result.operation == "musiclab-scoring":
        dataset_id = result.summary.get("dataset_id")
        if dataset_id is not None:
            lines.append(f"dataset: {dataset_id}")
        dataset_version = result.summary.get("dataset_version")
        if dataset_version is not None:
            lines.append(f"dataset_version: {dataset_version}")
        profile_name = result.summary.get("profile_name")
        if profile_name is not None:
            lines.append(f"profile: {profile_name}")
        total_cases = result.summary.get("total_cases")
        if total_cases is not None:
            lines.append(f"total_cases: {total_cases}")
        passed_cases = result.summary.get("passed_cases")
        if passed_cases is not None:
            lines.append(f"passed: {passed_cases}")
        failed_cases = result.summary.get("failed_cases")
        if failed_cases is not None:
            lines.append(f"failed: {failed_cases}")
        failed_ids = result.summary.get("failed_case_ids")
        if failed_ids:
            lines.append(f"failed_case_ids: {', '.join(failed_ids)}")
    if result.operation == "musiclab-quality":
        dataset_id = result.summary.get("dataset_id")
        if dataset_id is not None:
            lines.append(f"dataset: {dataset_id}")
        dataset_version = result.summary.get("dataset_version")
        if dataset_version is not None:
            lines.append(f"dataset_version: {dataset_version}")
        profile_name = result.summary.get("profile_name")
        if profile_name is not None:
            lines.append(f"profile: {profile_name}")
        total_cases = result.summary.get("total_cases")
        if total_cases is not None:
            lines.append(f"total_cases: {total_cases}")
        passed_cases = result.summary.get("passed_cases")
        if passed_cases is not None:
            lines.append(f"passed: {passed_cases}")
        failed_cases = result.summary.get("failed_cases")
        if failed_cases is not None:
            lines.append(f"failed: {failed_cases}")
        failed_ids = result.summary.get("failed_case_ids")
        if failed_ids:
            lines.append(f"failed_case_ids: {', '.join(failed_ids)}")
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
