"""The `mace` command line: what it prints and what it exits with.

CI runs `mace validate packs/`, so the exit code is a contract.
"""

import json
import re
import zipfile
from pathlib import Path

import pytest

from conftest import write_pack
from mace.cli import main
from mace.cli.play import keys_for
from mace.cli.timing import Keypress
from mace.content import validate_paths
from mace.wizard.project import Project
from mace.wizard.share import export_pack


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
    scripted(monkeypatch, ["2", "3", "3", "3", "4", "1"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    printed = capsys.readouterr().out
    assert "You are a peasant." in printed
    assert "You won." in printed


def test_play_reads_temperature_in_fahrenheit_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["q"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    printed = capsys.readouterr().out
    assert "°F" in printed
    assert "°C" not in printed


def test_play_can_be_asked_to_read_temperature_in_celsius(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--units", "celsius"]) == 0
    )
    printed = capsys.readouterr().out
    assert "°C" in printed
    assert "°F" not in printed


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
    assert "Pick a number between 1 and 5." in printed


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


def test_play_draws_the_map_on_demand(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["m", "q"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    printed = capsys.readouterr().out
    assert "● Fenmoor" in printed
    assert "6 ticks  Hagan's Castle" in printed


def test_play_says_the_map_is_there(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["q"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    assert "`m` for the map" in capsys.readouterr().out


def test_play_offers_the_map_when_the_player_types_nonsense(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["north", "q"])
    assert main(["play", "packs", "--pack", "peasants-quest"]) == 0
    assert "`m` for the map" in capsys.readouterr().out


def test_play_can_be_asked_to_slow_the_clock_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """docs/10 § Accessibility: reflex mode, with less of the reflex."""
    save = tmp_path / "slow.json"
    scripted(monkeypatch, ["q"])
    assert (
        main(
            [
                "play",
                "packs",
                "--pack",
                "peasants-quest",
                "--time-pressure",
                "0.5",
                "--save",
                str(save),
            ]
        )
        == 0
    )
    assert json.loads(save.read_text())["timePressure"] == 0.5


def test_serve_reports_content_it_cannot_load(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """It has to fail before it binds a port, not after."""
    write_pack(tmp_path / "packs", "broken", kind="game")
    assert main(["serve", str(tmp_path / "packs")]) == 1
    assert "error" in capsys.readouterr().err


# ── Saving and carrying on ────────────────────────────────────────────────────


def test_play_writes_the_save_it_was_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    save = tmp_path / "saves" / "north.json"
    scripted(monkeypatch, ["2", "3", "q"])
    assert main(["play", "packs", "--pack", "peasants-quest", "--save", str(save)]) == 0

    assert "Saved to" in capsys.readouterr().out
    written = json.loads(save.read_text())
    assert written["pack"] == "peasants-quest"
    assert [action["prompt"] for action in written["actions"]] == [
        "Say goodbye to Hallam",
        "Take the north road",
    ]


def test_play_carries_on_from_a_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    save = tmp_path / "north.json"
    scripted(monkeypatch, ["2", "3", "q"])
    assert main(["play", "packs", "--pack", "peasants-quest", "--save", str(save)]) == 0
    ended = capsys.readouterr().out

    scripted(monkeypatch, ["q"])
    assert main(["play", "packs", "--load", str(save)]) == 0
    resumed = capsys.readouterr().out

    # The replay happens in silence — what a player wants back is the room they
    # were standing in, not the whole game read out to them again.
    assert "Resumed — 2 actions replayed." in resumed
    assert "You are a peasant." not in resumed
    assert "The Old Bridge" in ended
    assert "The Old Bridge" in resumed


def test_play_reports_a_save_it_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["play", "packs", "--load", str(tmp_path / "nowhere.json")]) == 1
    assert "could not read the save" in capsys.readouterr().err


# ── Combat in a terminal ──────────────────────────────────────────────────────


def test_play_fights_a_troll_in_the_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The phase's own acceptance criterion: you can fight a troll and win."""
    # Walk north, refuse the toll, and then answer every windup correctly.
    # The keys are fixed rather than derived because that is what a player
    # types: the sequence is what reading this troll's habits looks like.
    scripted(monkeypatch, ["4", "3", "5", *"jddsdjd", "q"])
    assert (
        main(
            [
                "play",
                "packs",
                "--pack",
                "peasants-quest",
                "--combat",
                "tactical",
                "--seed",
                "mace",
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "Fighting: Gorm" in printed
    assert "Clean counter" in printed
    assert "You are still standing." in printed


def test_the_counter_matrix_is_shown_before_the_first_swing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The training wheels stay on until somebody builds a way to take them off."""
    scripted(monkeypatch, ["4", "3", "5", "q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "tactical"]) == 0
    )
    printed = capsys.readouterr().out
    assert "overhead   beaten by dodge" in printed


def test_an_exchange_says_why_it_went_that_way(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Attribution is what turns an outcome into learning."""
    scripted(monkeypatch, ["4", "3", "5", "p", "q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "tactical"]) == 0
    )
    printed = capsys.readouterr().out
    assert "you misread it" in printed


def test_a_fight_does_not_repeat_the_status_line_every_exchange(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`combat.resolve` already says what an exchange cost. Both still fire."""
    scripted(monkeypatch, ["4", "3", "5", "d", "d", "d", "q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "tactical"]) == 0
    )
    printed = capsys.readouterr().out
    fight = printed[printed.index("Fighting: Gorm") :]
    assert "The Old Bridge · " not in fight


def test_an_unknown_answer_is_explained_rather_than_taken(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["4", "3", "5", "z", "q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "tactical"]) == 0
    )
    assert "One of: dodge" in capsys.readouterr().out


def test_auto_mode_needs_no_answers_at_all(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted(monkeypatch, ["4", "3", "5", "q"])
    assert main(["play", "packs", "--pack", "peasants-quest", "--combat", "auto"]) == 0
    printed = capsys.readouterr().out
    assert "Fighting: Gorm" in printed
    assert "stamina" not in printed[printed.index("Fighting: Gorm") :]


def test_a_terminal_that_cannot_time_says_so_rather_than_faking_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A window that is secretly unfair is worse than no window at all."""
    monkeypatch.setattr("mace.cli.play.raw_terminal_available", lambda: False)
    scripted(monkeypatch, ["q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "reflex"]) == 0
    )
    assert "playing combat untimed" in capsys.readouterr().out


def test_keys_are_bound_without_content_naming_one() -> None:
    """A move's key would be presentation leaking into content."""
    bound = keys_for([("dodge", "dodge"), ("block", "block"), ("parry", "parry")])
    assert {key: response for key, (response, _label) in bound.items()} == {
        "d": "dodge",
        "b": "block",
        "p": "parry",
    }


def test_a_taken_letter_falls_through_to_the_next_one() -> None:
    bound = keys_for([("strike", "strike"), ("shove", "shove")])
    assert bound["s"][0] == "strike"
    assert bound["h"][0] == "shove"


def test_a_key_is_bound_from_the_label_not_the_protocol_name() -> None:
    """`use:fantasy.core:bread` is called Bread, and `b` is what you press."""
    bound = keys_for([("use:fantasy.core:bread", "Bread")])
    assert bound["b"] == ("use:fantasy.core:bread", "Bread")


def test_every_response_gets_a_key_even_when_the_letters_run_out() -> None:
    bound = keys_for([("aa", "aa"), ("aa", "aa"), ("aa", "aa")])
    assert len(bound) == 3


def test_a_timed_window_records_what_it_measured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one place a wall clock reaches the engine, as a recorded number."""
    presses = [Keypress("d", 4500), Keypress("d", 4500), Keypress(None, 1000)]

    def press(_window: int, **_kwargs: object) -> Keypress:
        return presses.pop(0) if presses else Keypress("q", 10)

    monkeypatch.setattr("mace.cli.play.raw_terminal_available", lambda: True)
    monkeypatch.setattr("mace.cli.play.read_key", press)
    scripted(monkeypatch, ["4", "3", "5", "q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "reflex"]) == 0
    )
    printed = capsys.readouterr().out
    assert "Clean counter" in printed
    assert "(too slow)" in printed


def test_movement_rides_along_with_a_timed_answer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A keypress's `move_by` reaches the action, and the distance printed moves."""
    presses = [Keypress("d", 900, 2.0)]

    def press(_window: int, **_kwargs: object) -> Keypress:
        return presses.pop(0) if presses else Keypress("q", 10)

    monkeypatch.setattr("mace.cli.play.raw_terminal_available", lambda: True)
    monkeypatch.setattr("mace.cli.play.read_key", press)
    scripted(monkeypatch, ["4", "3", "5", "q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "reflex"]) == 0
    )
    printed = capsys.readouterr().out
    distances = [float(d) for d in re.findall(r"distance ([\d.]+)ft", printed)]
    assert len(distances) >= 2
    assert distances[1] != distances[0]


def test_movement_rides_along_with_an_untimed_answer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A trailing `+N`/`-N` on the typed line moves before the answer resolves."""
    scripted(monkeypatch, ["4", "3", "5", "dodge +2", "q"])
    assert (
        main(["play", "packs", "--pack", "peasants-quest", "--combat", "tactical"]) == 0
    )
    printed = capsys.readouterr().out
    distances = [float(d) for d in re.findall(r"distance ([\d.]+)ft", printed)]
    assert len(distances) >= 2
    assert distances[1] != distances[0]


# ── Starting a pack ───────────────────────────────────────────────────────────


def test_new_creates_a_pack(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "new",
                str(tmp_path / "my-world"),
                "--requires",
                "--packs",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert (tmp_path / "my-world" / "pack.yml").is_file()
    assert "created" in capsys.readouterr().out


def test_new_names_the_pack_after_its_directory(tmp_path: Path) -> None:
    main(["new", str(tmp_path / "my-world"), "--requires", "--packs", str(tmp_path)])
    assert Project.open(tmp_path / "my-world").manifest.id == "my-world"


def test_new_warns_when_a_required_pack_is_not_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """It is still required, so the author needs to know now rather than later."""
    assert (
        main(
            [
                "new",
                str(tmp_path / "my-world"),
                "--requires",
                "fantasy.core",
                "--packs",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert "was not found" in capsys.readouterr().err


def test_new_refuses_to_overwrite_a_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["new", str(tmp_path / "my-world"), "--requires", "--packs", str(tmp_path)]
    assert main(args) == 0
    assert main(args) == 1
    assert "already a pack" in capsys.readouterr().err


def test_new_reports_an_unusable_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "new",
                str(tmp_path / "world"),
                "--id",
                "Not A Valid Id",
                "--requires",
                "--packs",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert "error" in capsys.readouterr().err


def test_a_new_pack_validates_as_far_as_an_empty_game_can(tmp_path: Path) -> None:
    """Empty is not the same as broken, and the difference should be legible."""
    main(["new", str(tmp_path / "my-world"), "--requires", "--packs", str(tmp_path)])
    report = validate_paths(tmp_path / "my-world")
    assert [problem.message for problem in report.errors] == [
        "is a game pack but has no `game:` manifest"
    ]


def exported(tmp_path: Path) -> Path:
    """A pack archive, written the way `mace author`'s export writes one.

    Parameters
    ----------
    tmp_path : Path
        Pytest's directory.

    Returns
    -------
    Path
        The archive.
    """
    root = write_pack(
        tmp_path / "mine",
        "gift",
        kind="game",
        files={
            "world.yml": {
                "locations": [
                    {"id": "home", "name": "Home", "exits": [{"to": "castle"}]},
                    {"id": "castle", "name": "The Castle", "exits": [{"to": "home"}]},
                ],
                "entities": [
                    {
                        "id": "hero",
                        "kind": "actor",
                        "name": "Hero",
                        "playable": True,
                        "stats": {
                            "hitpoints": {"base": 10, "max": 10},
                            "stamina": {"base": 10, "max": 10},
                        },
                    }
                ],
            },
            "game.yml": {
                "game": {
                    "name": "A Gift",
                    "player": {"entity": "hero", "startLocation": "home"},
                    "winConditions": [{"atLocation": {"location": "castle"}}],
                }
            },
        },
    )
    return export_pack(Project.open(root, root.parent), tmp_path / "post")


def test_import_opens_a_pack_somebody_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = exported(tmp_path)
    assert main(["import", str(archive), "--packs", str(tmp_path / "packs")]) == 0

    assert "opened" in capsys.readouterr().out
    assert (tmp_path / "packs" / "gift" / "game.yml").is_file()
    assert validate_paths(tmp_path / "packs" / "gift").ok


def test_import_refuses_to_overwrite_a_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Quietly replacing somebody's work is not a thing a tool does on a keystroke."""
    archive = exported(tmp_path)
    where = ["--packs", str(tmp_path / "packs")]
    assert main(["import", str(archive), *where]) == 0
    assert main(["import", str(archive), *where]) == 1
    assert "is already at" in capsys.readouterr().err
    assert main(["import", str(archive), *where, "--force"]) == 0


def test_import_refuses_something_that_is_not_a_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    holiday = tmp_path / "holiday.zip"
    holiday.write_bytes(b"PK not really")

    assert main(["import", str(holiday), "--packs", str(tmp_path / "packs")]) == 1
    assert "is not a MACE pack" in capsys.readouterr().err


def test_import_says_what_is_wrong_with_what_it_opened(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The wizard's export cannot write a broken pack. Somebody's hand-made zip
    can, and finding out at `mace play` time would be finding out too late."""
    archive = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive, "w") as writing:
        writing.writestr(
            "pack.yml",
            json.dumps(
                {
                    "id": "broken",
                    "name": "Broken",
                    "version": "0.1.0",
                    "kind": "game",
                    "maceVersion": "^0.1",
                }
            ),
        )
        writing.writestr("world.yml", json.dumps({"locations": [{"id": "here"}]}))

    assert main(["import", str(archive), "--packs", str(tmp_path / "packs")]) == 1
    assert (tmp_path / "packs" / "broken").is_dir()  # it is still on disk
    assert "error" in capsys.readouterr().err


def test_import_does_not_call_a_missing_dependency_the_packs_fault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pack that builds on `fantasy.core` is not broken for being read alone.

    So the check runs against the packs directory it landed in, which is
    where what it `requires` would be — and reports only the imported pack's
    own problems, because the author's other packs are not what they opened.
    """
    write_pack(tmp_path / "packs", "fantasy.core")
    archive = tmp_path / "leaning.zip"
    with zipfile.ZipFile(archive, "w") as writing:
        writing.writestr(
            "pack.yml",
            json.dumps(
                {
                    "id": "leaning",
                    "name": "Leaning",
                    "version": "0.1.0",
                    "kind": "library",
                    "maceVersion": "^0.1",
                    "requires": [{"id": "fantasy.core", "version": "^0.1"}],
                }
            ),
        )

    assert main(["import", str(archive), "--packs", str(tmp_path / "packs")]) == 0
    assert capsys.readouterr().err == ""
