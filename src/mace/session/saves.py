"""Saves: the packs, the seed, and everything the player did.

A save is not a photograph of the world. It is the recipe that produced it —
which packs and at which versions, the seed, the answers given at character
creation, and the ordered log of actions. Replaying that triple against the
same content rebuilds the playthrough exactly, which is what ADR-0004 is for.

It buys three things a snapshot would not. Saves are tiny and diffable, so they
fit in a bug report and read as prose. Sharing one shares an exact playthrough,
so "watch how I beat the troll" works. And a save that no longer fits its
content says so, at the action where it stopped fitting, with the menu that was
on offer — instead of loading into a world that quietly went somewhere else.

The price is that loading replays. That is cheap now and will not always be:
docs/10-clients-and-interface.md describes a periodic state snapshot alongside
the log, as an optimization and never the source of truth. It is not written
yet, and until it is, two things are true — a long playthrough reloads by
re-simulating itself, and a save whose content has moved under it cannot be
continued past the divergence, only reported.

See docs/10-clients-and-interface.md § Saves.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mace.content import ContentError, Library
from mace.engine.creation import Character
from mace.session.session import Session, choose_game

__all__ = ["FORMAT", "Save", "SaveError", "load", "read", "resume", "write"]

#: The save-file format. Bumped when a reader would get an old file wrong —
#: not when a field is added that an old reader can ignore.
FORMAT = 1


class SaveError(ContentError):
    """A save could not be read, or could not be replayed into a session."""


@dataclass(frozen=True, slots=True)
class Save:
    """A playthrough written down.

    Attributes
    ----------
    pack : str
        The game pack that was played.
    seed : str
        The session seed.
    packs : mapping
        Pack id to the version that was loaded when the save was written. Not
        used to *find* content — it is what lets a load say "this pack has
        moved since you saved" rather than diverging in silence.
    actions : tuple of dict
        Every action, in order, in recorded form. Choices are named by prompt.
    combat_mode : str or None
        The combat presentation the session opened with.
    character : Character or None
        What the player answered at character creation.
    start_at : str or None
        Where the session opened, when that was not the game's own start.
    start_tick : int or None
        The tick it opened on, when that was not zero.
    """

    pack: str
    seed: str
    packs: Mapping[str, str] = field(default_factory=dict)
    actions: tuple[dict[str, Any], ...] = ()
    combat_mode: str | None = None
    character: Character | None = None
    start_at: str | None = None
    start_tick: int | None = None

    @classmethod
    def of(cls, session: Session) -> Save:
        """Write a running session down.

        Parameters
        ----------
        session : Session
            The playthrough to record.

        Returns
        -------
        Save
            The recipe that reproduces it.
        """
        return cls(
            pack=session.pack,
            seed=session.seed,
            packs={
                pack.id: str(pack.manifest.version) for pack in session.library.packs
            },
            actions=tuple(dict(record) for record in session.log),
            combat_mode=session.combat_mode,
            character=session.character,
            start_at=session.start_at,
            start_tick=session.start_tick,
        )

    def record(self) -> dict[str, Any]:
        """The save as it goes on disk.

        Returns
        -------
        dict
            JSON-safe values, camelCase like everything else a person reads.
        """
        written: dict[str, Any] = {
            "format": FORMAT,
            "pack": self.pack,
            "seed": self.seed,
            "packs": {name: self.packs[name] for name in sorted(self.packs)},
        }
        if self.combat_mode is not None:
            written["combatMode"] = self.combat_mode
        if self.character is not None:
            written["character"] = {
                "background": self.character.background,
                "spend": {
                    stat: self.character.spend[stat]
                    for stat in sorted(self.character.spend)
                },
            }
        if self.start_at is not None:
            written["startAt"] = self.start_at
        if self.start_tick is not None:
            written["startTick"] = self.start_tick
        written["actions"] = [dict(record) for record in self.actions]
        return written

    @classmethod
    def restore(cls, record: Mapping[str, Any]) -> Save:
        """Read a save back from its record.

        Parameters
        ----------
        record : mapping
            What `record` wrote.

        Returns
        -------
        Save
            The save.

        Raises
        ------
        SaveError
            If the format is one this engine does not read, or the record is
            missing something a save cannot do without.
        """
        found = record.get("format", FORMAT)
        if not isinstance(found, int) or found > FORMAT:
            raise SaveError(
                f"this save is format {found}; this engine reads format {FORMAT}. "
                "A newer MACE wrote it."
            )
        if "pack" not in record:
            raise SaveError("this save does not say which game it is of")

        made = record.get("character")
        actions = record.get("actions") or []
        if not isinstance(actions, list):
            raise SaveError("a save's `actions` must be a list of action records")

        return cls(
            pack=str(record["pack"]),
            seed=str(record.get("seed", "mace")),
            packs={
                str(name): str(v) for name, v in (record.get("packs") or {}).items()
            },
            actions=tuple(dict(entry) for entry in actions),
            combat_mode=record.get("combatMode"),
            character=(
                None
                if made is None
                else Character(
                    background=made.get("background"),
                    spend=dict(made.get("spend") or {}),
                )
            ),
            start_at=record.get("startAt"),
            start_tick=record.get("startTick"),
        )


def write(session: Session, path: Path) -> Path:
    """Save a session to a file.

    Parameters
    ----------
    session : Session
        The playthrough.
    path : Path
        Where to write it.

    Returns
    -------
    Path
        The path written.

    Raises
    ------
    SaveError
        If the file cannot be written.
    """
    record = Save.of(session).record()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise SaveError(f"could not write the save to {path}: {error}") from error
    return path


def read(path: Path) -> Save:
    """Read a save from a file.

    Parameters
    ----------
    path : Path
        The save file.

    Returns
    -------
    Save
        The save.

    Raises
    ------
    SaveError
        If the file is missing, unreadable, or not a save.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SaveError(f"could not read the save at {path}: {error}") from error
    try:
        record = json.loads(text)
    except json.JSONDecodeError as error:
        raise SaveError(f"{path} is not a save file: {error}") from error
    if not isinstance(record, dict):
        raise SaveError(f"{path} is not a save file: it is not an object")
    return Save.restore(record)


def resume(save: Save, library: Library) -> tuple[Session, list[str]]:
    """Replay a save into a running session.

    Parameters
    ----------
    save : Save
        The recorded playthrough.
    library : Library
        The loaded content to replay it against.

    Returns
    -------
    tuple of (Session, list of str)
        The session, standing exactly where the save left it, and anything
        worth telling the player about how it got there — a pack that has
        changed version since, most likely.

    Raises
    ------
    SaveError
        If the game pack is not loaded, or an action no longer means anything,
        which is what content changing under a save looks like.
    """
    warnings = _drifted(save, library)

    try:
        session = Session.begin(
            library,
            choose_game(library, save.pack),
            seed=save.seed,
            combat_mode=save.combat_mode,
            character=save.character,
            start_at=save.start_at,
            start_tick=save.start_tick,
        )
    except ContentError as error:
        raise SaveError(f"this save cannot be opened: {error}") from error

    for number, record in enumerate(save.actions, start=1):
        try:
            session.replay(record)
        except ValueError as error:
            raise SaveError(
                f"this save stops making sense at action {number} "
                f"({record.get('kind', 'unknown')}). The content it was made "
                f"against has changed.\n{error}"
            ) from error
    return session, warnings


def load(path: Path, library: Library) -> tuple[Session, list[str]]:
    """Read a save and replay it, in one step.

    Parameters
    ----------
    path : Path
        The save file.
    library : Library
        The loaded content.

    Returns
    -------
    tuple of (Session, list of str)
        The session and anything worth saying about the load.

    Raises
    ------
    SaveError
        If the save cannot be read or cannot be replayed.
    """
    return resume(read(path), library)


def _drifted(save: Save, library: Library) -> list[str]:
    """Say which packs have moved since the save was written.

    A version change is not an error — most of them change nothing a save
    touches. It is the first thing worth knowing when a replay then fails, and
    the only warning available before it does.

    Parameters
    ----------
    save : Save
        The recorded playthrough.
    library : Library
        What is loaded now.

    Returns
    -------
    list of str
        One line per pack that is missing or at a different version, in id
        order.
    """
    loaded = {pack.id: str(pack.manifest.version) for pack in library.packs}
    drifted = []
    for name in sorted(save.packs):
        was = save.packs[name]
        now = loaded.get(name)
        if now is None:
            drifted.append(f"`{name}` {was} is not loaded now")
        elif now != was:
            drifted.append(f"`{name}` was {was} when this was saved, and is now {now}")
    return drifted
