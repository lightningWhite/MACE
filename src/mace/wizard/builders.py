"""The condition and effect builders: a cascade, as data.

`defineConditions()` in the v0 wizard printed a syntax explanation and hoped.
This is its replacement, and it is the single highest-value piece of the
wizard: an author picks *what this should depend on* from a short list of
things they already understand, answers two or three questions with values
picked from what exists, and reads back an English sentence.

    What should this depend on?
      1. Something somebody is carrying     5. A quest's progress
      2. Where somebody is                  6. Something you flagged earlier
      3. A character's stats                7. Random chance
      4. The weather, or the time           8. Advanced: write an expression

    > 1
    Which item?  … 2. Gold  …          > 2
    How many?                          > 10
    ✓  the player is carrying at least 10 Gold

Like everything else in `mace.wizard`, it is data rather than a script. A
`Recipe` names the tag it produces and the questions that fill it in; a
front-end asks them however it likes. The terminal renders the list above and
the web client will render a set of cards, and neither one contains the
vocabulary.

Every tag in both vocabularies has a recipe, checked by a test — a condition
the builder cannot produce is one an author has to hand-write YAML for, which
is the thing this module exists to prevent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mace.wizard.fields import (
    Bool,
    ConditionBuilder,
    Field,
    Fixed,
    MultiSelect,
    Number,
    Select,
    Text,
)
from mace.wizard.query import Query, QuestStages

__all__ = [
    "CONDITIONS",
    "EFFECTS",
    "Ask",
    "Recipe",
    "build_condition",
    "build_effect",
    "recipe_for",
]

_ACTOR = Select(options=Query("entities", reserved=True))
_ITEM = Select(options=Query("entities", where={"kind": "item"}))
_ANY_ENTITY = Select(options=Query("entities", reserved=True))


@dataclass(frozen=True, slots=True)
class Ask:
    """One question inside a recipe.

    Attributes
    ----------
    key : str
        Where the answer goes in the payload, dotted for nesting.
    title : str
        The question.
    field : Field
        What kind of answer it is.
    default : object
        What to use when the author passes. `None` leaves the key out, which
        is what makes the produced content the smallest thing that means what
        the author said.
    help : str
        A sentence of context, where one is worth having.
    depends_on : str
        Another ask's key in the same recipe, when this one's options should
        be narrowed to whatever was answered there — `stage` narrowed to
        `quest`, say. Empty for a question that stands on its own.
    """

    key: str
    title: str
    field: Field
    default: Any = None
    help: str = ""
    depends_on: str = ""


@dataclass(frozen=True, slots=True)
class Recipe:
    """One way to build a condition or an effect.

    Attributes
    ----------
    label : str
        The menu entry, phrased as the thing an author is thinking about
        rather than as the tag it produces.
    tag : str
        The condition or effect tag.
    asks : tuple of Ask
        The questions, in order.
    group : str
        Which heading it sits under in a long menu.
    help : str
        Shown under the label when the menu has room.
    fixed : mapping
        Payload keys this recipe always sets. `statAtLeast` and `statAtMost`
        are one question with two answers, and `questComplete` differs from
        `questFailed` only in the tag — the difference belongs in the menu,
        not in a question.
    """

    label: str
    tag: str
    asks: tuple[Ask, ...] = ()
    group: str = ""
    help: str = ""
    fixed: Mapping[str, Any] = field(default_factory=dict)

    def build(self, answers: Mapping[str, Any]) -> dict[str, Any]:
        """Assemble the authored mapping this recipe produces.

        Parameters
        ----------
        answers : mapping
            Ask key to the author's answer. A missing or None answer falls
            back to the ask's default, and a key that is still None is left
            out entirely.

        Returns
        -------
        dict
            `{tag: payload}`, ready to go into a content file.
        """
        if self.bare is not None:
            value = answers.get("")
            return {self.tag: self.bare.default if value is None else value}

        payload: dict[str, Any] = dict(self.fixed)
        for ask in self.asks:
            value = answers.get(ask.key)
            if value is None:
                value = ask.default
            if value is None:
                continue
            _plant(payload, ask.key.split("."), value)
        return {self.tag: payload}

    @property
    def bare(self) -> Ask | None:
        """The single question this recipe asks, when it asks only one.

        A one-argument tag is written without a wrapper — `{chance: 0.15}`
        rather than `{chance: {probability: 0.15}}` — because every model with
        a shorthand accepts both and one of them reads like a sentence.

        Returns
        -------
        Ask or None
            The lone question, or None when the payload has named keys.
        """
        if len(self.asks) == 1 and self.asks[0].key == "":
            return self.asks[0]
        return None


def build_condition(recipe: Recipe, answers: Mapping[str, Any]) -> dict[str, Any]:
    """Build a condition and reduce it to the smallest content that says it.

    Round-tripping through the model does two jobs at once. It validates, so
    an author finds out now rather than at load time; and it drops the
    defaults the cascade filled in on their behalf, so the file gets
    `{hasItem: {item: gold, qty: 10}}` rather than an `actor: player` nobody
    typed and nobody needs to read.

    Parameters
    ----------
    recipe : Recipe
        Which condition to build.
    answers : mapping
        Ask key to the author's answer.

    Returns
    -------
    dict
        The authored condition.

    Raises
    ------
    ValueError
        If the answers do not make a valid condition.
    """
    from mace.model import Condition

    return dict(Condition.model_validate(recipe.build(answers)).authored())


def build_effect(recipe: Recipe, answers: Mapping[str, Any]) -> dict[str, Any]:
    """Build an effect and reduce it to the smallest content that says it.

    Parameters
    ----------
    recipe : Recipe
        Which effect to build.
    answers : mapping
        Ask key to the author's answer.

    Returns
    -------
    dict
        The authored effect.

    Raises
    ------
    ValueError
        If the answers do not make a valid effect.
    """
    from mace.model import Effect

    return dict(Effect.model_validate(recipe.build(answers)).authored())


def recipe_for(tag: str, recipes: tuple[Recipe, ...]) -> Recipe:
    """The first recipe that produces a tag.

    Parameters
    ----------
    tag : str
        The condition or effect tag.
    recipes : tuple of Recipe
        Which vocabulary to look in.

    Returns
    -------
    Recipe
        The recipe.

    Raises
    ------
    KeyError
        If nothing builds it.
    """
    for recipe in recipes:
        if recipe.tag == tag:
            return recipe
    raise KeyError(f"nothing builds `{tag}`")


# ── Conditions ────────────────────────────────────────────────────────────────

CONDITIONS: tuple[Recipe, ...] = (
    Recipe(
        label="Something somebody is carrying",
        tag="hasItem",
        group="The player",
        asks=(
            Ask("item", "Which item?", _ITEM),
            Ask(
                "qty",
                "How many, at least?",
                Number(minimum=1, optional=True),
                default=1,
            ),
            Ask("actor", "Who is carrying it?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Where somebody is",
        tag="atLocation",
        group="The player",
        asks=(
            Ask("location", "Which place?", Select(options=Query("locations"))),
            Ask("actor", "Who?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="A character's stat is high enough",
        tag="statAtLeast",
        group="The player",
        asks=(
            Ask("stat", "Which stat?", Text(placeholder="strength")),
            Ask("value", "At least what?", Number(integer=False)),
            Ask("actor", "Whose?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="A character's stat is low enough",
        tag="statAtMost",
        group="The player",
        asks=(
            Ask("stat", "Which stat?", Text(placeholder="stamina")),
            Ask("value", "At most what?", Number(integer=False)),
            Ask("actor", "Whose?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Something you flagged earlier",
        tag="flag",
        group="The world",
        help="Flags are how one scene remembers what another one did.",
        asks=(
            Ask("entity", "On whom or what?", _ANY_ENTITY),
            Ask("flag", "Which flag?", Text(placeholder="has-been-paid")),
            Ask("is", "Set, or cleared?", Bool(optional=True), default=True),
        ),
    ),
    Recipe(
        label="The weather",
        tag="weather",
        group="The world",
        asks=(
            Ask(
                "",
                "Which conditions count?",
                MultiSelect(options=Query("weatherConditions"), min_items=1),
            ),
        ),
    ),
    Recipe(
        label="The kind of weather — wet, cold, dark",
        tag="weatherTag",
        group="The world",
        help="Matches any condition carrying the tag, across every pack.",
        asks=(Ask("", "Which tags?", MultiSelect(options=Fixed(()), min_items=1)),),
    ),
    Recipe(
        label="The season",
        tag="season",
        group="The world",
        asks=(Ask("", "Which seasons?", MultiSelect(options=Fixed(()), min_items=1)),),
    ),
    Recipe(
        label="The time of day",
        tag="dayPart",
        group="The world",
        asks=(
            Ask(
                "",
                "Which parts of the day?",
                MultiSelect(options=Fixed(()), min_items=1),
            ),
        ),
    ),
    Recipe(
        label="What a market is charging",
        tag="priceOf",
        group="The world",
        help=(
            "Against the ordinary price. 1.5 is half again the going rate, "
            "0.7 is a glut. Nothing ever goes outside a quarter to four times."
        ),
        asks=(
            Ask("good", "Which good?", Select(options=Query("goods"))),
            Ask(
                "above",
                "Dearer than what multiple of the usual price?",
                Number(minimum=0.25, maximum=4, integer=False, optional=True),
            ),
            Ask(
                "below",
                "And cheaper than what multiple?",
                Number(minimum=0.25, maximum=4, integer=False, optional=True),
            ),
            Ask(
                "market",
                "Which market?",
                Select(options=Query("markets"), optional=True),
                help="Blank means wherever the player is standing.",
            ),
        ),
    ),
    Recipe(
        label="A quest is finished",
        tag="questComplete",
        group="The story",
        asks=(Ask("", "Which quest?", Select(options=Query("quests"))),),
    ),
    Recipe(
        label="A quest has failed",
        tag="questFailed",
        group="The story",
        asks=(Ask("", "Which quest?", Select(options=Query("quests"))),),
    ),
    Recipe(
        label="A quest has reached a stage",
        tag="questStage",
        group="The story",
        asks=(
            Ask("quest", "Which quest?", Select(options=Query("quests"))),
            Ask(
                "stage",
                "Which stage?",
                Select(options=QuestStages()),
                depends_on="quest",
            ),
        ),
    ),
    Recipe(
        label="Random chance",
        tag="chance",
        group="Chance and combinations",
        help="Rolled on the surrounding content's own stream, so it replays.",
        asks=(
            Ask(
                "",
                "How likely, from 0 to 1?",
                Number(minimum=0, maximum=1, integer=False),
            ),
        ),
    ),
    Recipe(
        label="All of several things",
        tag="all",
        group="Chance and combinations",
        asks=(Ask("", "Which conditions?", ConditionBuilder()),),
    ),
    Recipe(
        label="Any of several things",
        tag="any",
        group="Chance and combinations",
        asks=(Ask("", "Which conditions?", ConditionBuilder()),),
    ),
    Recipe(
        label="The opposite of something",
        tag="not",
        group="Chance and combinations",
        asks=(Ask("", "Which condition?", ConditionBuilder(single=True)),),
    ),
    Recipe(
        label="Advanced: write an expression",
        tag="expr",
        group="Chance and combinations",
        help=(
            "For the things the list above cannot say. Never required — if you "
            "find yourself here often, the vocabulary is missing something."
        ),
        asks=(Ask("", "The expression", Text(placeholder="world.day > 7")),),
    ),
)


# ── Effects ───────────────────────────────────────────────────────────────────

EFFECTS: tuple[Recipe, ...] = (
    Recipe(
        label="Give somebody an item",
        tag="giveItem",
        group="Things and people",
        asks=(
            Ask("item", "Which item?", _ITEM),
            Ask("qty", "How many?", Number(minimum=1, optional=True), default=1),
            Ask("actor", "To whom?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Take an item away",
        tag="takeItem",
        group="Things and people",
        asks=(
            Ask("item", "Which item?", _ITEM),
            Ask("qty", "How many?", Number(minimum=1, optional=True), default=1),
            Ask("actor", "From whom?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Empty one thing into another",
        tag="transferContents",
        group="Things and people",
        help="A looted corpse, a chest tipped into a sack.",
        asks=(
            Ask("from", "Out of what?", _ANY_ENTITY),
            Ask("to", "Into what?", _ANY_ENTITY, default="player"),
        ),
    ),
    Recipe(
        label="Change how somebody feels about the player",
        tag="setDisposition",
        group="Things and people",
        asks=(
            Ask("actor", "Who?", _ANY_ENTITY),
            Ask(
                "to",
                "Feeling what?",
                Select(options=Fixed.of("friendly", "neutral", "hostile")),
            ),
        ),
    ),
    Recipe(
        label="Move a stat up or down",
        tag="adjustStat",
        group="Bodies and stats",
        asks=(
            Ask("stat", "Which stat?", Text(placeholder="hitpoints")),
            Ask(
                "delta", "By how much? (negative takes it away)", Number(integer=False)
            ),
            Ask("reason", "Because of what?", Text(optional=True)),
            Ask("actor", "Whose?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Set a stat outright",
        tag="setStat",
        group="Bodies and stats",
        asks=(
            Ask("stat", "Which stat?", Text(placeholder="hitpoints")),
            Ask("value", "To what?", Number(integer=False)),
            Ask("actor", "Whose?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Apply a temporary modifier",
        tag="applyModifier",
        group="Bodies and stats",
        help="A potion, a spell, a blessing that wears off.",
        asks=(
            Ask("stat", "Which stat?", Text(placeholder="speed")),
            Ask("add", "Add how much?", Number(integer=False, optional=True)),
            Ask("mult", "Multiply by how much?", Number(integer=False, optional=True)),
            Ask("ticks", "For how many ticks?", Number(minimum=1)),
            Ask("label", "Called what?", Text(optional=True)),
            Ask("actor", "Whose?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Hurt somebody",
        tag="damage",
        group="Bodies and stats",
        asks=(
            Ask("amount", "How much?", Number(integer=False)),
            Ask("actor", "Who?", _ANY_ENTITY, default="player"),
            Ask("reason", "From what?", Text(optional=True)),
        ),
    ),
    Recipe(
        label="Rest",
        tag="rest",
        group="Bodies and stats",
        help="Clears exposure and refills pools. The cost is the hours.",
        asks=(
            Ask(
                "ticks",
                "For how many ticks?",
                Number(minimum=1, optional=True),
                default=8,
            ),
        ),
    ),
    Recipe(
        label="Move somebody somewhere",
        tag="move",
        group="Place and time",
        help="Without travelling — this is a teleport, not a journey.",
        asks=(
            Ask("to", "Where to?", Select(options=Query("locations"))),
            Ask("actor", "Who?", _ACTOR, default="player"),
        ),
    ),
    Recipe(
        label="Put a place on the map",
        tag="reveal",
        group="Place and time",
        asks=(Ask("location", "Which place?", Select(options=Query("locations"))),),
    ),
    Recipe(
        label="Let time pass",
        tag="advanceTime",
        group="Place and time",
        asks=(Ask("ticks", "How many ticks?", Number(minimum=1)),),
    ),
    Recipe(
        label="Close a road",
        tag="closeRoute",
        group="Place and time",
        asks=(
            Ask("route", "Which road?", Select(options=Query("routes"))),
            Ask("permanent", "For good?", Bool(optional=True)),
            Ask("reason", "Tell the player what?", Text(optional=True)),
        ),
    ),
    Recipe(
        label="Move what things cost, somewhere",
        tag="marketShock",
        group="Place and time",
        help=(
            "A siege, an eruption, a good harvest. It fades on its own, which "
            "is what lets a player watch a world recover."
        ),
        asks=(
            Ask(
                "mult",
                "Times what, at its worst?",
                Number(minimum=0.05, maximum=20, integer=False),
                help="Above 1 is a shortage; below 1 is a glut.",
            ),
            Ask(
                "decayTicks",
                "Over how many ticks does it fade?",
                Number(minimum=1),
            ),
            Ask(
                "category",
                "Which kind of goods?",
                Text(placeholder="food", optional=True),
                help="Blank for everything.",
            ),
            Ask(
                "good",
                "Or one good in particular?",
                Select(options=Query("goods"), optional=True),
            ),
            Ask(
                "region",
                "Where — which region?",
                Select(options=Query("regions"), optional=True),
                help="Blank for everywhere.",
            ),
            Ask(
                "market",
                "Or one market in particular?",
                Select(options=Query("markets"), optional=True),
            ),
            Ask("reason", "What is it called?", Text(optional=True)),
        ),
    ),
    Recipe(
        label="Put somebody, or something, here",
        tag="spawnEntity",
        group="Place and time",
        help="What an encounter uses to introduce a person rather than a fight.",
        asks=(
            Ask("entity", "Who or what?", _ANY_ENTITY),
            Ask(
                "at",
                "Where?",
                Select(options=Query("locations"), optional=True),
                help="Blank for wherever the player is.",
            ),
            Ask(
                "transient",
                "Do they go when the player moves on?",
                Bool(optional=True),
                default=True,
                help="Something met on the road is met on the road.",
            ),
        ),
    ),
    Recipe(
        label="Reopen a road",
        tag="openRoute",
        group="Place and time",
        asks=(Ask("", "Which road?", Select(options=Query("routes"))),),
    ),
    Recipe(
        label="Change how long a road takes",
        tag="setRouteTicks",
        group="Place and time",
        help="Twelve lines of content and a detour that is genuinely longer.",
        asks=(
            Ask("route", "Which road?", Select(options=Query("routes"))),
            Ask("ticks", "How many ticks now?", Number(minimum=1)),
        ),
    ),
    Recipe(
        label="Override the light",
        tag="setLight",
        group="Place and time",
        help="Blank puts it back to whatever the sky is doing.",
        asks=(
            Ask(
                "",
                "How much light, 0 to 1?",
                Number(minimum=0, maximum=1, integer=False, optional=True),
            ),
        ),
    ),
    Recipe(
        label="Put a weather system on the map",
        tag="spawnFront",
        group="Place and time",
        asks=(
            Ask(
                "front", "Which kind of front?", Select(options=Query("weatherFronts"))
            ),
            Ask("at", "Forming over where?", Select(options=Query("regions"))),
        ),
    ),
    Recipe(
        label="Start a fight",
        tag="startCombat",
        group="Combat and company",
        asks=(
            Ask(
                "against",
                "Against whom?",
                MultiSelect(options=Query("entities"), min_items=1),
            ),
            Ask("canFlee", "Can the player run?", Bool(optional=True), default=True),
            Ask(
                "onWin",
                "Which scene if they win?",
                Select(options=Query("scenes"), optional=True),
            ),
            Ask(
                "onLose",
                "Which scene if they lose?",
                Select(options=Query("scenes"), optional=True),
            ),
            Ask(
                "onFlee",
                "Which scene if they run?",
                Select(options=Query("scenes"), optional=True),
            ),
        ),
        help=(
            "Writing all three outcomes is how a fight has consequences rather "
            "than just a result."
        ),
    ),
    Recipe(
        label="Somebody joins the player",
        tag="attachAlly",
        group="Combat and company",
        asks=(
            Ask("entity", "Who?", _ANY_ENTITY),
            Ask("until", "Until what?", ConditionBuilder(single=True)),
        ),
    ),
    Recipe(
        label="Somebody leaves",
        tag="dismissAlly",
        group="Combat and company",
        asks=(Ask("entity", "Who?", _ANY_ENTITY),),
    ),
    Recipe(
        label="Move a quest along",
        tag="advanceQuest",
        group="The story",
        asks=(
            Ask("quest", "Which quest?", Select(options=Query("quests"))),
            Ask("stage", "To which stage?", Text(optional=True)),
        ),
    ),
    Recipe(
        label="Raise or clear a flag",
        tag="setFlag",
        group="The story",
        asks=(
            Ask("entity", "On whom or what?", _ANY_ENTITY),
            Ask("flag", "Which flag?", Text(placeholder="has-spoken")),
            Ask("value", "Set it, or clear it?", Bool(optional=True), default=True),
        ),
    ),
    Recipe(
        label="Remember a value",
        tag="setVar",
        group="The story",
        help="Readable from expressions as `vars.name`.",
        asks=(
            Ask("name", "Called what?", Text(placeholder="kingWarned")),
            Ask("value", "Set to what?", Text()),
        ),
    ),
    Recipe(
        label="Play another scene",
        tag="playScene",
        group="The story",
        asks=(Ask("", "Which scene?", Select(options=Query("scenes"))),),
    ),
    Recipe(
        label="Make a world event happen now",
        tag="fireEvent",
        group="The story",
        asks=(Ask("", "Which event?", Select(options=Query("celestialEvents"))),),
    ),
    Recipe(
        label="Push an event closer to happening",
        tag="setPressure",
        group="The story",
        help="An act-two beat that lets the simulation deliver act three.",
        asks=(
            Ask("event", "Which event?", Select(options=Query("pressureEvents"))),
            Ask(
                "value",
                "How close, 0 to 1?",
                Number(minimum=0, maximum=1, integer=False),
            ),
        ),
    ),
    Recipe(
        label="Pass on some news",
        tag="tellNews",
        group="The story",
        help="Things that happened where the player was not.",
        asks=(
            Ask(
                "count", "How many items?", Number(minimum=1, optional=True), default=1
            ),
            Ask(
                "maxDaysOld",
                "Nothing older than how many days?",
                Number(minimum=0, optional=True),
            ),
        ),
    ),
    Recipe(
        label="End the game",
        tag="endGame",
        group="The story",
    ),
    Recipe(
        label="Start over",
        tag="restart",
        group="The story",
    ),
)


def _plant(payload: dict[str, Any], path: list[str], value: Any) -> None:
    """Put one answer into a payload, at a possibly-nested key.

    Parameters
    ----------
    payload : dict
        What is being built.
    path : list of str
        The dotted key, split.
    value : object
        The answer.
    """
    current = payload
    for key in path[:-1]:
        nested = current.get(key)
        if not isinstance(nested, dict):
            nested = {}
            current[key] = nested
        current = nested
    current[path[-1]] = value
