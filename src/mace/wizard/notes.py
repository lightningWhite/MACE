"""The authoring sidecar: what the wizard remembers that content cannot.

Open question 8 settled the shape — **the wizard edits YAML packs directly**,
with authoring metadata in `.mace/project.yml` inside the pack. The YAML stays
canonical and hand-editable at all times, which matters for a git-based
community, and there is no second format to drift out of sync.

What belongs here is what is true about the *work* rather than about the world:
which sections the author considers finished, what they left themselves a note
about, and what they last playtested with. What does not belong here is
anything a player could observe — map positions are `mapPosition` on a
location, because where a place sits on the map is part of the world.
"""

from __future__ import annotations

from pydantic import Field

from mace.model.base import ContentModel

__all__ = ["FORMAT_VERSION", "Note", "PlaytestSetup", "ProjectNotes"]

#: The sidecar's own version, so a later wizard can migrate an older one.
FORMAT_VERSION = 1


class Note(ContentModel):
    """Something the author left themselves.

    Attributes
    ----------
    about : str
        What it concerns, as `collection/id` — `locations/troll-bridge`. Free
        text rather than a reference, because a note about something you have
        not created yet is exactly the kind of note people write.
    text : str
        The note.
    """

    about: str = ""
    text: str


class PlaytestSetup(ContentModel):
    """What the author last started a playtest with.

    Remembered because iterating means running the same awkward corner of the
    world twenty times, and retyping "the bridge, at midnight, in a blizzard"
    twenty times is how people stop iterating.

    Attributes
    ----------
    seed : str
        The session seed. Fixed by default, so a change in the pack is the
        only variable that changed.
    start_location : str or None
        Where to begin, overriding the game's own start.
    start_tick : int or None
        When to begin.
    combat_mode : str or None
        Which combat presentation to use.
    """

    seed: str = "mace"
    start_location: str | None = None
    start_tick: int | None = Field(default=None, ge=0)
    combat_mode: str | None = None


class ProjectNotes(ContentModel):
    """The contents of `.mace/project.yml`, under its `project:` key.

    Attributes
    ----------
    format_version : int
        The sidecar format.
    completed : tuple of str
        Ids of the sections the author has marked done. Advisory: nothing
        stops them editing a finished section, and nothing requires them to
        finish one before starting another. That is the point of a task list
        rather than an interview.
    notes : tuple of Note
        What they left themselves.
    playtest : PlaytestSetup
        The last playtest setup.
    """

    format_version: int = FORMAT_VERSION
    completed: tuple[str, ...] = ()
    notes: tuple[Note, ...] = ()
    playtest: PlaytestSetup = PlaytestSetup()
