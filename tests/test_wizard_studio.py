"""The authoring session: the wizard's screens as data, for a form to draw.

Phase 4 made the *questions* data and left the screens around them inside a
terminal loop. These check the other half — that the task list, a section, one
object and one step come out as JSON a browser can render, and that a browser
rendering them is driving the same wizard the terminal drives rather than a
second one.

Two of them are load-bearing.

`test_a_picker_arrives_with_its_options_on_it` is the whole reason this module
exists: a browser cannot ask the catalog a question in the middle of a render,
so a `Select` has to reach it as a list. Without that a web form would go back
to typing references by hand, which is the exact hole `Query` was built to
close.

`test_an_answer_lands_in_the_authors_own_file` is the promise the project model
makes and a wire is the easiest place to break: an answer posted over HTTP has
to end up in the document the author wrote, comments and all, and not in a
detached copy of it.
"""

from pathlib import Path
from typing import Any

import pytest

from conftest import write_pack
from mace.content import ContentError
from mace.wizard.studio import Studio, Unknown, frame, vocabulary


def world(root: Path, **files: Any) -> Path:
    """A small game pack to open.

    Parameters
    ----------
    root : Path
        Where to write it.
    **files
        Filename stem to document.

    Returns
    -------
    Path
        The pack directory.
    """
    documents: dict[str, Any] = {
        "locations.yml": {
            "locations": [
                {
                    "id": "home",
                    "name": "Home",
                    # A comment on a key nobody is going to touch, so the
                    # round-trip promise has something to lose.
                    "description": "Six houses and a well.",
                    "exits": [{"to": "castle"}],
                },
                {"id": "castle", "name": "The Castle", "exits": [{"to": "home"}]},
            ]
        },
        "people.yml": {
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
                },
                {"id": "gold", "kind": "item", "name": "Gold"},
            ]
        },
        "game.yml": {
            "game": {
                "name": "Tiny",
                "player": {"entity": "hero", "startLocation": "home"},
                "winConditions": [{"atLocation": {"location": "castle"}}],
            }
        },
    }
    documents.update({f"{name}.yml": body for name, body in files.items()})
    return write_pack(root, "tiny", kind="game", files=documents)


@pytest.fixture
def studio(tmp_path: Path) -> Studio:
    return Studio.open(world(tmp_path))


def step_of(screen: dict[str, Any], step_id: str) -> dict[str, Any]:
    """One step out of an object screen.

    Parameters
    ----------
    screen : dict
        The object screen.
    step_id : str
        Which step.

    Returns
    -------
    dict
        The step.
    """
    return next(one for one in screen["steps"] if one["id"] == step_id)


# ── The task list ─────────────────────────────────────────────────────────────


def test_the_desk_is_the_task_list_the_terminal_draws(studio: Studio) -> None:
    desk = studio.desk()
    assert desk["name"] == "Tiny"
    assert [task["section"] for task in desk["tasks"]][:2] == ["game", "world"]
    assert 0 <= desk["percent"] <= 100
    world_task = next(one for one in desk["tasks"] if one["section"] == "world")
    assert world_task["summary"].startswith("2 locations")


def test_every_reply_carries_the_desk(studio: Studio) -> None:
    """The header that counts problems has to move when an answer moves it."""
    sent = frame(studio, studio.section("world"))
    assert sent["pack"]["id"] == "tiny"
    assert sent["desk"]["name"] == "Tiny"
    assert sent["screen"]["section"] == "world"
    assert sent["dirty"] == []


def test_a_frame_says_which_files_are_unsaved(studio: Studio) -> None:
    studio.answer("locations", "location.name", "The Hearth", "home")
    assert frame(studio)["dirty"] == ["locations.yml"]
    studio.save()
    assert frame(studio)["dirty"] == []


# ── A section ─────────────────────────────────────────────────────────────────


def test_a_section_lists_what_it_holds_across_its_collections(studio: Studio) -> None:
    """A section is a grouping of work, not of collections."""
    screen = studio.section("world")
    assert {one["id"] for one in screen["objects"]} == {"home", "castle"}
    assert screen["creates"] == ["locations", "routes"]


def test_a_section_says_which_of_its_objects_are_unfinished(tmp_path: Path) -> None:
    root = world(tmp_path)
    open_studio = Studio.open(root)
    open_studio.create("locations", "Moor")
    screen = open_studio.section("world")
    moor = next(one for one in screen["objects"] if one["id"] == "moor")
    assert moor["unfinished"]


def test_the_game_section_is_a_manifest_rather_than_a_list(studio: Studio) -> None:
    assert studio.section("game")["manifest"] is True


def test_a_section_nobody_has_is_a_404(studio: Studio) -> None:
    with pytest.raises(Unknown, match="no section"):
        studio.section("dragons")


# ── One object ────────────────────────────────────────────────────────────────


def test_an_object_screen_is_the_flow_with_its_answers_in_it(studio: Studio) -> None:
    screen = studio.object("locations", "home")
    assert screen["label"] == "Home"
    name = step_of(screen, "location.name")
    assert name["value"] == "Home"
    assert name["answered"] is True
    assert name["described"] == "Home"


def test_the_game_manifest_is_an_object_with_no_id(studio: Studio) -> None:
    screen = studio.object("game")
    assert screen["id"] is None
    assert step_of(screen, "game.name")["value"] == "Tiny"


def test_an_object_that_is_not_there_is_a_404(studio: Studio) -> None:
    with pytest.raises(Unknown, match="no `nowhere`"):
        studio.object("locations", "nowhere")


def test_a_collection_with_no_flow_is_a_404(studio: Studio) -> None:
    with pytest.raises(Unknown, match="nothing authors"):
        studio.object("climates", "temperate")


def test_a_collection_binding_without_an_object_is_refused(studio: Studio) -> None:
    with pytest.raises(Unknown, match="which object"):
        studio.object("locations")


# ── Fields, and what a form needs to draw them ────────────────────────────────


def test_a_picker_arrives_with_its_options_on_it(studio: Studio) -> None:
    """A browser cannot ask the catalog a question mid-render."""
    entities = step_of(studio.object("locations", "home"), "location.entities")
    assert entities["field"]["kind"] == "multi-select"
    offered = {one["value"] for one in entities["field"]["options"]}
    assert {"hero", "gold"} <= offered
    assert entities["field"]["allowCreate"] == "entities"


def test_a_picker_sees_a_thing_the_last_answer_created(tmp_path: Path) -> None:
    """A stale picker is what would make the forms a different tool."""
    open_studio = Studio.open(world(tmp_path))
    before = studio_options(open_studio)
    open_studio.create("locations", "Moor")
    assert "moor" not in before
    assert "moor" in studio_options(open_studio)


def studio_options(open_studio: Studio) -> set[str]:
    """Which places the game's start-location picker is offering.

    Parameters
    ----------
    open_studio : Studio
        The open pack.

    Returns
    -------
    set of str
        The offered values.
    """
    start = step_of(open_studio.object("game"), "game.player.startLocation")
    return {one["value"] for one in start["field"]["options"]}


def test_a_number_field_carries_its_bounds(studio: Studio) -> None:
    points = step_of(studio.object("game"), "game.player.creationPoints")
    assert points["field"]["kind"] == "number"
    assert points["field"]["integer"] is True
    assert points["field"]["minimum"] == 0


def test_a_repeat_carries_the_steps_that_build_one_entry(studio: Studio) -> None:
    exits = step_of(studio.object("locations", "home"), "location.exits")
    assert exits["field"]["kind"] == "repeat"
    assert exits["field"]["of"] == "exit"
    assert any(one["field"]["kind"] == "select" for one in exits["field"]["steps"])


def test_a_round_trip_value_comes_over_the_wire_as_plain_json(studio: Studio) -> None:
    """The author's own objects carry comments; those must not go on a wire."""
    import json

    screen = studio.object("locations", "home")
    json.dumps(screen)  # would raise on a ruamel node it could not encode
    description = step_of(screen, "location.description")
    assert description["value"] == "Six houses and a well."


# ── Answering ─────────────────────────────────────────────────────────────────


def test_an_answer_lands_in_the_authors_own_file(tmp_path: Path) -> None:
    """An answer posted over a wire has to reach the document, not a copy."""
    root = world(tmp_path)
    (root / "locations.yml").write_text(
        "# Places, and the roads between them.\n"
        "locations:\n"
        "  - id: home\n"
        "    name: Home        # where it starts\n"
        "    exits: [{to: castle}]\n"
        "  - id: castle\n"
        "    name: The Castle\n"
    )
    open_studio = Studio.open(root)
    open_studio.answer("locations", "location.name", "The Hearth", "home")
    open_studio.save()

    written = (root / "locations.yml").read_text()
    assert "# Places, and the roads between them." in written
    assert "# where it starts" in written
    assert "name: The Hearth" in written


def test_an_answer_comes_back_as_the_step_it_changed(studio: Studio) -> None:
    changed = studio.answer("locations", "location.safe", True, "home")
    assert changed["value"] is True
    assert changed["described"] == "yes"


def test_clearing_a_field_removes_it_rather_than_writing_a_null(
    studio: Studio,
) -> None:
    studio.answer("locations", "location.safe", True, "home")
    studio.answer("locations", "location.safe", None, "home")
    held = studio.project.get("locations", "home")
    assert held is not None and "safe" not in held


def test_answering_a_step_nobody_has_is_a_404(studio: Studio) -> None:
    with pytest.raises(Unknown, match="no step"):
        studio.answer("locations", "location.vibes", "eerie", "home")


def test_answering_an_object_nobody_has_is_a_content_error(studio: Studio) -> None:
    with pytest.raises(ContentError, match="no `nowhere`"):
        studio.answer("locations", "location.name", "X", "nowhere")


# ── Making and unmaking ───────────────────────────────────────────────────────


def test_creating_takes_only_what_the_object_needs_to_exist(studio: Studio) -> None:
    """Nothing blocks anything: an id and a name is a location."""
    made = studio.create("locations", "Moor")
    assert made == "moor"
    assert studio.object("locations", "moor")["label"] == "Moor"


def test_creating_carries_any_other_answers_it_was_given(studio: Studio) -> None:
    studio.create(
        "locations",
        "Moor",
        answers={"location.description": ["Wet, and going on forever."]},
    )
    screen = studio.object("locations", "moor")
    assert step_of(screen, "location.description")["value"] == [
        "Wet, and going on forever."
    ]


def test_creating_without_a_name_says_so(studio: Studio) -> None:
    with pytest.raises(ContentError, match="needs a name"):
        studio.create("locations", "   ")


def test_creating_in_a_section_takes_the_fields_that_section_fixes(
    studio: Studio,
) -> None:
    """A thing made under Items is an item without anybody being asked."""
    studio.create("entities", "Lantern", section="items")
    held = studio.project.get("entities", "lantern")
    assert held is not None and held["kind"] == "item"


def test_creating_something_that_is_already_there_is_refused(studio: Studio) -> None:
    with pytest.raises(ContentError, match="already there"):
        studio.create("locations", "Home")


def test_the_game_manifest_is_not_something_you_create(studio: Studio) -> None:
    with pytest.raises(Unknown, match="not something you create"):
        studio.create("game", "Whatever")


def test_deleting_removes_it_and_says_whether_there_was_one(studio: Studio) -> None:
    assert studio.delete("locations", "castle") is True
    assert studio.delete("locations", "castle") is False
    assert {one["id"] for one in studio.section("world")["objects"]} == {"home"}


def test_deleting_something_things_point_at_is_allowed_and_reported(
    studio: Studio,
) -> None:
    """A wizard that refused could not be used to restructure a world."""
    studio.delete("locations", "castle")
    assert any("castle" in one["message"] for one in studio.report())


# ── The problem list ──────────────────────────────────────────────────────────


def test_the_report_is_the_validator_worst_first(tmp_path: Path) -> None:
    root = world(tmp_path, broken={"locations": [{"id": "bad", "nonsense": True}]})
    problems = Studio.open(root).report()
    assert problems
    assert problems[0]["severity"] == "error"
    assert any(one["object"] == "bad" for one in problems)


def test_a_section_carries_only_its_own_problems(tmp_path: Path) -> None:
    root = world(tmp_path, broken={"locations": [{"id": "bad", "nonsense": True}]})
    screen = Studio.open(root).section("world")
    assert screen["problems"]
    assert all(one["collection"] != "entities" for one in screen["problems"])


def test_a_file_that_will_not_parse_is_reported_on_every_frame(
    tmp_path: Path,
) -> None:
    root = world(tmp_path)
    (root / "junk.yml").write_text("locations: [\n")
    assert frame(Studio.open(root))["unreadable"]


# ── The cascade ───────────────────────────────────────────────────────────────


def test_the_vocabulary_is_every_recipe_the_terminal_has(studio: Studio) -> None:
    from mace.wizard.builders import CONDITIONS, EFFECTS

    described = vocabulary()
    assert len(described["conditions"]) == len(CONDITIONS)
    assert len(described["effects"]) == len(EFFECTS)
    assert {one["group"] for one in described["conditions"]} >= {"The player"}


def test_a_cascade_ask_arrives_with_this_packs_options_on_it(studio: Studio) -> None:
    has_item = next(
        one for one in studio.vocabulary()["conditions"] if one["tag"] == "hasItem"
    )
    which = has_item["asks"][0]
    assert {option["value"] for option in which["field"]["options"]} == {"gold"}


def test_building_a_condition_returns_content_and_english(studio: Studio) -> None:
    built = studio.build("conditions", "hasItem", {"item": "gold", "qty": 10})
    assert built["authored"] == {"hasItem": {"item": "gold", "qty": 10}}
    assert built["said"] == "the player is carrying at least 10 Gold"


def test_building_drops_the_defaults_the_cascade_filled_in(studio: Studio) -> None:
    """The file gets the smallest content that means what the author said."""
    built = studio.build("conditions", "hasItem", {"item": "gold"})
    assert "actor" not in built["authored"]["hasItem"]


def test_building_an_effect_works_the_same_way(studio: Studio) -> None:
    built = studio.build("effects", "giveItem", {"item": "gold", "qty": 4})
    assert built["authored"] == {"giveItem": {"item": "gold", "qty": 4}}
    assert "Gold" in built["said"]


def test_building_something_nothing_makes_is_a_404(studio: Studio) -> None:
    with pytest.raises(Unknown, match="nothing builds"):
        studio.build("conditions", "vibeCheck", {})


def test_building_nonsense_is_refused_by_the_model(studio: Studio) -> None:
    with pytest.raises(ValueError, match="qty"):
        studio.build("conditions", "hasItem", {"item": "gold", "qty": 0})


def test_saying_a_condition_that_will_not_build_does_not_go_blank(
    studio: Studio,
) -> None:
    """Content in a project is allowed to be wrong for a while."""
    said = studio.say("conditions", [{"hasItem": {"qty": "several"}}])
    assert "wrong" in said


# ── Saving ────────────────────────────────────────────────────────────────────


def test_saving_writes_only_what_changed(tmp_path: Path) -> None:
    root = world(tmp_path)
    open_studio = Studio.open(root)
    assert open_studio.save() == []

    open_studio.answer("locations", "location.name", "The Hearth", "home")
    assert open_studio.save() == ["locations.yml"]


# ── The map ───────────────────────────────────────────────────────────────────


def test_the_atlas_is_the_shape_of_the_pack(studio: Studio) -> None:
    """Not the player's atlas: no fog, no weather, no opinion about anywhere."""
    drawn = studio.atlas()
    assert {one["id"] for one in drawn["places"]} == {"home", "castle"}
    exits = {one["id"]: one["exits"] for one in drawn["places"]}
    assert exits == {"home": ["castle"], "castle": ["home"]}


def test_a_place_nobody_has_positioned_says_so(studio: Studio) -> None:
    """The client laying it out is not the same as the author having chosen."""
    place = next(one for one in studio.atlas()["places"] if one["id"] == "home")
    assert place["x"] is None and place["y"] is None

    studio.answer("locations", "location.mapPosition", {"x": 3, "y": 4}, "home")
    place = next(one for one in studio.atlas()["places"] if one["id"] == "home")
    assert (place["x"], place["y"]) == (3.0, 4.0)


def test_drawing_a_road_writes_the_ways_onto_it_too(studio: Studio) -> None:
    """A route is a road; an exit is the option to walk down it."""
    studio.create("locations", "Moor")
    made = studio.link("home", "moor", 5)

    assert made == "home-to-moor"
    road = next(one for one in studio.atlas()["roads"] if one["id"] == made)
    assert (road["from"], road["to"], road["ticks"]) == ("home", "moor", 5)

    both = {one["id"]: one["exits"] for one in studio.atlas()["places"]}
    assert "moor" in both["home"]
    assert "home" in both["moor"]


def test_a_road_can_be_named(studio: Studio) -> None:
    studio.create("locations", "Moor")
    assert studio.link("home", "moor", 5, name="The Long Way") == "the-long-way"


def test_a_road_to_nowhere_is_refused(studio: Studio) -> None:
    with pytest.raises(ContentError, match="no `nowhere`"):
        studio.link("home", "nowhere", 4)


def test_a_road_from_a_place_to_itself_is_refused(studio: Studio) -> None:
    with pytest.raises(ContentError, match="somewhere else"):
        studio.link("home", "home", 4)


def test_a_road_that_is_already_there_is_refused(studio: Studio) -> None:
    studio.create("locations", "Moor")
    studio.link("home", "moor", 5)
    with pytest.raises(ContentError, match="already there"):
        studio.link("home", "moor", 5)


def test_rubbing_a_road_out_takes_the_ways_onto_it_with_it(studio: Studio) -> None:
    """An exit naming a route that is gone is a dangling reference."""
    studio.create("locations", "Moor")
    made = studio.link("home", "moor", 5)

    assert studio.unlink(made) is True
    assert studio.unlink(made) is False
    assert studio.atlas()["roads"] == []
    both = {one["id"]: one["exits"] for one in studio.atlas()["places"]}
    assert "moor" not in both["home"]
    # The exit the author wrote by hand is untouched: it names no route.
    assert both["home"] == ["castle"]


# ── The scene graph ───────────────────────────────────────────────────────────


def scenes(root: Path, *written: Any) -> Studio:
    """A pack whose scenes are whatever a test needs them to be.

    Parameters
    ----------
    root : Path
        Where to write it.
    *written
        Scene mappings.

    Returns
    -------
    Studio
        The open pack.
    """
    return Studio.open(world(root, plot={"scenes": list(written)}))


def test_the_graph_says_what_leads_where(tmp_path: Path) -> None:
    open_studio = scenes(
        tmp_path,
        {"id": "start", "say": ["Well then."], "goto": "onward"},
        {"id": "onward", "say": ["And then."]},
    )
    open_studio.answer("locations", "location.onArrive", "start", "home")

    graph = open_studio.graph()
    by_id = {one["id"]: one for one in graph["scenes"]}
    assert by_id["start"]["leadsTo"] == ["onward"]
    assert by_id["start"]["entrance"] is True
    assert by_id["onward"]["entrance"] is False


def test_the_graph_finds_a_scene_with_no_way_in(tmp_path: Path) -> None:
    """The one question worth asking of a pack past about a dozen scenes."""
    open_studio = scenes(
        tmp_path,
        {"id": "start", "say": ["Well then."]},
        {"id": "orphan", "say": ["Nobody comes here."]},
    )
    open_studio.answer("locations", "location.onArrive", "start", "home")

    by_id = {one["id"]: one for one in open_studio.graph()["scenes"]}
    assert by_id["start"]["reachable"] is True
    assert by_id["orphan"]["reachable"] is False


def test_a_scene_that_only_reaches_itself_is_still_an_orphan(
    tmp_path: Path,
) -> None:
    """A `goto` loop is an island, not a healthy corner of the map."""
    open_studio = scenes(
        tmp_path,
        {"id": "start", "say": ["Well then."]},
        {"id": "loop", "say": ["Again."], "goto": "loop"},
    )
    open_studio.answer("locations", "location.onArrive", "start", "home")

    by_id = {one["id"]: one for one in open_studio.graph()["scenes"]}
    assert by_id["loop"]["reachable"] is False


def test_the_graph_agrees_with_the_validator(tmp_path: Path) -> None:
    """Two answers to "can a player get here" is one too many."""
    open_studio = scenes(
        tmp_path,
        {"id": "start", "say": ["Well then."]},
        {"id": "orphan", "say": ["Nobody comes here."]},
    )
    open_studio.answer("locations", "location.onArrive", "start", "home")

    orphaned = {
        one["id"] for one in open_studio.graph()["scenes"] if not one["reachable"]
    }
    reported = {
        one["object"]
        for one in open_studio.report()
        if one["collection"] == "scenes" and "not reached" in one["message"]
    }
    assert orphaned == reported == {"orphan"}


def test_the_graph_says_which_scenes_will_not_build(tmp_path: Path) -> None:
    """A scene that is not on the graph is not a scene somebody deleted."""
    open_studio = scenes(
        tmp_path,
        {"id": "start", "say": ["Well then."]},
        {"id": "broken", "nonsense": True},
    )
    assert open_studio.graph()["dropped"] == ["broken"]


def test_a_scene_that_hands_control_back_is_marked_as_one(tmp_path: Path) -> None:
    open_studio = scenes(
        tmp_path,
        {"id": "start", "say": ["Well then."]},
        {
            "id": "onward",
            "say": ["Pick."],
            "choices": [{"prompt": "Go", "goto": "start"}],
        },
    )
    by_id = {one["id"]: one for one in open_studio.graph()["scenes"]}
    assert by_id["start"]["ends"] is True
    assert by_id["onward"]["ends"] is False


# ── The live preview ──────────────────────────────────────────────────────────


def inheriting(root: Path) -> Studio:
    """A pack with a parent and a child, which is what a preview is for.

    Parameters
    ----------
    root : Path
        Where to write it.

    Returns
    -------
    Studio
        The open pack.
    """
    return Studio.open(
        world(
            root,
            beasts={
                "entities": [
                    {
                        "id": "troll",
                        "kind": "actor",
                        "name": "Troll",
                        "description": [
                            {"text": "Moss in its hair.", "when": {"dayPart": ["day"]}},
                            {"text": "Something large, breathing."},
                        ],
                        "tags": ["monster"],
                        "disposition": "neutral",
                        "stats": {
                            "hitpoints": {"base": 80, "max": 80},
                            "strength": {"base": 70},
                        },
                        "inventory": [{"item": "gold", "qty": 12}],
                    },
                    {"id": "gorm", "extends": "troll", "name": "Gorm"},
                ]
            },
        )
    )


def test_a_preview_is_the_object_rather_than_the_file(tmp_path: Path) -> None:
    """`extends` means the file is not the object, and a form cannot say so."""
    seen = inheriting(tmp_path).preview("entities", "gorm")

    assert seen["built"] is True
    assert seen["inherits"] == "troll"
    assert {one["stat"] for one in seen["stats"]} == {"hitpoints", "strength"}
    assert [one["qty"] for one in seen["carries"]] == [12]


def test_a_preview_says_which_of_it_the_author_actually_wrote(
    tmp_path: Path,
) -> None:
    """An author who cannot tell will retype it."""
    seen = inheriting(tmp_path).preview("entities", "gorm")
    facts = {one["label"]: one["own"] for one in seen["facts"]}
    assert facts["tags"] is False
    assert facts["disposition"] is False


def test_a_preview_puts_a_conditional_description_in_english(
    tmp_path: Path,
) -> None:
    """Three lines in a file, one line in play."""
    seen = inheriting(tmp_path).preview("entities", "gorm")
    assert [one["when"] for one in seen["lines"]] == ["it is day", "always"]


def test_a_backgrounds_description_is_a_plain_pitch_not_a_conditional_line(
    tmp_path: Path,
) -> None:
    """A background's `description` is a bare string, unlike an entity's.

    `_lines` used to assume every collection's description was the usual
    tuple of conditional lines and iterated the string character by
    character, which crashed the preview of any background at all.
    """
    open_studio = Studio.open(
        world(
            tmp_path,
            folk={
                "backgrounds": [
                    {
                        "id": "memory-wiped",
                        "name": "Memory-Wiped",
                        "description": "You remember nothing before the ditch.",
                    }
                ]
            },
        )
    )
    seen = open_studio.preview("backgrounds", "memory-wiped")
    assert seen["built"] is True
    assert seen["lines"] == [
        {"text": "You remember nothing before the ditch.", "when": "always"}
    ]


def test_a_preview_of_something_that_will_not_build_says_why(
    tmp_path: Path,
) -> None:
    """A preview that went blank when an author broke something is untrusted."""
    open_studio = Studio.open(
        world(tmp_path, broken={"locations": [{"id": "bad", "nonsense": True}]})
    )
    seen = open_studio.preview("locations", "bad")
    assert seen["built"] is False
    assert seen["why"]
    assert seen["name"] == "bad"


def test_a_preview_of_nothing_is_a_404(tmp_path: Path) -> None:
    with pytest.raises(Unknown, match="no `nowhere`"):
        Studio.open(world(tmp_path)).preview("locations", "nowhere")


def test_a_preview_is_of_unsaved_work(tmp_path: Path) -> None:
    """Compiling never touches the disk, so a live preview is actually live."""
    open_studio = inheriting(tmp_path)
    open_studio.answer("entities", "entity.name", "Gorm the Patient", "gorm")
    assert open_studio.preview("entities", "gorm")["name"] == "Gorm the Patient"
    assert open_studio.project.dirty
