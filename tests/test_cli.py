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


# ── Playing ───────────────────────────────────────────────────────────────────


def scripted(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    """Answer the player prompts with a fixed script.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest's patcher.
    answers : list of str
        What to type, in order. Running out means the player walked away.
    """
    remaining = list(answers)

    def typed(_prompt: str = "") -> str:
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    monkeypatch.setattr("builtins.input", typed)


def test_play_walks_a_pack_to_its_ending(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["1", "2", "3", "3", "4", "1"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    printed = capsys.readouterr().out
    assert "You are a peasant." in printed
    assert "You won." in printed


def test_play_stops_when_the_player_does(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["q"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    assert "Until next time." in capsys.readouterr().out


def test_play_complains_about_a_number_that_is_not_on_offer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["fenmoor", "99", "q"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    printed = capsys.readouterr().out
    assert "Type the number" in printed
    assert "Pick a number between 1 and 3." in printed


def test_play_needs_to_know_which_game(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_pack(tmp_path / "packs", "not-a-game")
    assert main(["play", str(tmp_path / "packs")]) == 1
    assert "no game packs found" in capsys.readouterr().err


def test_play_reports_a_broken_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_pack(tmp_path / "packs", "broken", kind="game")
    assert main(["play", str(tmp_path / "packs")]) == 1
    assert "game" in capsys.readouterr().err
