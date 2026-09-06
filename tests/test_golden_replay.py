"""Golden replay: a seed plus an action log produces exactly this event stream.

This is the contract ADR-0004 exists to buy. It is what would let a TypeScript
port of the engine be checked against the Python one, and what catches a change
in simulation behaviour that no unit test thought to ask about.

A golden file records the packs and their versions, the seed, the actions, and
every event they produced. If a change legitimately alters one, regenerate it
and **say so in the commit message** — an unremarked golden change is a
behaviour change nobody reviewed.

    MACE_UPDATE_GOLDEN=1 pytest tests/test_golden_replay.py

Actions are recorded by the **prompt** of the option they took, not by its
index. An index is what the engine takes and the wrong thing to write down: the
moment an author inserts a menu entry above the one a recording meant, an
index-based log still replays, down a different road, and nothing says so — it
just produces a different event stream, which reads as an engine regression.
A prompt fails loudly instead, with the menu that was actually on offer in the
message, and the fix is obvious.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from mace.content import Library, load_library
from mace.engine.actions import decode
from mace.engine.step import StepResult, begin, step

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKS = REPO_ROOT / "packs"
GOLDEN = Path(__file__).resolve().parent / "golden"


def replay(library: Library, recording: dict[str, Any]) -> list[dict[str, Any]]:
    """Run a recording's actions and collect everything that happened.

    Parameters
    ----------
    library : Library
        The loaded packs.
    recording : dict
        A golden file's contents.

    Returns
    -------
    list of dict
        The event records, in order, with the action that caused each batch.
    """
    result = begin(library, recording["pack"], seed=recording["seed"])
    stream: list[dict[str, Any]] = [{"action": None, "events": result.records()}]

    for number, record in enumerate(recording["actions"], start=1):
        try:
            action = decode(record, offered=offered(result))
        except ValueError as error:
            raise AssertionError(
                f"{recording['name']}: action {number} cannot be taken.\n{error}"
            ) from error
        result = step(result.state, action, library)
        stream.append({"action": record, "events": result.records()})
    return stream


def offered(result: StepResult) -> list[str]:
    """The prompts a step left on offer, in order.

    Parameters
    ----------
    result : StepResult
        The step just taken.

    Returns
    -------
    list of str
        The option prompts, or an empty list when nothing is pending.
    """
    pending = result.state.pending
    if pending is None:
        return []
    return [option.prompt for option in pending.options]


def pack_versions(library: Library) -> dict[str, str]:
    """The version of every loaded pack.

    A golden file that does not say which content produced it cannot be
    trusted when it fails: the engine and the packs are both variables.

    Parameters
    ----------
    library : Library
        The loaded packs.

    Returns
    -------
    dict
        Pack id to version, sorted.
    """
    return {pack.id: pack.manifest.version for pack in library.packs}


def golden_files() -> list[Path]:
    """Every recorded playthrough.

    Returns
    -------
    list of Path
        Sorted paths, so failures are reported in a stable order.
    """
    return sorted(GOLDEN.glob("*.json"))


@pytest.mark.parametrize("path", golden_files(), ids=lambda p: p.stem)
def test_replay_matches_the_recording(path: Path) -> None:
    recording = json.loads(path.read_text())
    library = load_library(PACKS)
    actual = replay(library, recording)
    versions = pack_versions(library)

    if os.environ.get("MACE_UPDATE_GOLDEN"):  # pragma: no cover — a tool, not a test
        recording["packs"] = versions
        recording["stream"] = actual
        path.write_text(json.dumps(recording, indent=2) + "\n")
        pytest.skip(f"regenerated {path.name}")

    assert versions == recording["packs"], (
        "the packs that produced this recording have changed version; "
        "regenerate with MACE_UPDATE_GOLDEN=1 and say so in the commit"
    )
    assert actual == recording["stream"], (
        f"{path.name} replayed differently. If the change is intended, "
        "regenerate with MACE_UPDATE_GOLDEN=1 and say so in the commit message."
    )


def test_there_are_recordings_to_replay() -> None:
    """Guard against the whole contract silently covering nothing."""
    assert golden_files(), f"no golden recordings under {GOLDEN}"


def test_replaying_twice_gives_the_same_answer() -> None:
    """Determinism, checked directly rather than only through the files."""
    library = load_library(PACKS)
    recording = json.loads(golden_files()[0].read_text())
    assert replay(library, recording) == replay(library, recording)


def test_recordings_name_their_choices_rather_than_numbering_them() -> None:
    """The format is the point: a number is not a thing you can write down.

    Without this, the next person to add a menu entry gets a golden diff that
    looks like an engine regression instead of an error naming the option that
    moved.
    """
    for path in golden_files():
        recording = json.loads(path.read_text())
        for number, record in enumerate(recording["actions"], start=1):
            if record["kind"] != "choose":
                continue
            assert "prompt" in record, (
                f"{path.name} action {number} is recorded as an index. "
                "Record the option's prompt instead."
            )
            assert "option" not in record


def test_a_choice_that_no_longer_exists_says_so_clearly() -> None:
    """The failure a moved menu entry should produce."""
    library = load_library(PACKS)
    recording = json.loads(golden_files()[0].read_text())
    broken = dict(recording)
    broken["actions"] = [{"kind": "choose", "prompt": "Ask the goose for directions"}]

    with pytest.raises(AssertionError) as caught:
        replay(library, broken)
    message = str(caught.value)
    assert "Ask the goose for directions" in message
    assert "These were:" in message
