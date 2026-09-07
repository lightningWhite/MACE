"""Playtest from anywhere, with the world set up however you need it.

The single most important feature for keeping an author engaged, and the one
the v0 wizard could not offer at all: nothing was playable until everything
was done. Here, a session starts from the project **as it is in memory** —
unsaved changes included, half-finished objects dropped with a note rather
than a crash — at whatever point in the world the author wants to look at.

    Start me at the Troll Bridge, at midnight, in a blizzard, with a rope.

Every part of that is a session-opening parameter, the way the seed is. The
seed itself defaults to something fixed, because while you are iterating the
*content* should be the only thing that changed between two runs.

The two halves the engine cannot take as arguments — the weather and the extra
kit — are applied to the opening state rather than smuggled into content. The
weather is set and then left to the simulation, so "in a blizzard" means the
blizzard is happening now and will pass in its own time, which is the thing
worth testing.
"""

from __future__ import annotations

from mace.content import ContentError, Library
from mace.engine.creation import Character
from mace.engine.step import StepResult, begin, context_for
from mace.wizard.notes import PlaytestSetup
from mace.wizard.project import Project

__all__ = ["OPENING_INTENSITY", "start", "start_from"]

#: How hard a weather condition an author asks for comes on. Middling-strong:
#: an author testing "in a blizzard" wants the blizzard to bite, and pinning it
#: at 1.0 would be testing the extreme rather than the weather.
OPENING_INTENSITY = 0.6


def start_from(project: Project, setup: PlaytestSetup) -> tuple[StepResult, Library]:
    """Open a session on the project as it stands, unsaved changes included.

    Parameters
    ----------
    project : Project
        The pack being authored.
    setup : PlaytestSetup
        Where and how to begin.

    Returns
    -------
    tuple of (StepResult, Library)
        The opening step and the library it was compiled from — the caller
        needs both, because every later `step` takes the same library.

    Raises
    ------
    ContentError
        If the project is not a playable game, or the setup names something
        that does not exist.
    """
    loaded = project.compile()
    return start(loaded.library, project.manifest.id, setup), loaded.library


def start(library: Library, pack_id: str, setup: PlaytestSetup) -> StepResult:
    """Open a session set up the way an author asked for.

    Parameters
    ----------
    library : Library
        The compiled content.
    pack_id : str
        Which game.
    setup : PlaytestSetup
        Where and how to begin.

    Returns
    -------
    StepResult
        The opening state and everything it produced.

    Raises
    ------
    ContentError
        If the setup names something that does not exist.
    """
    character = None
    if setup.background or setup.spend:
        character = Character(background=setup.background, spend=dict(setup.spend))

    result = begin(
        library,
        pack_id,
        seed=setup.seed,
        combat_mode=setup.combat_mode,
        character=character,
        start_at=setup.start_location,
        start_tick=setup.start_tick,
    )

    _stock(library, pack_id, result, setup)
    _sky(library, pack_id, result, setup)
    return result


def _stock(
    library: Library, pack_id: str, result: StepResult, setup: PlaytestSetup
) -> None:
    """Put the author's extra kit into the protagonist's hands.

    Parameters
    ----------
    library : Library
        The compiled content.
    pack_id : str
        The game pack, which the references resolve against.
    result : StepResult
        The opening step, whose state is stocked in place.
    setup : PlaytestSetup
        The setup.

    Raises
    ------
    ContentError
        If an item reference names nothing.
    """
    player = result.state.protagonist
    for reference, qty in setup.items.items():
        item = library.resolve(reference, "entities", within=pack_id)
        player.inventory[item] = player.inventory.get(item, 0) + int(qty)


def _sky(
    library: Library, pack_id: str, result: StepResult, setup: PlaytestSetup
) -> None:
    """Make the weather be what the author wanted to look at.

    Set rather than pinned: the condition is in force now and the region's own
    chain carries on from it, so a blizzard behaves like a blizzard that
    started a moment ago rather than like a permanent fixture. Testing what
    happens *when it lifts* is half of why you asked for it.

    Parameters
    ----------
    library : Library
        The compiled content.
    pack_id : str
        The game pack.
    result : StepResult
        The opening step, whose state is adjusted in place.
    setup : PlaytestSetup
        The setup.

    Raises
    ------
    ContentError
        If the weather reference names nothing, or there is no region here to
        apply it to.
    """
    if setup.weather is None:
        return
    condition = library.resolve(setup.weather, "weatherConditions", within=pack_id)
    state = result.state
    here = context_for(library, state).weather().region
    if here is None or here not in state.weather:
        raise ContentError(
            "there is no region here to put weather in — give the start "
            "location a `region`, or set `game.world.startRegion`",
            pack=pack_id,
        )

    sky = state.weather[here]
    sky.condition = condition
    sky.intensity = OPENING_INTENSITY
    sky.began_at_tick = state.tick
    sky.sequence = None
