import json

from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, Severity, Status, StepResult
from noqlen_flux.services import DoctorService, FluxService


def test_flux_result_to_dict_serializes_contract() -> None:
    result = FluxResult(
        operation="unit-test",
        status=Status.WARNING,
        steps=[StepResult("inspect", Status.WARNING, "review needed")],
        summary={"items": 1},
    ).finish()

    payload = result.to_dict()

    assert payload["operation"] == "unit-test"
    assert payload["status"] == "warning"
    assert payload["steps"][0]["name"] == "inspect"
    assert payload["steps"][0]["status"] == "warning"
    assert payload["summary"] == {"items": 1}
    assert payload["started_at"]
    assert payload["finished_at"]


def test_flux_result_to_json_redacts_sensitive_context() -> None:
    result = FluxResult(
        operation="redaction",
        status=Status.SUCCESS,
        warnings=[FluxWarning("safe", "safe warning", context={"token": "placeholder-secret"})],
        summary={"api_key": "placeholder-secret", "public": "ok"},
    )

    raw = result.to_json()
    payload = json.loads(raw)

    assert "placeholder-secret" not in raw
    assert payload["summary"]["api_key"] == "[redacted]"
    assert payload["summary"]["public"] == "ok"
    assert payload["warnings"][0]["context"]["token"] == "[redacted]"


def test_step_result_serializes_warnings_errors_and_artifacts() -> None:
    step = StepResult(
        name="plan",
        status=Status.FAILED,
        message="blocked",
        warnings=[FluxWarning("warn", "careful", Severity.WARNING)],
        errors=[FluxError("error", "blocked")],
        artifacts=[Artifact("manifest", "planned manifest", metadata={"format": "json"})],
    )

    payload = step.to_dict()

    assert payload["warnings"][0]["severity"] == "warning"
    assert payload["errors"][0]["code"] == "error"
    assert payload["artifacts"][0]["kind"] == "manifest"


def test_models_and_services_do_not_depend_on_terminal_output(capsys) -> None:
    result = DoctorService().run()
    output = capsys.readouterr()

    assert isinstance(FluxService(), FluxService)
    assert result.status == Status.SUCCESS
    assert output.out == ""
    assert output.err == ""
