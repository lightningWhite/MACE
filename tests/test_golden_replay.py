"""Golden replay: a seed plus an action log produces exactly this event stream.

This is the contract ADR-0004 exists to buy. It is what would let a TypeScript
port of the engine be checked against the Python one, and what catches a change
in simulation behaviour that no unit test thought to ask about.

A golden file records the packs and their versions, the seed, the actions, and
every event they produced. If a change legitimately alters one, regenerate it
and **say so in the commit message** — an unremarked golden change is a
behaviour change nobody reviewed.

    MACE_UPDATE_GOLDEN=1 pytest tests/test_golden_replay.py
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from mace.content import Library, load_library
from mace.engine.actions import decode
from mace.engine.step import begin, step

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

    for record in recording["actions"]:
        result = step(result.state, decode(record), library)
        stream.append({"action": record, "events": result.records()})
    return stream


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
