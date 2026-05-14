import pytest

from noqlen_flux.cli import main


def test_help_exits_successfully(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "noqlen-flux" in output
    assert "doctor" in output


def test_doctor_is_safe_stub(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "doctor: success" in output
    assert "not implemented" in output
