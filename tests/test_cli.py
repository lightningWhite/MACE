"""The `mace` command line: what it prints and what it exits with.

CI runs `mace validate packs/`, so the exit code is a contract.
"""

from pathlib import Path

import pytest

from conftest import write_pack
from mace.cli import main


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: mace" in capsys.readouterr().out


def test_validate_succeeds_on_a_clean_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_pack(
        tmp_path,
        "tidy",
        files={
            "a.yml": {
                "locations": [{"id": "home", "name": "Home", "onArrive": "wake"}],
                "scenes": [{"id": "wake", "say": ["You wake."]}],
            }
        },
    )
    assert main(["validate", str(tmp_path / "tidy")]) == 0
    assert "no problems found" in capsys.readouterr().out


def test_validate_fails_on_a_broken_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_pack(
        tmp_path,
        "broken",
        files={
            "a.yml": {
                "locations": [{"id": "home", "name": "Home", "onArrive": "missing"}]
            }
        },
    )
    assert main(["validate", str(tmp_path / "broken")]) == 1
    captured = capsys.readouterr()
    assert "missing" in captured.err
    assert "1 error" in captured.err


def test_errors_only_hides_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_pack(
        tmp_path,
        "noisy",
        files={
            "a.yml": {
                "scenes": [{"id": "nothing"}],
                "locations": [{"id": "home", "name": "Home", "onArrive": "missing"}],
            }
        },
    )
    assert main(["validate", "--errors-only", str(tmp_path / "noisy")]) == 1
    captured = capsys.readouterr()
    assert "changes nothing" not in captured.err
    assert "missing" in captured.err


def test_validate_reports_a_missing_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", str(tmp_path / "nowhere")]) == 1
    assert "no such directory" in capsys.readouterr().err
