from pathlib import Path

from noqlen_flux.musiclab_scenario import (
    MusicLabScenario,
    MusicLabScenarioConfig,
    MusicLabScenarioPack,
    MusicLabScenarioReport,
    MusicLabScenarioResult,
    MusicLabScenarioStepResult,
    ScenarioCategory,
    ScenarioKind,
    ScenarioOutcome,
    ScenarioSeverity,
)
from noqlen_flux.musiclab_scenario_factory import (
    SyntheticFixture,
    SyntheticProbeProfile,
    build_probe_findings,
    build_good_candidate,
)
from noqlen_flux.musiclab_scenario_packs import (
    all_scenario_packs,
    get_scenario,
    get_scenario_fixture,
    list_all_scenarios,
    list_all_packs,
)
from noqlen_flux.quality import (
    QualityFindingKind,
    QualityGrade,
)
from noqlen_flux.results import Status
from noqlen_flux.search import SearchKind, SearchQuery
from noqlen_flux.services import MusicLabScenarioRunnerService


class TestMusicLabScenarioContracts:
    def test_scenario_serializes_safely(self) -> None:
        scenario = MusicLabScenario(
            scenario_id="test-scenario",
            description="A test scenario",
            category=ScenarioCategory.GOOD,
            kind=ScenarioKind.SINGLE_TRACK,
            tags=["test"],
        )
        payload = scenario.to_dict()
        assert payload["scenario_id"] == "test-scenario"
        assert payload["category"] == "good"
        assert "test" in payload["tags"]

    def test_scenario_result_serializes_safely(self) -> None:
        result = MusicLabScenarioResult(
            scenario_id="test-scenario",
            outcome=ScenarioOutcome.PASS,
            expected_grade=QualityGrade.EXCELLENT.value,
            actual_grade=QualityGrade.EXCELLENT.value,
            expected_routing_outcome="approved",
            actual_routing_outcome="approved",
            expected_staging_area="approved",
            actual_staging_area="approved",
            objective_failure_codes=[],
            heuristic_warning_codes=[],
            destructive_action_detected=False,
        )
        payload = result.to_dict()
        assert payload["scenario_id"] == "test-scenario"
        assert payload["outcome"] == "pass"
        assert payload["destructive_action_detected"] is False

    def test_scenario_report_serializes_safely(self) -> None:
        report = MusicLabScenarioReport(
            report_id="rpt-1",
            pack_id="test-pack",
            total_scenarios=1,
            passed=1,
            failed=0,
            skipped=0,
            errored=0,
        )
        payload = report.to_dict()
        assert payload["report_id"] == "rpt-1"
        assert payload["pack_id"] == "test-pack"
        assert payload["total_scenarios"] == 1

    def test_scenario_pack_serializes_safely(self) -> None:
        pack = MusicLabScenarioPack(
            pack_id="test-pack",
            description="Test pack",
            version="1",
            scenarios=[],
        )
        payload = pack.to_dict()
        assert payload["pack_id"] == "test-pack"
        assert payload["version"] == "1"

    def test_scenario_config_defaults(self) -> None:
        config = MusicLabScenarioConfig()
        assert config.dry_run is True
        assert config.run_scoring is True
        assert config.run_quality is True
        assert config.simulate_artifact is True


class TestSyntheticProbeProfile:
    def test_probe_profile_defaults(self) -> None:
        probe = SyntheticProbeProfile()
        assert probe.codec == "flac"
        assert probe.sample_rate == 44100
        assert probe.bit_depth == 16
        assert probe.decode_ok is True
        assert probe.has_audio_stream is True
        assert probe.lowpass_suspicion is False
        assert probe.spectral_cutoff_hz is None

    def test_probe_profile_serializes_safely(self) -> None:
        probe = SyntheticProbeProfile(
            codec="mp3",
            sample_rate=48000,
            spectral_cutoff_hz=16000,
            lowpass_suspicion=True,
        )
        payload = probe.to_dict()
        assert payload["codec"] == "mp3"
        assert payload["sample_rate"] == 48000
        assert payload["spectral_cutoff_hz"] == 16000
        assert payload["lowpass_suspicion"] is True

    def test_build_probe_findings_clean_flac(self) -> None:
        probe = SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16)
        findings = build_probe_findings(probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        heuristic = [f for f in findings if f.kind == QualityFindingKind.HEURISTIC_WARNING]
        diagnostic = [f for f in findings if f.kind == QualityFindingKind.DIAGNOSTIC]
        assert len(objective) == 0
        assert len(heuristic) == 0
        assert len(diagnostic) > 0


class TestCutoffLowpassRules:
    def test_cutoff_alone_is_heuristic_warning(self) -> None:
        probe = SyntheticProbeProfile(
            codec="flac",
            spectral_cutoff_hz=9400,
            decode_ok=True,
            has_audio_stream=True,
        )
        findings = build_probe_findings(probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        heuristic = [f for f in findings if f.kind == QualityFindingKind.HEURISTIC_WARNING]
        assert len(objective) == 0, "Cutoff alone must NOT produce objective failure"
        assert len(heuristic) > 0, "Cutoff alone must produce heuristic warning"

    def test_lowpass_alone_is_heuristic_warning(self) -> None:
        probe = SyntheticProbeProfile(
            codec="flac",
            lowpass_suspicion=True,
            decode_ok=True,
            has_audio_stream=True,
        )
        findings = build_probe_findings(probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        heuristic = [f for f in findings if f.kind == QualityFindingKind.HEURISTIC_WARNING]
        assert len(objective) == 0, "Lowpass alone must NOT produce objective failure"
        assert len(heuristic) > 0, "Lowpass alone must produce heuristic warning"

    def test_decode_failure_is_objective(self) -> None:
        probe = SyntheticProbeProfile(
            codec="flac",
            decode_ok=False,
            has_audio_stream=True,
        )
        findings = build_probe_findings(probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        assert len(objective) > 0, "Decode failure must produce objective failure"

    def test_lowpass_plus_decode_failure_has_both(self) -> None:
        probe = SyntheticProbeProfile(
            codec="flac",
            lowpass_suspicion=True,
            spectral_cutoff_hz=12000,
            decode_ok=False,
            has_audio_stream=True,
        )
        findings = build_probe_findings(probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        heuristic = [f for f in findings if f.kind == QualityFindingKind.HEURISTIC_WARNING]
        assert len(objective) > 0, "Must have decode-failure objective"
        assert len(heuristic) > 0, "Must have lowpass/cutoff heuristic"
        decode_codes = [f.code for f in objective]
        assert "decode-failure" in decode_codes

    def test_zero_byte_is_objective(self) -> None:
        probe = SyntheticProbeProfile(
            file_size_bytes=0,
            probe_success=False,
            decode_ok=False,
            has_audio_stream=False,
        )
        findings = build_probe_findings(probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        codes = [f.code for f in objective]
        assert "zero-byte-file" in codes

    def test_no_audio_stream_is_objective(self) -> None:
        probe = SyntheticProbeProfile(
            has_audio_stream=False,
            audio_stream_count=0,
        )
        findings = build_probe_findings(probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        codes = [f.code for f in objective]
        assert "no-audio-stream" in codes


class TestFixtureFactory:
    def test_build_good_candidate(self) -> None:
        candidate = build_good_candidate("test-1", "Artist", "Title")
        assert candidate.candidate_id == "test-1"
        assert candidate.artist == "Artist"
        assert candidate.title == "Title"
        assert len(candidate.files) == 1
        assert candidate.files[0].extension == "flac"

    def test_build_good_candidate_custom_files(self) -> None:
        candidate = build_good_candidate(
            "test-2", "Artist", "Title",
            files=[("custom.mp3", "mp3", 5000000)],
        )
        assert candidate.files[0].filename == "custom.mp3"
        assert candidate.files[0].extension == "mp3"

    def test_synthetic_fixture_has_all_fields(self) -> None:
        probe = SyntheticProbeProfile(codec="flac")
        fixture = SyntheticFixture(
            fixture_id="fx-1",
            description="Test fixture",
            query=SearchQuery(kind=SearchKind.TRACK, artist="A", title="T"),
            candidate=build_good_candidate("fx-1", "A", "T"),
            probe=probe,
        )
        payload = fixture.to_dict()
        assert payload["fixture_id"] == "fx-1"
        assert "query" in payload


class TestScenarioPacks:
    def test_all_packs_are_loaded(self) -> None:
        packs = all_scenario_packs()
        assert "good-formats" in packs
        assert "corrupt-and-invalid" in packs
        assert "transcode-suspicion" in packs
        assert "fake-quality" in packs
        assert "sample-rate-manipulation" in packs
        assert "lowpass-and-cutoff" in packs
        assert "false-positive-guard" in packs
        assert "album-scenarios" in packs
        assert "edge-cases" in packs
        assert "source-profiles" in packs

    def test_good_formats_pack_fixtures(self) -> None:
        packs = all_scenario_packs()
        pack, fixtures = packs["good-formats"]
        assert len(pack.scenarios) == 8
        assert all(s.category == ScenarioCategory.GOOD for s in pack.scenarios)
        assert len(fixtures) == 8

    def test_corrupt_pack_fixtures(self) -> None:
        packs = all_scenario_packs()
        pack, fixtures = packs["corrupt-and-invalid"]
        assert len(pack.scenarios) == 7
        assert all(s.category == ScenarioCategory.BAD for s in pack.scenarios)

    def test_false_positive_guard_pack_fixtures(self) -> None:
        packs = all_scenario_packs()
        pack, fixtures = packs["false-positive-guard"]
        assert len(pack.scenarios) == 7
        assert all(s.category == ScenarioCategory.FALSE_POSITIVE for s in pack.scenarios)

    def test_source_profile_pack_does_not_encode_quality_findings(self) -> None:
        packs = all_scenario_packs()
        pack, fixtures = packs["source-profiles"]
        assert len(pack.scenarios) == 9
        for fixture in fixtures.values():
            findings = build_probe_findings(fixture.probe)
            objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
            heuristic = [f for f in findings if f.kind == QualityFindingKind.HEURISTIC_WARNING]
            assert objective == []
            assert heuristic == []

    def test_qobuz_like_scenario_exists(self) -> None:
        scenario = get_scenario("qobuz_like_cutoff_9_4khz_decode_ok")
        assert scenario is not None
        assert scenario.scenario_id == "qobuz_like_cutoff_9_4khz_decode_ok"
        fixture = get_scenario_fixture("qobuz_like_cutoff_9_4khz_decode_ok")
        assert fixture is not None
        assert fixture.probe.spectral_cutoff_hz == 9400
        assert fixture.probe.decode_ok is True

    def test_lowpass_suspicion_only_has_no_objective(self) -> None:
        fixture = get_scenario_fixture("lowpass_suspicion_only")
        assert fixture is not None
        assert fixture.probe.lowpass_suspicion is True
        assert fixture.probe.decode_ok is True
        findings = build_probe_findings(fixture.probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        assert len(objective) == 0

    def test_lowpass_plus_decode_failure_is_bad(self) -> None:
        fixture = get_scenario_fixture("lowpass_plus_decode_failure")
        assert fixture is not None
        assert fixture.probe.decode_ok is False
        findings = build_probe_findings(fixture.probe)
        objective = [f for f in findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        assert len(objective) > 0
        codes = [f.code for f in objective]
        assert "decode-failure" in codes

    def test_list_all_scenarios_has_all_required(self) -> None:
        scenarios = list_all_scenarios()
        scenario_ids = {s.scenario_id for s in scenarios}
        required = {
            "flac-16-44-good",
            "flac-24-96-good",
            "wav-good",
            "alac-good",
            "mp3-320-good",
            "aac-256-good",
            "opus-good",
            "ogg-vorbis-good",
            "zero-byte",
            "corrupt-file",
            "no-audio-stream",
            "invalid-duration",
            "truncated-file",
            "container-unreadable",
            "probe-timeout",
            "fake-flac",
            "mp3-transcoded-to-flac",
            "aac-transcoded-to-wav",
            "opus-renamed-as-flac",
            "lossy-source-lossless-container",
            "bitrate-container-incompatible",
            "fake-24bit",
            "fake-96khz",
            "upsampled-44-to-96",
            "downsampled-96-to-44",
            "qobuz_like_cutoff_9_4khz_decode_ok",
            "lowpass_suspicion_only",
            "spectral_cutoff_only",
            "lowpass_with_valid_metadata",
            "lowpass_plus_decode_failure",
            "fake_flac_lowpass_but_decode_ok",
            "mp3_320_good_lowpass_like",
            "album-completo",
            "album-faixa-faltando",
            "album-faixa-duplicada",
            "album-ordem-errada",
            "album-mixed-formats",
            "album-um-arquivo-ruim",
            "arquivo-locked",
            "usuario-offline",
            "download-incompleto",
            "candidato-errado-bom",
            "candidato-bom-metadata-ruim",
            "source-qobuz_like",
            "source-bandcamp_like",
            "source-cd_rip_like",
            "source-soulseek_folder_like",
            "source-youtube_rip_like",
            "source-spotify_rip_like",
            "source-web_rip_like",
            "source-vinyl_rip_like",
            "source-live_bootleg_like",
        }
        missing = required - scenario_ids
        assert not missing, f"Missing scenarios: {missing}"

    def test_list_all_packs(self) -> None:
        packs = list_all_packs()
        assert len(packs) == 12
        pack_ids = {p.pack_id for p in packs}
        assert "false-positive-guard" in pack_ids
        assert "source-profiles" in pack_ids
        assert "advanced-quality" in pack_ids


class TestScenarioRunner:
    def test_list_scenarios(self) -> None:
        result = MusicLabScenarioRunnerService().list_scenarios()
        assert result.status == Status.SUCCESS
        assert result.summary.get("scenario_count", 0) > 0

    def test_list_packs(self) -> None:
        result = MusicLabScenarioRunnerService().list_packs()
        assert result.status == Status.SUCCESS
        assert result.summary.get("pack_count", 0) > 0

    def test_run_scenario_not_found(self) -> None:
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="non-existent",
            workspace_root="/tmp/noqlen-flux-test",
        )
        assert result.status == Status.FAILED

    def test_run_pack_not_found(self) -> None:
        result = MusicLabScenarioRunnerService().run_pack(
            pack_id="non-existent-pack",
            workspace_root="/tmp/noqlen-flux-test",
        )
        assert result.status == Status.FAILED

    def test_run_good_scenario_flac_16_44(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="flac-16-44-good",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        assert result.summary.get("actual_grade") == "excellent"
        assert result.summary.get("actual_routing_outcome") == "approved"
        assert result.summary.get("destructive_action_detected") is False

    def test_run_bad_scenario_zero_byte(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="zero-byte",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        assert result.summary.get("actual_grade") == "bad"
        assert "zero-byte-file" in result.summary.get("objective_failure_codes", [])

    def test_run_qobuz_like_not_punished(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="qobuz_like_cutoff_9_4khz_decode_ok",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        assert result.summary.get("actual_grade") != "bad", "qobuz_like must not be bad"
        assert result.summary.get("actual_routing_outcome") not in ("rejected", "delete_eligible"), "qobuz_like must not be rejected"

    def test_run_lowpass_only_not_bad(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="lowpass_suspicion_only",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        assert result.summary.get("actual_grade") != "bad", "Lowpass only must not be bad"
        objective = result.summary.get("objective_failure_codes", [])
        assert len(objective) == 0, "Lowpass only must not have objective failures"

    def test_run_false_positive_guard_pack(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_pack(
            pack_id="false-positive-guard",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status in (Status.SUCCESS, Status.WARNING)
        assert result.summary.get("total_scenarios", 0) > 0
        critical = result.summary.get("critical_failures", [])
        assert len(critical) == 0, f"Critical failures in false-positive-guard: {critical}"

    def test_source_profile_alone_does_not_decide_quality(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="source-youtube_rip_like",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        assert result.summary.get("actual_grade") == "excellent"
        assert result.summary.get("objective_failure_codes") == []
        assert result.summary.get("heuristic_warning_codes") == []

    def test_pack_report_redacts_workspace_path(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "private-user-name" / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_pack(
            pack_id="source-profiles",
            workspace_root=workspace,
            dry_run=True,
        )
        metadata = result.summary["report"]["metadata"]
        assert metadata["workspace_root"] == "[workspace-root]"
        assert "private-user-name" not in str(result.summary["report"])

    def test_run_good_formats_pack(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_pack(
            pack_id="good-formats",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status in (Status.SUCCESS, Status.WARNING)
        assert result.summary.get("total_scenarios", 0) > 0

    def test_destructive_action_is_detected_for_bad_scenario(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="corrupt-file",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        assert result.summary.get("actual_grade") == "bad"

    def test_qobuz_like_cutoff_not_quarantined_at_staging(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="qobuz_like_cutoff_9_4khz_decode_ok",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        actual_staging = result.summary.get("actual_staging_area")
        assert actual_staging != "quarantine", "qobuz_like cutoff must not be auto-quarantined at staging"
        assert actual_staging != "rejected", "qobuz_like cutoff must not be auto-rejected at staging"
        assert actual_staging != "delete_eligible", "qobuz_like cutoff must never be delete_eligible"

    def test_lowpass_suspicion_only_not_rejected_or_delete(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="lowpass_suspicion_only",
            workspace_root=workspace,
            dry_run=True,
        )
        assert result.status == Status.SUCCESS
        actual_staging = result.summary.get("actual_staging_area")
        assert actual_staging not in ("rejected", "delete_eligible"), \
            f"Lowpass only must not be {actual_staging}"
        actual_routing = result.summary.get("actual_routing_outcome")
        assert actual_routing not in ("rejected", "delete_eligible"), \
            f"Lowpass only routing must not be {actual_routing}"

    def test_corrupt_decode_failure_never_delete_eligible(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        for scenario_id in ("corrupt-file", "zero-byte", "truncated-file", "lowpass_plus_decode_failure"):
            result = MusicLabScenarioRunnerService().run_scenario(
                scenario_id=scenario_id,
                workspace_root=workspace,
                dry_run=True,
            )
            actual_staging = result.summary.get("actual_staging_area")
            actual_routing = result.summary.get("actual_routing_outcome")
            assert actual_staging != "delete_eligible", \
                f"{scenario_id}: corrupt/decode_failure must not be delete_eligible at staging"
            assert actual_routing != "delete_eligible", \
                f"{scenario_id}: corrupt/decode_failure must not route to delete_eligible"

    def test_fake_flac_lowpass_decode_ok_never_delete(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="fake-flac",
            workspace_root=workspace,
            dry_run=True,
        )
        actual_routing = result.summary.get("actual_routing_outcome")
        actual_staging = result.summary.get("actual_staging_area")
        assert actual_routing not in ("rejected", "delete_eligible"), \
            f"Fake FLAC transcode must not route to {actual_routing}"
        assert actual_staging not in ("rejected", "delete_eligible"), \
            f"Fake FLAC transcode must not stage to {actual_staging}"

    def test_transcode_suspicion_never_rejected_or_delete(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        transcode_scenarios = [
            "fake-flac", "mp3-transcoded-to-flac", "aac-transcoded-to-wav",
            "opus-renamed-as-flac", "lossy-source-lossless-container",
            "bitrate-container-incompatible",
        ]
        for scenario_id in transcode_scenarios:
            result = MusicLabScenarioRunnerService().run_scenario(
                scenario_id=scenario_id,
                workspace_root=workspace,
                dry_run=True,
            )
            actual_routing = result.summary.get("actual_routing_outcome")
            actual_staging = result.summary.get("actual_staging_area")
            assert actual_routing not in ("rejected", "delete_eligible"), \
                f"{scenario_id}: transcode suspicion must not route to {actual_routing}"
            assert actual_staging not in ("rejected", "delete_eligible"), \
                f"{scenario_id}: transcode suspicion must not stage to {actual_staging}"

    def test_good_scenarios_never_delete_eligible(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        good_scenarios = [
            "flac-16-44-good", "flac-24-96-good", "wav-good", "alac-good",
            "mp3-320-good", "aac-256-good", "opus-good", "ogg-vorbis-good",
        ]
        for scenario_id in good_scenarios:
            result = MusicLabScenarioRunnerService().run_scenario(
                scenario_id=scenario_id,
                workspace_root=workspace,
                dry_run=True,
            )
            actual_staging = result.summary.get("actual_staging_area")
            assert actual_staging != "delete_eligible", \
                f"{scenario_id}: good scenario must not be delete_eligible"
            assert result.summary.get("destructive_action_detected") is False, \
                f"{scenario_id}: good scenario must not have destructive actions"

    def test_handoff_guard_for_good_scenario(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="flac-16-44-good",
            workspace_root=workspace,
            dry_run=True,
        )
        handoff_step = _find_step(result, "handoff-preview")
        if handoff_step:
            meta = handoff_step.get("metadata", {})
            assert meta.get("forge_ready") is True, \
                "Good FLAC 16-44 scenario should be forge_ready"
            assert meta.get("valid") is True

    def test_handoff_guard_blocks_corrupt_scenario(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="corrupt-file",
            workspace_root=workspace,
            dry_run=True,
        )
        handoff_step = _find_step(result, "handoff-preview")
        if handoff_step:
            meta = handoff_step.get("metadata", {})
            assert meta.get("forge_ready") is False, \
                "Corrupt file scenario must NOT be forge_ready"

    def test_handoff_guard_blocks_decode_failure(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        for scenario_id in ("corrupt-file", "zero-byte", "truncated-file"):
            result = MusicLabScenarioRunnerService().run_scenario(
                scenario_id=scenario_id,
                workspace_root=workspace,
                dry_run=True,
            )
            handoff_step = _find_step(result, "handoff-preview")
            if handoff_step:
                meta = handoff_step.get("metadata", {})
                assert meta.get("forge_ready") is False, \
                    f"{scenario_id}: decode_failure must not be forge_ready"

    def test_handoff_guard_for_qobuz_like_cutoff(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="qobuz_like_cutoff_9_4khz_decode_ok",
            workspace_root=workspace,
            dry_run=True,
        )
        actual_staging = result.summary.get("actual_staging_area")
        handoff_step = _find_step(result, "handoff-preview")
        if handoff_step:
            meta = handoff_step.get("metadata", {})
            handoff_status = meta.get("handoff_status")
            assert handoff_status not in ("rejected", "delete_eligible", "quarantine"), \
                f"Qobuz-like cutoff must not be {handoff_status} for handoff"
            assert actual_staging not in ("rejected", "delete_eligible", "quarantine"), \
                f"Qobuz-like cutoff must not be {actual_staging}"

    def test_handoff_guard_for_lowpass_suspicion_only(self, tmp_path: Path) -> None:
        workspace = str(tmp_path / "flux-workspace")
        result = MusicLabScenarioRunnerService().run_scenario(
            scenario_id="lowpass_suspicion_only",
            workspace_root=workspace,
            dry_run=True,
        )
        actual_staging = result.summary.get("actual_staging_area")
        handoff_step = _find_step(result, "handoff-preview")
        if handoff_step:
            meta = handoff_step.get("metadata", {})
            assert actual_staging != "delete_eligible", \
                "Lowpass suspicion must not be delete_eligible for handoff"
            assert meta.get("handoff_status") != "delete_eligible"


def _find_step(result, step_name: str) -> dict | None:
    scenario_result = result.summary.get("scenario_result", {})
    steps = scenario_result.get("steps", [])
    for step in steps:
        if step.get("step_name") == step_name:
            return step
    return None
