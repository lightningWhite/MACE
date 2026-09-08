"""The declarative flow: pickers, fields, bindings, and the task list.

The properties worth guarding are the ones that make the wizard different from
the v0 one. Every reference is picked from something that exists. A field
describes itself in English. An answer lands in the author's own file without
disturbing anything around it. And the task list tells the truth about a pack
somebody may have hand-edited since the wizard last saw it.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import game_pack
from mace.wizard.fields import (
    Bool,
    ConditionBuilder,
    Fixed,
    Invalid,
    MapEditor,
    MultiSelect,
    NotOneLine,
    Number,
    Select,
    Text,
    TextList,
)
from mace.wizard.flow import Binding, Flow, Step, answered
from mace.wizard.flows import ENTITY, GAME, LOCATION
from mace.wizard.project import Project
from mace.wizard.query import Catalog, Query, QuestStages, Scoped
from mace.wizard.tasks import SECTIONS, State, review

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKS = REPO_ROOT / "packs"


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project.open(game_pack(tmp_path), tmp_path)


@pytest.fixture
def catalog(project: Project) -> Catalog:
    return Catalog(project)


@pytest.fixture(scope="module")
def quest() -> Project:
    """The real pack, opened for editing.

    Used where the point is that the wizard reads a hand-written world
    correctly rather than one the test just wrote.
    """
    return Project.open(PACKS / "games" / "peasants-quest", PACKS)


# ── Queries ───────────────────────────────────────────────────────────────────


def test_a_query_offers_the_things_that_exist(catalog: Catalog) -> None:
    offered = Query("locations").options(catalog)

    assert [option.value for option in offered] == ["castle", "home"]
    assert [option.label for option in offered] == ["The Castle", "Home"]


def test_the_projects_own_things_are_written_bare(quest: Project) -> None:
    """A qualified id in your own file breaks the day you rename your pack."""
    catalog = Catalog(quest)
    mine = {
        option.value for option in Query("entities", scope="project").options(catalog)
    }
    theirs = {
        option.value for option in Query("entities", scope="libraries").options(catalog)
    }

    assert "gorm" in mine
    assert "fantasy.core:bridge-troll" in theirs


def test_a_filter_sees_through_extends(quest: Project) -> None:
    """`gorm` extends a troll and never says `kind`; he is still an actor."""
    catalog = Catalog(quest)
    actors = {
        option.value
        for option in Query(
            "entities", scope="project", where={"kind": "actor"}
        ).options(catalog)
    }

    assert {"gorm", "captain-orin", "letholin"} <= actors


def test_the_player_is_offered_without_being_defined(catalog: Catalog) -> None:
    """`player` is whichever entity the game names, and an author picking it
    should not have to know that."""
    offered = Query("entities", reserved=True).options(catalog)

    assert offered[0].value == "player"
    assert offered[0].label == "the player"


def test_a_reference_to_nothing_stays_visible(catalog: Catalog) -> None:
    assert catalog.label("atlantis", "locations") == "atlantis"
    assert not catalog.exists("atlantis", "locations")


@pytest.fixture
def two_quests(tmp_path: Path) -> Project:
    """A pack with two quests, so a stage picker has something to narrow."""

    def stage(id_: str) -> dict[str, Any]:
        return {"id": id_, "journal": "...", "complete": [{"chance": 1}]}

    quests = {
        "quests": [
            {
                "id": "the-summons",
                "name": "The Summons",
                "stages": [stage("set-out"), stage("arrive")],
            },
            {
                "id": "the-heist",
                "name": "The Heist",
                "stages": [stage("case-the-vault"), stage("crack-it")],
            },
        ]
    }
    return Project.open(game_pack(tmp_path, world=quests), tmp_path)


def test_quest_stages_are_offered_scoped_to_their_quest(two_quests: Project) -> None:
    catalog = Catalog(two_quests)
    offered = QuestStages().options(catalog)

    assert {(o.value, o.scope) for o in offered} == {
        ("set-out", "the-summons"),
        ("arrive", "the-summons"),
        ("case-the-vault", "the-heist"),
        ("crack-it", "the-heist"),
    }


def test_a_scoped_source_narrows_to_one_quest(two_quests: Project) -> None:
    catalog = Catalog(two_quests)
    narrowed = Scoped(QuestStages(), "the-heist").options(catalog)

    assert {o.value for o in narrowed} == {"case-the-vault", "crack-it"}


# ── Fields ────────────────────────────────────────────────────────────────────


def test_a_select_takes_a_number_or_a_name(catalog: Catalog) -> None:
    field = Select(options=Query("locations"))

    assert field.parse("1", catalog) == "castle"
    assert field.parse("home", catalog) == "home"
    assert field.parse("The Castle", catalog) == "castle"


def test_a_select_says_what_is_wrong_rather_than_guessing(catalog: Catalog) -> None:
    field = Select(options=Query("locations"))

    with pytest.raises(Invalid, match="between 1 and 2"):
        field.parse("the moon", catalog)


def test_a_select_reads_back_as_the_name_the_author_gave_it(catalog: Catalog) -> None:
    assert (
        Select(options=Query("locations")).describe("castle", catalog) == "The Castle"
    )


def test_a_multi_select_takes_a_list_and_drops_repeats(catalog: Catalog) -> None:
    field = MultiSelect(options=Query("locations"))

    assert field.parse("1, 2, 1", catalog) == ["castle", "home"]
    assert field.parse("", catalog) == []


def test_numbers_are_checked_against_their_bounds(catalog: Catalog) -> None:
    field = Number(minimum=0, maximum=10)

    assert field.parse("5", catalog) == 5
    with pytest.raises(Invalid, match="no higher than 10"):
        field.parse("11", catalog)
    with pytest.raises(Invalid, match="whole number"):
        field.parse("half", catalog)


def test_yes_and_no_are_both_answers(catalog: Catalog) -> None:
    assert Bool().parse("y", catalog) is True
    assert Bool().parse("no", catalog) is False
    assert Bool().describe(False, catalog) == "no"


def test_the_map_field_falls_back_to_two_numbers(catalog: Catalog) -> None:
    """A field the terminal cannot draw must still be answerable in one."""
    assert MapEditor().parse("3, 4", catalog) == {"x": 3.0, "y": 4.0}
    assert MapEditor().describe({"x": 3, "y": 4}, catalog) == "(3, 4)"
    with pytest.raises(Invalid, match="two numbers"):
        MapEditor().parse("over there", catalog)


def test_a_built_field_refuses_to_be_typed_at(catalog: Catalog) -> None:
    for field in (ConditionBuilder(), TextList()):
        assert field.interactive
        with pytest.raises(NotOneLine):
            field.parse("something", catalog)


def test_a_condition_reads_back_in_english(catalog: Catalog) -> None:
    said = ConditionBuilder().describe(
        [{"atLocation": {"location": "castle"}}], catalog
    )

    assert said == "the player is at The Castle"


def test_a_half_written_condition_says_so_rather_than_vanishing(
    catalog: Catalog,
) -> None:
    assert ConditionBuilder().describe([{"nonsense": 1}], catalog) == (
        "a condition that does not build yet"
    )


def test_a_fixed_list_is_offered_without_touching_content(catalog: Catalog) -> None:
    field = Select(options=Fixed.of("gentle", ("hard", "hard — no mercy")))

    assert field.parse("2", catalog) == "hard"
    assert field.describe("hard", catalog) == "hard — no mercy"


# ── Bindings ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("written", "collection", "path"),
    [
        ("game.name", None, ("name",)),
        ("game.player.startLocation", None, ("player", "startLocation")),
        ("locations[{id}].entities", "locations", ("entities",)),
        ("entities[{id}].combat.profile", "entities", ("combat", "profile")),
    ],
)
def test_bindings_parse(
    written: str, collection: str | None, path: tuple[str, ...]
) -> None:
    binding = Binding.parse(written)

    assert binding.collection == collection
    assert binding.path == path


def test_a_binding_that_names_no_field_is_refused() -> None:
    with pytest.raises(ValueError, match="binds to no field"):
        Binding.parse("locations[{id}]")


def test_an_answer_lands_in_the_authors_own_file(project: Project) -> None:
    step = LOCATION.step("location.name")
    step.write(project, "A Different Home", "home")

    assert project.get("locations", "home") is not None
    assert dict(project.get("locations", "home") or {})["name"] == "A Different Home"
    assert step.read(project, "home") == "A Different Home"
    assert project.dirty == {Path("world.yml")}


def test_a_nested_answer_makes_the_way_to_itself(project: Project) -> None:
    step = GAME.step("game.rules.combatMode")
    step.write(project, "reflex")

    assert dict(project.game or {})["rules"] == {"combatMode": "reflex"}


def test_clearing_an_answer_removes_the_key_rather_than_writing_a_null(
    project: Project,
) -> None:
    GAME.step("game.tagline").write(project, "Something")
    GAME.step("game.tagline").write(project, None)

    assert "tagline" not in dict(project.game or {})


def test_writing_to_something_that_does_not_exist_says_so(project: Project) -> None:
    from mace.content import ContentError

    with pytest.raises(ContentError, match="no `atlantis`"):
        LOCATION.step("location.name").write(project, "Atlantis", "atlantis")


def test_a_step_sees_a_field_the_object_inherits(quest: Project) -> None:
    """`gorm` never writes `kind`, so asking him again would be nagging."""
    assert ENTITY.step("entity.kind").read(quest, "gorm") == "actor"


@pytest.mark.parametrize(
    ("value", "counts"),
    [(None, False), ("", False), ([], False), ({}, False), (0, True), (False, True)],
)
def test_zero_and_false_are_answers_and_empty_is_not(value: Any, counts: bool) -> None:
    assert answered(value) is counts


def test_a_flow_lists_what_it_is_still_waiting_for(project: Project) -> None:
    waiting = {step.id for step in GAME.unanswered(project)}

    assert "game.introduction" in waiting
    assert "game.name" not in waiting
    assert "game.tagline" not in waiting  # optional


def test_asking_for_a_step_that_does_not_exist_says_which_flow() -> None:
    with pytest.raises(KeyError, match="location"):
        LOCATION.step("location.nonsense")


# ── The task list ─────────────────────────────────────────────────────────────


def test_the_task_list_covers_a_real_pack(quest: Project) -> None:
    listed = review(quest)

    assert listed.name == "A Peasant's Quest"
    assert {task.section.id for task in listed.tasks} == {
        section.id for section in SECTIONS
    }
    assert listed.task("game").state is State.DONE
    assert listed.task("world").summary.startswith("4 locations")
    assert listed.errors == 0


def test_a_section_nobody_has_touched_reads_as_empty(quest: Project) -> None:
    assert review(quest).task("weather").state is State.EMPTY


def test_things_are_counted_in_the_words_an_author_uses(quest: Project) -> None:
    """`5 entities` is a fact about the model, not about their world."""
    assert "characters" in review(quest).task("characters").summary


def test_an_author_can_mark_a_section_done_themselves(quest: Project) -> None:
    from mace.wizard.notes import ProjectNotes

    before = review(quest).task("weather").state
    quest.notes = ProjectNotes(completed=("weather",))
    after = review(quest).task("weather").state
    quest.notes = ProjectNotes()

    assert before is State.EMPTY
    assert after is State.DONE


def test_a_problem_lands_on_the_section_it_is_about(project: Project) -> None:
    project.put(
        "locations",
        {"id": "nowhere", "name": "Nowhere", "onArrive": "a-scene-that-is-not-there"},
    )
    listed = review(project)

    assert listed.errors
    assert listed.task("world").errors
    assert listed.task("world").note


def test_an_unfinished_object_holds_its_section_open(project: Project) -> None:
    project.put("locations", {"id": "sketch"})
    listed = review(project)

    assert listed.task("world").state is State.STARTED
    assert "unfinished" in listed.task("world").summary


def test_every_flow_step_binds_somewhere_real() -> None:
    """A typo in a `binds` would be a step that silently writes nowhere."""
    from mace.wizard.flows import FLOWS

    for flow in (GAME, *FLOWS.values()):
        for step in flow.steps:
            binding = step.binding
            assert binding.collection == flow.collection
            assert binding.path


def test_every_flow_step_has_a_unique_id() -> None:
    from mace.wizard.flows import FLOWS

    for flow in (GAME, *FLOWS.values()):
        ids = [step.id for step in flow.steps]
        assert len(ids) == len(set(ids)), f"{flow.id} repeats a step id"


def test_a_step_is_only_required_when_leaving_it_blank_is_unfinished() -> None:
    """A field the model defaults sensibly is a field an author may skip.

    `minutesPerTick` is thirty unless you say otherwise, so asking again for
    the rest of the project would be nagging about a decision the engine has
    already made. What stays required is either required by the model, or the
    thing a game is not a game without.
    """
    required = {step.id for step in GAME.steps if not step.optional}

    assert required == {
        "game.name",
        "game.introduction",
        "game.player.entity",
        "game.player.startLocation",
        "game.winConditions",
    }


def test_a_flow_is_a_flow_even_when_it_is_empty() -> None:
    empty = Flow(id="nothing", title="Nothing", steps=(Step("a", "A?", "game.name"),))

    assert empty.step("a").title == "A?"
    assert isinstance(empty.step("a").field, Text)
