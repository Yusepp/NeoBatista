"""Command-line startup tests."""

from pytest import CaptureFixture, MonkeyPatch

from neobatista import cli
from neobatista.config import Settings
from neobatista.errors import ConfigurationError


def test_cli_fails_fast_for_invalid_configuration(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    def fail() -> Settings:
        raise ConfigurationError("missing token")

    monkeypatch.setattr(Settings, "from_env", fail)

    assert cli.main() == 2
    assert "missing token" in capsys.readouterr().err
