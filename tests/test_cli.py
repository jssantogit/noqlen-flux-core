from noqlen_flux.cli import main


def test_help_exits_successfully(capsys) -> None:
    assert main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "noqlen-flux" in output
    assert "doctor" in output


def test_doctor_is_safe_stub(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "bootstrap: OK" in output
    assert "downloads" in output
    assert "not implemented" in output
