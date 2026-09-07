"""The task list: what is done, what is half-done, and what is wrong.

The top level of the wizard is a **task list, not an interview**. You can work
on anything in any order, leave things half-finished, and come back — which is
how hobby projects actually get built, and the opposite of the v0 wizard's
recursive walk that could not be backed out of.

    A PEASANT'S QUEST                            ▸ 4 problems   ▸ 62% complete

      ✓  Game setup            name, intro, win/lose         complete
      ◐  World map             6 locations, 5 routes          2 places have no way out
      ◐  Characters            4 defined                      `captain` has no scenes
      ✓  Items                 9 defined
      ○  Weather & climate     using fantasy.core defaults

Everything on that screen is computed here, from two sources: what the project
holds, and what the validator says about it. Nothing is cached — a task list is
cheap and an out-of-date one is worse than none, because the whole point is
that it tells the truth about a pack somebody may have hand-edited between
sessions.

Completion is advisory in both directions. A section counts as done when it
holds something and has no errors; an author can also mark one done themselves
and the wizard believes them. Nothing blocks anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mace.content.validation import Problem, Report, Severity
from mace.wizard.flows import FLOWS, GAME
from mace.wizard.project import Project

__all__ = ["Section", "SECTIONS", "State", "Task", "TaskList", "review"]


class State(Enum):
    """How far along one section is."""

    EMPTY = "empty"
    STARTED = "started"
    DONE = "done"

    @property
    def mark(self) -> str:
        """The character that stands for this state in a list.

        Returns
        -------
        str
            `○`, `◐`, or `✓`.
        """
        return {"empty": "○", "started": "◐", "done": "✓"}[self.value]


@dataclass(frozen=True, slots=True)
class Section:
    """One heading on the task list.

    Sections are groupings of *work*, which is why they do not map one-to-one
    onto collections: an author thinks "the world map" and means locations,
    routes, and regions together, and thinks "characters" and "items" about
    two halves of one collection.

    Attributes
    ----------
    id : str
        Stable, and what the sidecar records as completed.
    title : str
        The heading.
    collections : tuple of str
        Which content it covers.
    where : mapping
        A filter narrowing a collection — `{"kind": "item"}`.
    flow : str or None
        The flow that authors it, when one does.
    noun : tuple of str
        Singular and plural for what this section counts, when the collection
        name is the wrong word for it. A section over `entities` filtered to
        actors counts *characters*, and telling an author they have "5
        entities" is telling them about the model rather than their world.
    help : str
        A sentence about what belongs here.
    """

    id: str
    title: str
    collections: tuple[str, ...] = ()
    where: Mapping[str, Any] | None = None
    flow: str | None = None
    noun: tuple[str, str] | None = None
    help: str = ""


#: The task list, in the order an author usually gets to them. Game setup
#: first because everything else refers to it; the world before the people in
#: it, because a person with nowhere to stand is harder to think about than an
#: empty village.
SECTIONS: tuple[Section, ...] = (
    Section(
        id="game",
        title="Game setup",
        flow="game",
        help="The title, the opening, who the player is, and what winning means.",
    ),
    Section(
        id="world",
        title="World map",
        collections=("locations", "routes", "regions"),
        flow="locations",
        help="Places, the roads between them, and the regions weather happens to.",
    ),
    Section(
        id="characters",
        title="Characters",
        collections=("entities",),
        where={"kind": "actor"},
        flow="entities",
        noun=("character", "characters"),
        help="Everyone the player can talk to, fight, or travel with.",
    ),
    Section(
        id="items",
        title="Items",
        collections=("entities",),
        where={"kind": "item"},
        flow="entities",
        noun=("item", "items"),
        help="Everything the player can carry, wear, or spend.",
    ),
    Section(
        id="scenes",
        title="Scenes",
        collections=("scenes",),
        flow="scenes",
        help="Every conversation, every choice, every ending.",
    ),
    Section(
        id="quests",
        title="Quests",
        collections=("quests",),
        flow="quests",
        help="What the player is doing, in stages, with a journal.",
    ),
    Section(
        id="encounters",
        title="Encounters",
        collections=("encounterTables",),
        help="What the roads might throw at somebody walking down them.",
    ),
    Section(
        id="weather",
        title="Weather & climate",
        collections=("climates", "weatherConditions", "weatherFronts", "terrains"),
        help=(
            "Usually a library's job. A game that defines none of these takes "
            "the ones its dependencies bring."
        ),
    ),
    Section(
        id="player",
        title="Player setup",
        collections=("backgrounds",),
        flow="backgrounds",
        help="Who the protagonist could have been, and what they get to choose.",
    ),
)


@dataclass(frozen=True, slots=True)
class Task:
    """One line of the task list.

    Attributes
    ----------
    section : Section
        What it covers.
    state : State
        How far along it is.
    summary : str
        What it holds — `6 locations, 5 routes`.
    problems : tuple of Problem
        Everything the validator said about this section, worst first.
    """

    section: Section
    state: State
    summary: str
    problems: tuple[Problem, ...] = ()

    @property
    def note(self) -> str:
        """The one thing worth saying about this section on a crowded screen.

        Returns
        -------
        str
            The worst problem's message, or an empty string.
        """
        return self.problems[0].message if self.problems else ""

    @property
    def errors(self) -> int:
        """How many of this section's problems break the game.

        Returns
        -------
        int
            The error count.
        """
        return sum(1 for one in self.problems if one.severity is Severity.ERROR)


@dataclass(frozen=True, slots=True)
class TaskList:
    """The whole screen.

    Attributes
    ----------
    name : str
        What the pack is called.
    tasks : tuple of Task
        One per section, in order.
    report : Report
        Everything the validator found, including whatever no section claimed.
    """

    name: str
    tasks: tuple[Task, ...]
    report: Report

    @property
    def percent(self) -> int:
        """How much of the work is done, as a share of the sections.

        Deliberately crude. A progress number that tried to be precise would
        be a number an author argued with, and the useful signal is only ever
        "most of it" or "barely started".

        Returns
        -------
        int
            0 to 100.
        """
        if not self.tasks:
            return 0  # pragma: no cover — SECTIONS is never empty
        done = sum(1 for task in self.tasks if task.state is State.DONE)
        return round(done * 100 / len(self.tasks))

    @property
    def problems(self) -> int:
        """How many problems there are in total.

        Returns
        -------
        int
            The count across every severity.
        """
        return len(self.report.problems)

    @property
    def errors(self) -> int:
        """How many of them break the game.

        Returns
        -------
        int
            The error count.
        """
        return sum(1 for one in self.report.problems if one.severity is Severity.ERROR)

    def task(self, section_id: str) -> Task:
        """One task by its section id.

        Parameters
        ----------
        section_id : str
            The section.

        Returns
        -------
        Task
            The task.

        Raises
        ------
        KeyError
            If there is no such section.
        """
        for task in self.tasks:
            if task.section.id == section_id:
                return task
        raise KeyError(f"no section `{section_id}`")


def review(project: Project) -> TaskList:
    """Work out where a project stands, right now.

    Parameters
    ----------
    project : Project
        The open pack.

    Returns
    -------
    TaskList
        The whole screen: every section, its state, and its problems.
    """
    report = project.report()
    claimed: dict[str, list[Problem]] = {section.id: [] for section in SECTIONS}
    for problem in report.problems:
        owner = _owner(problem)
        if owner is not None:
            claimed[owner].append(problem)

    return TaskList(
        name=_name_of(project),
        tasks=tuple(
            _task(project, section, tuple(_worst_first(claimed[section.id])))
            for section in SECTIONS
        ),
        report=report,
    )


def _task(project: Project, section: Section, problems: tuple[Problem, ...]) -> Task:
    """Build one line of the list.

    Parameters
    ----------
    project : Project
        The open pack.
    section : Section
        What it covers.
    problems : tuple of Problem
        Its problems, worst first.

    Returns
    -------
    Task
        The task.
    """
    if section.id == "game":
        return _game_task(project, section, problems)

    counts = _counts(project, section)
    held = sum(counts.values())

    if project.notes and section.id in project.notes.completed:
        return Task(section, State.DONE, _summarise(section, counts), problems)
    if not held:
        return Task(section, State.EMPTY, _nothing_yet(section), problems)

    errors = any(one.severity is Severity.ERROR for one in problems)
    unfinished = _unfinished(project, section)
    state = State.STARTED if errors or unfinished else State.DONE
    summary = _summarise(section, counts)
    if unfinished:
        summary = f"{summary} — {unfinished} unfinished"
    return Task(section, state, summary, problems)


def _game_task(
    project: Project, section: Section, problems: tuple[Problem, ...]
) -> Task:
    """The game-setup line, which counts steps rather than objects.

    Parameters
    ----------
    project : Project
        The open pack.
    section : Section
        The game section.
    problems : tuple of Problem
        Its problems.

    Returns
    -------
    Task
        The task.
    """
    if project.game is None:
        return Task(section, State.EMPTY, "not started", problems)
    waiting = GAME.unanswered(project)
    errors = any(one.severity is Severity.ERROR for one in problems)
    if waiting:
        titles = ", ".join(step.binding.leaf for step in waiting[:3])
        more = f", +{len(waiting) - 3} more" if len(waiting) > 3 else ""
        return Task(section, State.STARTED, f"still needs {titles}{more}", problems)
    if errors:
        return Task(section, State.STARTED, "answered, but not yet right", problems)
    return Task(section, State.DONE, "name, opening, player, win and lose", problems)


def _counts(project: Project, section: Section) -> dict[str, int]:
    """How many things this section holds, per collection.

    Parameters
    ----------
    project : Project
        The open pack.
    section : Section
        The section.

    Returns
    -------
    dict
        Collection to count, omitting the empty ones.
    """
    from mace.wizard.query import Catalog, Query

    catalog = Catalog(project)
    counts: dict[str, int] = {}
    for collection in section.collections:
        query = Query(collection, scope="project", where=section.where or {})
        found = len(query.options(catalog))
        if found:
            counts[collection] = found
    return counts


def _unfinished(project: Project, section: Section) -> int:
    """How many of this section's objects still have a required step blank.

    Parameters
    ----------
    project : Project
        The open pack.
    section : Section
        The section.

    Returns
    -------
    int
        The count, or 0 when nothing authors this section.
    """
    flow = FLOWS.get(section.flow or "")
    if flow is None or flow.collection is None:
        return 0
    from mace.wizard.query import Catalog, Query

    mine = Query(flow.collection, scope="project", where=section.where or {})
    return sum(
        1
        for option in mine.options(Catalog(project))
        if flow.unanswered(project, option.value)
    )


def _summarise(section: Section, counts: Mapping[str, int]) -> str:
    """Say what a section holds, in the words an author would use.

    Parameters
    ----------
    section : Section
        The section, for its own noun where it has one.
    counts : mapping
        Collection to count.

    Returns
    -------
    str
        `6 locations, 5 routes`.
    """
    parts = []
    for collection, count in counts.items():
        one, many = section.noun or _nouns(collection)
        parts.append(f"{count} {one if count == 1 else many}")
    return ", ".join(parts) or "nothing yet"


def _nouns(collection: str) -> tuple[str, str]:
    """What one and several of a collection are called.

    The plural comes from the collection key itself rather than from a rule:
    `entities` is already the plural of `entity`, and no rule that turns one
    into the other is worth writing.

    Parameters
    ----------
    collection : str
        The collection name, in camelCase.

    Returns
    -------
    tuple of (str, str)
        Singular and plural.
    """
    from mace.content.library import SINGULAR

    spaced = "".join(
        f" {letter.lower()}" if letter.isupper() else letter for letter in collection
    )
    return SINGULAR.get(collection, spaced), spaced


def _nothing_yet(section: Section) -> str:
    """What to say about a section with nothing in it.

    Parameters
    ----------
    section : Section
        The section.

    Returns
    -------
    str
        A phrase saying whether that is a gap or a choice.
    """
    if section.id == "weather":
        return "using whatever the libraries bring"
    return "nothing yet"


def _owner(problem: Problem) -> str | None:
    """Which section a problem belongs to.

    Parameters
    ----------
    problem : Problem
        The problem.

    Returns
    -------
    str or None
        A section id, or None when no section covers it.
    """
    if problem.collection in {None, "game"}:
        return "game"
    for section in SECTIONS:
        if problem.collection in section.collections and section.where is None:
            return section.id
    # Entities are split across two sections and a problem does not say which
    # half it is about. Characters is the better default: an item's problems
    # are usually about the character carrying it.
    if problem.collection == "entities":
        return "characters"
    return None


def _worst_first(problems: Sequence[Problem]) -> list[Problem]:
    """Order problems so the one worth reading is first.

    Parameters
    ----------
    problems : sequence of Problem
        The problems.

    Returns
    -------
    list of Problem
        Errors, then warnings, then notes, stable within each.
    """
    order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.NOTE: 2}
    return sorted(problems, key=lambda one: order[one.severity])


def _name_of(project: Project) -> str:
    """What to call the pack at the top of the screen.

    Parameters
    ----------
    project : Project
        The open pack.

    Returns
    -------
    str
        The game's title where it has one, else the pack's name.
    """
    game = project.game
    if isinstance(game, Mapping) and game.get("name"):
        return str(game["name"])
    return project.manifest.name
