"""The wizard in a terminal.

Everything this module knows is how to *render*. The questions, the pickers,
the cascades, the task list and the problem list all come from `mace.wizard`
as data, and the web client will render the same objects into forms. A step
type is added there, not here.

Four screens, and you can leave any of them:

    the task list  →  a section  →  one object  →  one step

Nothing blocks. A section can be left half-done, an object can be left without
a name, and the game can be played at any point in any of it. Saving is
explicit and always allowed, because an author must be able to stop
mid-thought (docs/09-authoring-and-wizard.md).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, TextIO

from mace.cli.play import Renderer, choose, fight
from mace.cli.timing import raw_terminal_available
from mace.content import ContentError
from mace.content.validation import Severity
from mace.engine.debug import Overlay, overlay
from mace.engine.state import Outcome
from mace.engine.step import step
from mace.wizard.builders import (
    CONDITIONS,
    EFFECTS,
    Ask,
    Recipe,
    build_condition,
    build_effect,
)
from mace.wizard.fields import (
    ConditionBuilder,
    EffectBuilder,
    Field,
    Invalid,
    MultiSelect,
    Repeat,
    Select,
    StatAllocator,
    TextList,
)
from mace.wizard.flow import Flow, Step, answered
from mace.wizard.flows import FLOWS, GAME
from mace.wizard.generators import FLAVOURS, PRESETS, SIZES, start_world, suggest_table
from mace.wizard.language import Names, say_conditions
from mace.wizard.notes import Note, PlaytestSetup, ProjectNotes
from mace.wizard.playtest import start_from
from mace.wizard.project import Project
from mace.wizard.query import Catalog, Option
from mace.wizard.tasks import Task, TaskList, review

__all__ = ["author"]

RULE = "─" * 72

#: Which sections have scaffolding to offer, and what to call it.
_GENERATORS = {"world": "starter map", "encounters": "suggest a table"}

#: How the three severities are marked in a problem list.
MARKS = {Severity.ERROR: "✗", Severity.WARNING: "!", Severity.NOTE: "·"}


class Leave(Exception):
    """The author asked to go back a screen."""


class Stop(Exception):
    """The author asked to close the wizard."""


@dataclass(slots=True)
class Wizard:
    """One authoring session.

    Attributes
    ----------
    project : Project
        The pack being edited.
    out : TextIO
        Where to write.
    interactive : bool
        Whether there is anybody there to answer.
    """

    project: Project
    out: TextIO
    interactive: bool = True
    _catalog: Catalog | None = field(default=None, init=False)

    @property
    def catalog(self) -> Catalog:
        """What exists, for the pickers.

        Returns
        -------
        Catalog
            The catalog over this project.
        """
        if self._catalog is None:
            self._catalog = Catalog(self.project)
        return self._catalog

    # ── Writing ───────────────────────────────────────────────────────────

    def say(self, text: str = "") -> None:
        """Write one line.

        Parameters
        ----------
        text : str
            The line.
        """
        print(text, file=self.out)

    def ask(self, prompt: str = "> ") -> str:
        """Read one answer.

        Parameters
        ----------
        prompt : str
            What to show.

        Returns
        -------
        str
            The trimmed answer.

        Raises
        ------
        Stop
            If there is nobody there — a closed input ends the session rather
            than looping forever on an empty answer.
        """
        print(f"\n{prompt}", end="", file=self.out, flush=True)
        try:
            return input("").strip()
        except (EOFError, KeyboardInterrupt):
            self.say("")
            raise Stop from None

    def problem_lines(self, problems: Sequence[Any], limit: int = 8) -> None:
        """Print a problem list.

        Parameters
        ----------
        problems : sequence of Problem
            What is wrong.
        limit : int
            How many to show before saying there are more.
        """
        for problem in problems[:limit]:
            where = problem.object_id or problem.collection or ""
            mark = MARKS[problem.severity]
            self.say(f"    {mark} {where + ': ' if where else ''}{problem.message}")
        if len(problems) > limit:
            self.say(f"    … and {len(problems) - limit} more")

    # ── The task list ─────────────────────────────────────────────────────

    def home(self) -> None:
        """Show the task list and act on what the author picks.

        Raises
        ------
        Stop
            When the author is done.
        """
        while True:
            listed = review(self.project)
            self._task_list(listed)
            typed = self.ask().lower()

            if typed in {"q", "quit", "exit"}:
                self._quit()
                return
            if typed in {"s", "save"}:
                self._save()
                continue
            if typed in {"v", "validate"}:
                self._validate(listed)
                continue
            if typed in {"p", "play", "playtest"}:
                self._playtest()
                continue
            if typed in {"n", "note"}:
                self._note()
                continue
            if typed.isdigit() and 1 <= int(typed) <= len(listed.tasks):
                try:
                    self.section(listed.tasks[int(typed) - 1])
                except Leave:
                    continue
                continue
            self.say("  A number, or one of p / v / s / n / q.")

    def _task_list(self, listed: TaskList) -> None:
        """Draw the task list.

        Parameters
        ----------
        listed : TaskList
            What to draw.
        """
        problems = (
            "no problems"
            if not listed.problems
            else f"{listed.problems} problem{'' if listed.problems == 1 else 's'}"
        )
        unsaved = "  ▸ unsaved changes" if self.project.dirty else ""
        self.say("")
        self.say(RULE)
        self.say(
            f"  {listed.name.upper()}"
            f"      ▸ {problems}   ▸ {listed.percent}% complete{unsaved}"
        )
        self.say(RULE)
        self.say("")
        for number, task in enumerate(listed.tasks, start=1):
            self.say(
                f"  {number:>2}. {task.state.mark}  {task.section.title:<20}"
                f"{_short(task.summary, 38):<40}{_short(task.note, 46)}"
            )
        self.say("")
        self.say("      [p] playtest   [v] validate   [s] save   [n] note   [q] quit")

    # ── A section ─────────────────────────────────────────────────────────

    def section(self, task: Task) -> None:
        """Show one section's contents and act on what the author picks.

        Parameters
        ----------
        task : Task
            The section.

        Raises
        ------
        Leave
            When the author goes back.
        Stop
            When the author is done.
        """
        if task.section.id == "game":
            self.object_screen(GAME, None)
            raise Leave

        kinds = [
            collection for collection in task.section.collections if collection in FLOWS
        ]
        while True:
            listed = self._objects(task)
            self.say("")
            self.say(f"  {task.section.title.upper()} — {task.section.help}")
            self.say("")
            if not listed:
                self.say("    nothing here yet")
            for number, (collection, option) in enumerate(listed, start=1):
                self.say(
                    f"  {number:>2}. {_short(option.label, 30):<32}{option.value}"
                    f"{'' if len(kinds) < 2 else f'   ({_local(collection)})'}"
                )
            if task.problems:
                self.say("")
                self.problem_lines(task.problems)
            self.say("")
            actions = "[b] back" if not kinds else "[n] new   [d] delete   [b] back"
            if task.section.id in _GENERATORS:
                actions = f"[g] {_GENERATORS[task.section.id]}   {actions}"
            if not kinds:
                self.say("      This one is hand-written for now — no flow yet.")
            self.say(f"      {actions}")

            typed = self.ask().lower()
            if typed in {"b", "back", ""}:
                raise Leave
            if typed in {"q", "quit"}:
                raise Stop
            if typed in {"g", "generate"} and task.section.id in _GENERATORS:
                self._generate(task.section.id)
                continue
            if kinds and typed in {"n", "new"}:
                chosen = self._which_kind(kinds)
                if chosen is not None:
                    created = self._create(FLOWS[chosen], task)
                    if created is not None:
                        self._edit(FLOWS[chosen], created)
                continue
            if kinds and typed in {"d", "delete"}:
                self._delete(listed)
                continue
            if typed.isdigit() and 1 <= int(typed) <= len(listed):
                collection, option = listed[int(typed) - 1]
                if collection not in FLOWS:
                    self.say("  That one is hand-written for now.")
                    continue
                self._edit(FLOWS[collection], option.value)
                continue
            self.say("  A number, or one of n / d / b.")

    def _objects(self, task: Task) -> list[tuple[str, Option]]:
        """What one section currently holds, and which collection each is in.

        A section is a grouping of work rather than of collections — the world
        map is places, roads, and regions together — so an object has to carry
        the collection it came from, or picking it opens the wrong flow.

        Parameters
        ----------
        task : Task
            The section.

        Returns
        -------
        list of tuple
            Collection and object, in the order they are offered.
        """
        from mace.wizard.query import Query

        found: list[tuple[str, Option]] = []
        for collection in task.section.collections:
            query = Query(collection, scope="project", where=task.section.where or {})
            found.extend((collection, option) for option in query.options(self.catalog))
        return found

    def _which_kind(self, kinds: Sequence[str]) -> str | None:
        """Ask which of a section's collections a new object belongs to.

        Parameters
        ----------
        kinds : sequence of str
            The collections this section can create in.

        Returns
        -------
        str or None
            The collection, or None if the author backed out.

        Raises
        ------
        Stop
            When the author is done.
        """
        if len(kinds) == 1:
            return kinds[0]
        for number, collection in enumerate(kinds, start=1):
            self.say(f"      {number:>2}. a new {FLOWS[collection].noun}")
        typed = self.ask("Which kind?  ")
        if typed.isdigit() and 1 <= int(typed) <= len(kinds):
            return kinds[int(typed) - 1]
        return None

    def _edit(self, flow: Flow, object_id: str) -> None:
        """Open one object, coming back to the section afterwards.

        Parameters
        ----------
        flow : Flow
            Which flow builds it.
        object_id : str
            The object.

        Raises
        ------
        Stop
            When the author is done.
        """
        try:
            self.object_screen(flow, object_id)
        except Leave:
            return

    def _create(self, flow: Flow, task: Task) -> str | None:
        """Ask for a new object's id and put an empty one in the project.

        An object has to exist before anything can point at it, and it has to
        be pointable-at long before it is finished — so this asks the least it
        can and gets out of the way.

        Parameters
        ----------
        flow : Flow
            Which flow builds it.
        task : Task
            The section it is being made in, for the fields that section fixes.

        Returns
        -------
        str or None
            The new object's local id, or None if the author backed out.

        Raises
        ------
        Stop
            When the author is done.
        """
        assert flow.collection is not None
        name = self.ask(f"What is the new {flow.noun} called?  ")
        if not name:
            return None
        local_id = _slug(name)
        if local_id in self.project.ids(flow.collection):
            self.say(f"  There is already a `{local_id}`.")
            return None

        authored: dict[str, Any] = {"id": local_id}
        if any(step.binding.leaf == "name" for step in flow.steps):
            authored["name"] = name
        for key, value in (task.section.where or {}).items():
            authored[key] = value
        self.project.put(flow.collection, authored)
        self.say(f"  Made `{local_id}`.")
        return local_id

    def _delete(self, listed: Sequence[tuple[str, Option]]) -> None:
        """Remove an object, once.

        Parameters
        ----------
        listed : sequence of tuple
            What is on the screen, so a number means the same thing here.

        Raises
        ------
        Stop
            When the author is done.
        """
        typed = self.ask("Delete which number?  ")
        if not typed.isdigit() or not 1 <= int(typed) <= len(listed):
            self.say("  Nothing deleted.")
            return
        collection, chosen = listed[int(typed) - 1]
        sure = self.ask(
            f"Delete {chosen.label}? Anything pointing at it breaks. [y/N] "
        )
        if sure.lower() not in {"y", "yes"}:
            self.say("  Nothing deleted.")
            return
        self.project.drop(collection, chosen.value)
        self.say(f"  Deleted `{chosen.value}`. Validate to see what it broke.")

    def _generate(self, section_id: str) -> None:
        """Offer the scaffolding for one section.

        Always editable and never mandatory: what comes back is ordinary
        content, written into the author's own files, which they are expected
        to rearrange. Nothing here happens during a session.

        Parameters
        ----------
        section_id : str
            Which section asked.

        Raises
        ------
        Stop
            When the author is done.
        """
        if section_id == "world":
            self._starter_map()
        else:
            self._suggest_table()

    def _starter_map(self) -> None:
        """Make a map to rearrange instead of a blank page.

        Raises
        ------
        Stop
            When the author is done.
        """
        self.say("")
        for number, flavour in enumerate(FLAVOURS, start=1):
            self.say(f"      {number:>2}. {flavour.label}")
        typed = self.ask("Which one?  ")
        if not typed.isdigit() or not 1 <= int(typed) <= len(FLAVOURS):
            self.say("  Nothing generated.")
            return
        flavour = FLAVOURS[int(typed) - 1]

        size = self.ask(f"How big? {'/'.join(SIZES)} [small]  ").lower() or "small"
        if size not in SIZES:
            self.say(f"  `{size}` is not a size. Nothing generated.")
            return
        seed = self.ask("Seed — change it to get a different map [mace]  ") or "mace"
        climate = self._a_climate()

        made = start_world(
            self.project, flavour=flavour.id, size=size, seed=seed, climate=climate
        )
        if not made:
            self.say("  Everything it would have made is already here.")
            return
        for one in made:
            self.say(f"    + {one}")
        self.say("")
        self.say("  Rename all of it. It is a shape, not a world.")

    def _a_climate(self) -> str | None:
        """Ask which climate the new regions should use, if any is on offer.

        Returns
        -------
        str or None
            The climate reference, or None to leave the regions weatherless.

        Raises
        ------
        Stop
            When the author is done.
        """
        from mace.wizard.query import Query

        offered = Query("climates").options(self.catalog)
        if not offered:
            return None
        self.say("")
        for number, option in enumerate(offered, start=1):
            self.say(f"      {number:>2}. {option.label}   ({option.note})")
        typed = self.ask("Which climate? [blank for none]  ")
        if typed.isdigit() and 1 <= int(typed) <= len(offered):
            return offered[int(typed) - 1].value
        return None

    def _suggest_table(self) -> None:
        """Propose an encounter table from the presets and the libraries.

        Raises
        ------
        Stop
            When the author is done.
        """
        self.say("")
        for number, preset in enumerate(PRESETS, start=1):
            self.say(
                f"      {number:>2}. {preset.label:<26}"
                f"something happens {preset.chance:.0%} of the time, "
                f"{preset.threat_share:.0%} of it dangerous"
            )
        typed = self.ask("How does this road feel?  ")
        if not typed.isdigit() or not 1 <= int(typed) <= len(PRESETS):
            self.say("  Nothing generated.")
            return
        preset = PRESETS[int(typed) - 1]

        name = self.ask("What is the table called?  ")
        if not name:
            return
        local_id = _slug(name)
        if self.project.get("encounterTables", local_id) is not None:
            self.say(f"  There is already a `{local_id}`.")
            return

        table = suggest_table(self.project, local_id=local_id, name=name, preset=preset)
        self.project.put("encounterTables", table)
        if not table.get("entries"):
            self.say(
                "  Nothing in your libraries to draw entries from, so it is "
                "switched off. Write some scenes and turn its `chance` up."
            )
            return
        self.say(f"  Made `{local_id}` with {len(table['entries'])} entries.")
        self.say("  Retune it — the `chance` is the one dial that matters.")

    # ── One object ────────────────────────────────────────────────────────

    def object_screen(self, flow: Flow, object_id: str | None) -> None:
        """Show one object's steps and act on what the author picks.

        Parameters
        ----------
        flow : Flow
            Which flow builds it.
        object_id : str or None
            The object, or None for the game manifest.

        Raises
        ------
        Leave
            When the author goes back.
        Stop
            When the author is done.
        """
        while True:
            self.say("")
            title = flow.title if object_id is None else f"{flow.title} — {object_id}"
            self.say(f"  {title.upper()}")
            self.say("")
            steps = list(flow.steps)
            for number, one in enumerate(steps, start=1):
                value = one.read(self.project, object_id)
                mark = " " if answered(value) or one.optional else "·"
                described = one.field.describe(value, self.catalog)
                self.say(f"  {number:>2}.{mark} {one.title:<44}{_short(described)}")
            self.say("")
            self.say("      [b] back")

            typed = self.ask().lower()
            if typed in {"b", "back", ""}:
                raise Leave
            if typed in {"q", "quit"}:
                raise Stop
            if typed.isdigit() and 1 <= int(typed) <= len(steps):
                self._answer(steps[int(typed) - 1], object_id)
                continue
            self.say("  A number, or `b` to go back.")

    def _answer(self, one: Step, object_id: str | None) -> None:
        """Ask one step and record the answer.

        Parameters
        ----------
        one : Step
            The step.
        object_id : str or None
            Which object.

        Raises
        ------
        Stop
            When the author is done.
        """
        self.say("")
        self.say(f"  {one.title}")
        if one.help:
            for line in _wrap(one.help):
                self.say(f"    {line}")
        current = one.read(self.project, object_id)
        if answered(current):
            self.say(f"    now: {one.field.describe(current, self.catalog)}")

        try:
            value = self._collect(one.field, current)
        except Leave:
            return
        try:
            one.write(self.project, value, object_id)
        except ContentError as error:
            self.say(f"    ! {error}")
            return
        self.say(f"    ✓ {one.field.describe(value, self.catalog)}")

    def _collect(self, one: Field, current: Any) -> Any:
        """Get a value for one field, however that field is answered.

        Parameters
        ----------
        one : Field
            The field.
        current : object
            What it holds now.

        Returns
        -------
        object
            The new value.

        Raises
        ------
        Leave
            If the author backed out.
        Stop
            When the author is done.
        """
        if isinstance(one, TextList):
            return self._lines(current)
        if isinstance(one, ConditionBuilder):
            return self._conditions(one, current)
        if isinstance(one, EffectBuilder):
            return self._effects(current)
        if isinstance(one, Repeat):
            return self._repeat(one, current)
        if isinstance(one, StatAllocator):
            return self._statblock(one, current)
        return self._typed(one)

    def _typed(self, one: Field) -> Any:
        """Read a one-line answer, showing the options where there are any.

        Parameters
        ----------
        one : Field
            The field.

        Returns
        -------
        object
            The parsed value.

        Raises
        ------
        Leave
            If the author backed out.
        Stop
            When the author is done.
        """
        offered: tuple[Option, ...] = ()
        creates: str | None = None
        if isinstance(one, Select | MultiSelect):
            offered = one.options.options(self.catalog)
            creates = one.allow_create
            for number, option in enumerate(offered, start=1):
                note = f"   ({option.note})" if option.note else ""
                self.say(f"      {number:>2}. {option.label}{note}")
            if creates:
                self.say(f"      {len(offered) + 1:>2}. + a new one")
        hint = one.hint(self.catalog)
        self.say(
            f"    ({hint}; `-` leaves it alone)"
            if hint
            else "    (`-` leaves it alone)"
        )

        while True:
            typed = self.ask()
            if typed.lower() in {"-", "back"}:
                raise Leave
            if creates and typed == str(len(offered) + 1):
                made = self._create_inline(creates)
                if made is None:
                    continue
                return [made] if isinstance(one, MultiSelect) else made
            try:
                return one.parse(typed, self.catalog)
            except Invalid as error:
                self.say(f"    {error}")

    def _create_inline(self, collection: str) -> str | None:
        """Make a new object without leaving the question that needed it.

        This is what stops an author having to abandon a half-finished scene
        to go and define the item they just realised it needs.

        Parameters
        ----------
        collection : str
            What to create.

        Returns
        -------
        str or None
            The new object's id, or None if they backed out.

        Raises
        ------
        Stop
            When the author is done.
        """
        flow = FLOWS.get(collection)
        if flow is None:
            self.say(f"    Nothing here can make a {collection} yet.")
            return None
        name = self.ask(f"What is the new {flow.noun} called?  ")
        if not name:
            return None
        local_id = _slug(name)
        authored: dict[str, Any] = {"id": local_id}
        if any(step.binding.leaf == "name" for step in flow.steps):
            authored["name"] = name
        self.project.put(collection, authored)
        self.say(f"    ✓ made `{local_id}` — fill it in from its own section.")
        return local_id

    def _lines(self, current: Any) -> list[Any]:
        """Collect a list of lines, one at a time.

        Parameters
        ----------
        current : object
            What is there now, which is offered as the starting point.

        Returns
        -------
        list
            The lines.

        Raises
        ------
        Stop
            When the author is done.
        """
        kept: list[Any] = list(current or [])
        if kept:
            for number, line in enumerate(kept, start=1):
                self.say(f"      {number:>2}. {_line_text(line)}")
            if self.ask("Keep these and add to them? [Y/n] ").lower() in {"n", "no"}:
                kept = []
        self.say("    One line at a time. A blank line ends it.")
        while True:
            typed = self.ask("  + ")
            if not typed:
                return kept
            kept.append(typed)

    def _statblock(self, one: StatAllocator, current: Any) -> dict[str, Any]:
        """Collect named numbers, against a budget where there is one.

        Parameters
        ----------
        one : StatAllocator
            The field.
        current : object
            What is there now.

        Returns
        -------
        dict
            Stat name to its authored entry.

        Raises
        ------
        Stop
            When the author is done.
        """
        kept: dict[str, Any] = dict(current or {})
        if one.points:
            self.say(f"    {one.points} points to spread.")
        self.say("    A name and a number — `strength 32`. A blank line ends it.")
        while True:
            typed = self.ask("  + ")
            if not typed:
                return kept
            name, _, number = typed.partition(" ")
            try:
                value: float = float(number)
            except ValueError:
                self.say("    A name and a number, like `strength 32`.")
                continue
            existing = kept.get(name)
            if isinstance(existing, Mapping):
                kept[name] = {**existing, "base": value}
            else:
                kept[name] = {"base": value}
            self.say(f"    ✓ {name} {number}")

    def _conditions(self, one: ConditionBuilder, current: Any) -> Any:
        """Build conditions with the guided cascade.

        Parameters
        ----------
        one : ConditionBuilder
            The field, which says whether it holds one or several.
        current : object
            What is there now.

        Returns
        -------
        object
            The authored condition, or list of them.

        Raises
        ------
        Stop
            When the author is done.
        """
        kept = self._cascade(current, CONDITIONS, "condition", one.single)
        if one.single:
            return kept[0] if kept else None
        return kept

    def _effects(self, current: Any) -> list[Any]:
        """Build effects with the guided cascade.

        Parameters
        ----------
        current : object
            What is there now.

        Returns
        -------
        list
            The authored effects, in order.

        Raises
        ------
        Stop
            When the author is done.
        """
        return self._cascade(current, EFFECTS, "effect", False)

    def _cascade(
        self, current: Any, recipes: tuple[Recipe, ...], noun: str, single: bool
    ) -> list[Any]:
        """The shared add / remove loop over a vocabulary of recipes.

        Parameters
        ----------
        current : object
            What is there now.
        recipes : tuple of Recipe
            Which vocabulary.
        noun : str
            `condition` or `effect`.
        single : bool
            Whether only one is wanted.

        Returns
        -------
        list
            The authored mappings.

        Raises
        ------
        Stop
            When the author is done.
        """
        kept = list(_as_list(current))
        names = Names(self.project.dependencies, self.project.manifest.id, self.catalog)
        while True:
            self.say("")
            for number, one in enumerate(kept, start=1):
                self.say(f"      {number:>2}. {_said(one, noun, names)}")
            if not kept:
                self.say(
                    f"      (no {noun}s — that means `always`)"
                    if noun == "condition"
                    else "      (nothing happens)"
                )
            self.say("")
            self.say("      [a] add   [r] remove   [d] done")
            typed = self.ask().lower()
            if typed in {"d", "done", ""}:
                return kept[:1] if single and kept else kept
            if typed in {"r", "remove"} and kept:
                which = self.ask("Remove which number?  ")
                if which.isdigit() and 1 <= int(which) <= len(kept):
                    kept.pop(int(which) - 1)
                continue
            if typed in {"a", "add"}:
                made = self._one(recipes, noun)
                if made is not None:
                    kept.append(made)
                    if single:
                        return [made]
                continue
            self.say("      One of a / r / d.")

    def _one(self, recipes: tuple[Recipe, ...], noun: str) -> Any:
        """Ask which recipe, then ask that recipe's questions.

        Parameters
        ----------
        recipes : tuple of Recipe
            The vocabulary.
        noun : str
            `condition` or `effect`.

        Returns
        -------
        object or None
            The authored mapping, or None if the author backed out.

        Raises
        ------
        Stop
            When the author is done.
        """
        self.say("")
        self.say(
            "    What should this depend on?"
            if noun == "condition"
            else "    What should happen?"
        )
        heading = ""
        for number, recipe in enumerate(recipes, start=1):
            if recipe.group != heading:
                heading = recipe.group
                self.say(f"      — {heading}")
            self.say(f"      {number:>2}. {recipe.label}")

        typed = self.ask()
        if not typed.isdigit() or not 1 <= int(typed) <= len(recipes):
            self.say("      Nothing added.")
            return None
        recipe = recipes[int(typed) - 1]
        if recipe.help:
            for line in _wrap(recipe.help):
                self.say(f"      {line}")

        answers: dict[str, Any] = {}
        for ask in recipe.asks:
            self.say("")
            self.say(f"    {ask.title}")
            if ask.help:
                for line in _wrap(ask.help):
                    self.say(f"      {line}")
            if ask.default is not None:
                self.say(f"      (blank for {_shown(ask.default)})")
            try:
                answers[ask.key] = self._collect(_askable(ask), None)
            except Leave:
                return None

        build = build_condition if noun == "condition" else build_effect
        try:
            return build(recipe, answers)
        except ValueError as error:
            self.say(f"      ! that is not a valid {noun}: {_first_line(error)}")
            return None

    def _repeat(self, one: Repeat, current: Any) -> list[Any]:
        """Collect a list of sub-objects, each built by its own little flow.

        Parameters
        ----------
        one : Repeat
            The field.
        current : object
            What is there now.

        Returns
        -------
        list
            The entries.

        Raises
        ------
        Stop
            When the author is done.
        """
        kept = list(_as_list(current))
        while True:
            self.say("")
            for number, entry in enumerate(kept, start=1):
                self.say(f"      {number:>2}. {_entry(entry)}")
            if not kept:
                self.say(f"      (no {one.of}s yet)")
            self.say("")
            self.say("      [a] add   [r] remove   [d] done")
            typed = self.ask().lower()
            if typed in {"d", "done", ""}:
                return kept
            if typed in {"r", "remove"} and kept:
                which = self.ask("Remove which number?  ")
                if which.isdigit() and 1 <= int(which) <= len(kept):
                    kept.pop(int(which) - 1)
                continue
            if typed in {"a", "add"}:
                entry = self._entry_fields(one)
                if entry:
                    kept.append(entry)
                continue
            self.say("      One of a / r / d.")

    def _entry_fields(self, one: Repeat) -> dict[str, Any]:
        """Ask a repeat entry's own questions.

        Parameters
        ----------
        one : Repeat
            The field, whose `steps` describe one entry.

        Returns
        -------
        dict
            The entry, with the keys the author answered.

        Raises
        ------
        Stop
            When the author is done.
        """
        entry: dict[str, Any] = {}
        for sub in one.steps:
            assert isinstance(sub, Step)
            self.say("")
            self.say(f"    {sub.title}")
            if sub.help:
                for line in _wrap(sub.help):
                    self.say(f"      {line}")
            try:
                value = self._collect(sub.field, None)
            except Leave:
                return entry
            if answered(value):
                entry[sub.binding.leaf] = value
        return entry

    # ── The actions on the bottom row ─────────────────────────────────────

    def _save(self) -> None:
        """Write every changed file, and say which."""
        try:
            written = self.project.save()
        except OSError as error:  # pragma: no cover — a full disk, a bad mount
            self.say(f"  ! could not save: {error}")
            return
        if not written:
            self.say("  Nothing had changed.")
            return
        for path in written:
            self.say(f"  wrote {path}")

    def _validate(self, listed: TaskList) -> None:
        """Show the whole problem list.

        Parameters
        ----------
        listed : TaskList
            The review that produced it.
        """
        self.say("")
        if not listed.report.problems:
            self.say("  Nothing wrong with it.")
            return
        self.problem_lines(listed.report.problems, limit=40)
        self.say("")
        self.say(
            f"  {listed.errors} error(s). Errors stop it running; "
            "they never stop you saving."
        )

    def _note(self) -> None:
        """Leave a note about something, including something that does not exist yet.

        Raises
        ------
        Stop
            When the author is done.
        """
        about = self.ask("About what? (`locations/troll-bridge`, or blank)  ")
        text = self.ask("The note:  ")
        if not text:
            return
        notes = self.project.notes
        self.project.remember(
            ProjectNotes(
                format_version=notes.format_version,
                completed=notes.completed,
                notes=(*notes.notes, Note(about=about, text=text)),
                playtest=notes.playtest,
            )
        )
        self.say("  Noted.")

    def _playtest(self) -> None:
        """Set a session up and play it, unsaved changes included.

        Raises
        ------
        Stop
            When the author is done.
        """
        setup = self._setup(self.project.notes.playtest)
        notes = self.project.notes
        self.project.remember(
            ProjectNotes(
                format_version=notes.format_version,
                completed=notes.completed,
                notes=notes.notes,
                playtest=setup,
            )
        )

        try:
            result, library = start_from(self.project, setup)
        except ContentError as error:
            self.say(f"  ! it will not start: {error}")
            return

        self.say("")
        self.say(RULE)
        renderer = Renderer(self.out, interactive=self.interactive)
        renderer.show(result.events)
        timed = raw_terminal_available() and result.state.combat_mode == "reflex"

        while result.state.outcome is Outcome.PLAYING:
            if setup.debug:
                self._overlay(overlay(library, result.state))
            combat = result.state.combat
            if combat is not None and combat.tell is not None:
                action = fight(renderer, result, timed)
            else:
                action = choose(renderer, result)
            if action is None:
                break
            result = step(result.state, action, library)
            renderer.show(result.events)

        self.say("")
        self.say(RULE)
        self.say("  Back to the wizard.")

    def _setup(self, remembered: PlaytestSetup) -> PlaytestSetup:
        """Ask where and how to start, offering what was used last time.

        Parameters
        ----------
        remembered : PlaytestSetup
            The last setup, which is nearly always the one wanted again.

        Returns
        -------
        PlaytestSetup
            The setup to use.

        Raises
        ------
        Stop
            When the author is done.
        """
        self.say("")
        self.say(f"  Playtest — last time: {_setup_line(remembered)}")
        self.say("      [enter] the same again   [c] change it")
        if self.ask().lower() not in {"c", "change"}:
            return remembered

        from mace.wizard.query import Query

        def pick(collection: str, prompt: str, now: str | None) -> str | None:
            offered = Query(collection).options(self.catalog)
            self.say("")
            for number, option in enumerate(offered, start=1):
                self.say(f"      {number:>2}. {option.label}   ({option.note})")
            typed = self.ask(f"{prompt} [{now or 'the game start'}]  ")
            if not typed:
                return now
            if typed == "-":
                return None
            if typed.isdigit() and 1 <= int(typed) <= len(offered):
                return offered[int(typed) - 1].value
            return typed

        seed = self.ask(f"Seed [{remembered.seed}]  ") or remembered.seed
        where = pick("locations", "Start where?", remembered.start_location)
        tick = self.ask(f"Start tick [{remembered.start_tick or 'the game start'}]  ")
        sky = pick("weatherConditions", "In what weather?", remembered.weather)
        kit = self.ask("Extra items, as `rope 1, dagger 1`  ")
        debug = self.ask("Show the debug overlay? [y/N]  ").lower() in {"y", "yes"}

        return PlaytestSetup(
            seed=seed,
            start_location=where,
            start_tick=int(tick) if tick.isdigit() else remembered.start_tick,
            weather=sky,
            items=_kit(kit) if kit else dict(remembered.items),
            background=remembered.background,
            spend=dict(remembered.spend),
            combat_mode=remembered.combat_mode,
            debug=debug,
        )

    def _overlay(self, seen: Overlay) -> None:
        """Draw the debug overlay.

        Parameters
        ----------
        seen : Overlay
            What the engine is thinking.
        """
        names = Names(self.project.dependencies, self.project.manifest.id, self.catalog)
        self.say("")
        self.say(
            f"  ┊ tick {seen.tick} · day {seen.day} {seen.day_part} {seen.season}"
            f" · {_local(seen.location)} · {seen.weather}"
        )
        for tested in seen.conditions:
            mark = "✓" if tested.holds else "✗"
            said = say_conditions(tested.when, names)
            trouble = f"  ! {tested.error}" if tested.error else ""
            self.say(f"  ┊ {mark} {tested.subject}: {said}{trouble}")
        for modifier in seen.modifiers:
            parts = []
            if modifier.add:
                parts.append(f"{modifier.add:+.2f}")
            if modifier.mult != 1.0:
                parts.append(f"×{modifier.mult:.2f}")
            lapses = (
                "" if modifier.expires_in is None else f", {modifier.expires_in}t left"
            )
            self.say(
                f"  ┊ ~ {modifier.stat} {' '.join(parts) or 'no change'}"
                f" ({modifier.label or modifier.source}{lapses})"
            )
        for table in seen.tables:
            since = "never" if table.ticks_since is None else f"{table.ticks_since} ago"
            self.say(
                f"  ┊ ⚄ {_local(table.table)} pressure {table.pressure:+.3f}"
                f" · fired {table.fired} · last {since}"
            )
        if seen.flags:
            self.say(f"  ┊ ⚑ {', '.join(seen.flags)}")
        if seen.streams:
            drawn = " ".join(f"{_local(n)}:{p}" for n, p in seen.streams)
            self.say(f"  ┊ ⚂ {drawn}")

    def _quit(self) -> None:
        """Offer to save on the way out.

        Raises
        ------
        Stop
            Never — quitting is the one thing that always works.
        """
        if not self.project.dirty:
            self.say("\n  Until next time.")
            return
        files = ", ".join(str(path) for path in sorted(self.project.dirty))
        if self.ask(f"Save {files} first? [Y/n]  ").lower() not in {"n", "no"}:
            self._save()
        self.say("\n  Until next time.")


def author(root: Path, packs: Path, out: TextIO | None = None) -> int:
    """Open a pack in the wizard.

    Parameters
    ----------
    root : Path
        The pack directory.
    packs : Path
        Where its dependencies live.
    out : TextIO or None
        Where to write. Defaults to standard output.

    Returns
    -------
    int
        The process exit code.
    """
    stream = out or sys.stdout
    try:
        project = Project.open(root, packs)
    except ContentError as error:
        print(f"error   {error}", file=sys.stderr)
        return 1

    wizard = Wizard(project, stream, interactive=sys.stdin.isatty())
    for problem in project.unreadable:
        wizard.say(f"  ! {problem}")
    try:
        wizard.home()
    except Stop:
        wizard.say("\n  Until next time.")
    return 0


def _askable(ask: Ask) -> Field:
    """The field for one cascade question, made skippable where it has a default.

    A question with a default is a question the author should be able to press
    enter on — "who is carrying it" almost always means the player, and being
    made to say so every time is what turns a cascade into a form.

    Parameters
    ----------
    ask : Ask
        The question.

    Returns
    -------
    Field
        The field, optional if there is something to fall back to.
    """
    if ask.default is None or ask.field.optional:
        return ask.field
    return replace(ask.field, optional=True)


def _shown(value: Any) -> str:
    """A default, as it should read in a prompt.

    Parameters
    ----------
    value : object
        The default.

    Returns
    -------
    str
        `the player`, `yes`, `1`.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _said(authored: Any, noun: str, names: Names) -> str:
    """Render one authored condition or effect for a list.

    Parameters
    ----------
    authored : object
        The authored mapping.
    noun : str
        `condition` or `effect`.
    names : Names
        The naming service.

    Returns
    -------
    str
        The English, or the raw mapping when it will not build.
    """
    from mace.model import Condition, Effect
    from mace.wizard.language import say_condition, say_effect

    try:
        if noun == "condition":
            return say_condition(Condition.model_validate(authored), names)
        return say_effect(Effect.model_validate(authored), names)
    except ValueError:
        return f"{authored}  (does not build yet)"


def _entry(entry: Any) -> str:
    """Summarise one repeat entry for a list.

    Parameters
    ----------
    entry : object
        The authored entry.

    Returns
    -------
    str
        `to: castle · route: road`.
    """
    if not isinstance(entry, Mapping):
        return str(entry)
    return " · ".join(f"{key}: {value}" for key, value in entry.items())


def _kit(typed: str) -> dict[str, int]:
    """Read `rope 1, dagger 1` into items and quantities.

    Parameters
    ----------
    typed : str
        What the author typed.

    Returns
    -------
    dict
        Reference to quantity. An entry with no number means one.
    """
    kit: dict[str, int] = {}
    for part in typed.split(","):
        reference, _, count = part.strip().partition(" ")
        if reference:
            kit[reference] = int(count) if count.strip().isdigit() else 1
    return kit


def _setup_line(setup: PlaytestSetup) -> str:
    """Say a playtest setup in one line.

    Parameters
    ----------
    setup : PlaytestSetup
        The setup.

    Returns
    -------
    str
        `seed mace · at troll-bridge · tick 48 · in storm`.
    """
    parts = [f"seed {setup.seed}"]
    if setup.start_location:
        parts.append(f"at {_local(setup.start_location)}")
    if setup.start_tick is not None:
        parts.append(f"tick {setup.start_tick}")
    if setup.weather:
        parts.append(f"in {_local(setup.weather)}")
    if setup.items:
        parts.append("with " + ", ".join(_local(one) for one in setup.items))
    if setup.background:
        parts.append(f"as {_local(setup.background)}")
    if setup.debug:
        parts.append("debug on")
    return " · ".join(parts)


def _as_list(value: Any) -> list[Any]:
    """Read a value that may be a list, a lone item, or nothing.

    Parameters
    ----------
    value : object
        The authored value.

    Returns
    -------
    list
        Its entries.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _line_text(line: Any) -> Any:
    """The text of a narration line, which may be a bare string.

    Parameters
    ----------
    line : object
        A string or a `{text: ...}` mapping.

    Returns
    -------
    object
        The text.
    """
    return line.get("text", "") if isinstance(line, Mapping) else line


def _slug(name: str) -> str:
    """Turn a name into a content id.

    Parameters
    ----------
    name : str
        What the author typed.

    Returns
    -------
    str
        `the-old-bridge`.
    """
    kept = [c.lower() if c.isalnum() else "-" for c in name]
    return "-".join(part for part in "".join(kept).split("-") if part) or "untitled"


def _short(text: str, width: int = 44) -> str:
    """Trim a value for the right-hand column.

    Parameters
    ----------
    text : str
        The value.
    width : int
        How much room there is.

    Returns
    -------
    str
        The value, or its beginning with an ellipsis.
    """
    flat = " ".join(text.split())
    return flat if len(flat) <= width else f"{flat[: width - 1]}…"


def _wrap(text: str, width: int = 66) -> list[str]:
    """Break help text into lines.

    Parameters
    ----------
    text : str
        The help.
    width : int
        Where to break.

    Returns
    -------
    list of str
        The lines.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _first_line(error: Exception) -> str:
    """The first line of a validation error, which is the useful one.

    Parameters
    ----------
    error : Exception
        The error.

    Returns
    -------
    str
        Its first line.
    """
    return str(error).splitlines()[-1].strip()


def _local(qualified: str | None) -> str:
    """Strip the pack from a qualified id, for display.

    Parameters
    ----------
    qualified : str or None
        The id.

    Returns
    -------
    str
        The local part.
    """
    return "" if qualified is None else qualified.split(":", 1)[-1]
