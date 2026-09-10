"""Saying conditions and effects in English.

The v0 wizard's worst moment was `defineConditions()`, which printed a syntax
explanation and asked the author to type `player.location == castle`. Its
replacement is a guided cascade — and a cascade is only worth having if the
thing it produces reads back in the language the author was thinking in.

So this module is the other half of the builders: one function that turns any
authored condition into a sentence, and one that does the same for an effect.
Everything in the wizard that shows an author what they already have goes
through here, which is why an author can build a whole game and only see YAML
if they go looking for it.

Rendering is deliberately *lossy about syntax and exact about meaning*. It
names things by their `name` where they have one, since `Bridge Troll` is what
the author called it and `fantasy.core:bridge-troll` is what the file calls it.
It never invents information: a reference that resolves to nothing is shown as
the author wrote it, because a dangling reference the wizard quietly
prettified would be a dangling reference nobody found.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from mace.content import ContentError, Library
from mace.engine.expr import Expression
from mace.model import Condition, Effect
from mace.model.base import ContentModel
from mace.wizard.query import Catalog

__all__ = ["Names", "say_condition", "say_conditions", "say_effect", "say_effects"]

#: How the reserved actor names read.
RESERVED_LABELS = {"player": "the player"}

#: Collections a reference in each payload field points into, for the fields
#: whose name does not say. Everything else is looked up by its field name.
_FIELD_COLLECTIONS: dict[str, str] = {
    "actor": "entities",
    "against": "entities",
    "at": "regions",
    "entity": "entities",
    "event": "celestialEvents",
    "front": "weatherFronts",
    "heading": "regions",
    "in_region": "regions",
    "item": "entities",
    "location": "locations",
    "on_flee": "scenes",
    "on_lose": "scenes",
    "on_win": "scenes",
    "quest": "quests",
    "route": "routes",
    "scene": "scenes",
    "source": "entities",
    "target": "entities",
    "to": "entities",
}


@dataclass(frozen=True, slots=True)
class Names:
    """Turns content references into the words an author used for them.

    Attributes
    ----------
    library : Library or None
        Where to look definitions up. None renders every reference as written,
        which is what a project holding content that does not compile yet
        needs — an author mid-sentence still gets readable output.
    within : str
        The pack references are written inside.
    catalog : Catalog or None
        An open project, consulted before the library. This is what lets the
        wizard name the author's own half-written objects: a location that
        does not compile has no model to read a `name` off, and its raw
        mapping has one all the same.
    """

    library: Library | None = None
    within: str = ""
    catalog: Catalog | None = None

    def of(self, reference: str, collection: str) -> str:
        """What to call one reference.

        Parameters
        ----------
        reference : str
            As the author wrote it.
        collection : str
            Which collection it points into.

        Returns
        -------
        str
            The definition's `name`, or a readable form of the id.
        """
        if reference in RESERVED_LABELS:
            return RESERVED_LABELS[reference]
        if self.catalog is not None:
            labelled = self.catalog.label(reference, collection)
            if labelled != reference:
                return labelled
        if self.library is not None:
            try:
                found = self.library.find(reference, collection, within=self.within)
            except (ContentError, KeyError):
                found = None
            named = getattr(found, "name", None)
            if isinstance(named, str) and named:
                return named
        return reference.split(":", 1)[-1].replace("-", " ")

    def possessive(self, reference: str) -> str:
        """An actor's name in the possessive, for `the player's strength`.

        Parameters
        ----------
        reference : str
            The actor.

        Returns
        -------
        str
            `the player's`, `Gorm's`.
        """
        name = self.of(reference, "entities")
        return f"{name}'" if name.endswith("s") else f"{name}'s"


def say_conditions(conditions: Sequence[Condition], names: Names) -> str:
    """Say a list of conditions, which are ANDed.

    Parameters
    ----------
    conditions : sequence of Condition
        The conditions.
    names : Names
        The naming service.

    Returns
    -------
    str
        One sentence, or "always" for an empty list — which is what an empty
        `when` means and worth saying out loud.
    """
    if not conditions:
        return "always"
    return _joined([say_condition(one, names) for one in conditions], "and")


def say_condition(condition: Condition, names: Names) -> str:
    """Say one condition.

    Parameters
    ----------
    condition : Condition
        The condition.
    names : Names
        The naming service.

    Returns
    -------
    str
        A phrase that fits after "when".
    """
    body = condition.payload
    tag = condition.tag
    get = _getter(body)

    if tag in {"all", "any"}:
        joiner = "and" if tag == "all" else "or"
        return _joined([say_condition(one, names) for one in get("conditions")], joiner)
    if tag == "not":
        return f"not ({say_condition(get('condition'), names)})"

    if tag == "hasItem":
        item = names.of(get("item"), "entities")
        qty = get("qty")
        carried = item if qty == 1 else f"at least {qty} {item}"
        return f"{names.of(get('actor'), 'entities')} is carrying {carried}"
    if tag == "atLocation":
        actor = names.of(get("actor"), "entities")
        return f"{actor} is at {names.of(get('location'), 'locations')}"
    if tag == "flag":
        entity = names.of(get("entity"), "entities")
        mark = "is" if get("is_") else "is not"
        return f"{entity} {mark} flagged `{get('flag')}`"
    if tag in {"statAtLeast", "statAtMost"}:
        bound = "at least" if tag == "statAtLeast" else "at most"
        whose = names.possessive(get("actor"))
        return f"{whose} {get('stat')} is {bound} {_number(get('value'))}"
    if tag == "questStage":
        quest = names.of(get("quest"), "quests")
        return f"{quest} is at the `{get('stage')}` stage"
    if tag in {"questComplete", "questFailed"}:
        state = "is complete" if tag == "questComplete" else "has failed"
        return f"{names.of(get('quest'), 'quests')} {state}"
    if tag == "chance":
        return f"a {_percent(get('probability'))} chance"
    if tag == "expr":
        return f"`{get('expression').source}` is true"
    if tag == "weather":
        conditions = [names.of(one, "weatherConditions") for one in get("conditions")]
        return f"the weather is {_joined(conditions, 'or')}"
    if tag == "weatherTag":
        return f"the weather is {_joined(list(get('tags')), 'or')}"
    if tag == "season":
        return f"it is {_joined(list(get('seasons')), 'or')}"
    if tag == "dayPart":
        return f"it is {_joined(list(get('parts')), 'or')}"
    if tag == "priceOf":
        return _price(get, names)

    return f"[{tag}] {_arguments(body, names)}"  # pragma: no cover — new tag


def _price(get: Any, names: Names) -> str:
    """Say a price band in the words an author was thinking in.

    Parameters
    ----------
    get : callable
        Field reader for the payload.
    names : Names
        The naming service.

    Returns
    -------
    str
        `grain costs over 1.5× its usual price at Fenmoor`.
    """
    good = names.of(get("good"), "goods")
    above, below = get("above"), get("below")
    if above is not None and below is not None:
        band = f"between {_number(above)}× and {_number(below)}× its usual price"
    elif above is not None:
        band = f"over {_number(above)}× its usual price"
    else:
        band = f"under {_number(below)}× its usual price"

    market = get("market")
    where = " here" if market is None else f" at {names.of(market, 'markets')}"
    return f"{good} costs {band}{where}"


def _shock(get: Any, names: Names) -> str:
    """Say a price shock in the words an author was thinking in.

    Parameters
    ----------
    get : callable
        Field reader for the payload.
    names : Names
        The naming service.

    Returns
    -------
    str
        `food doubles in price in The Range, fading over 600 ticks`.
    """
    good, category = get("good"), get("category")
    if good is not None:
        what = names.of(good, "goods")
    elif category is not None:
        what = f"anything {category}"
    else:
        what = "everything"

    mult = get("mult")
    moves = (
        f"costs {_number(mult)}× as much" if mult >= 1 else f"costs {_number(mult)}×"
    )

    market, region = get("market"), get("region")
    if market is not None:
        where = f" at {names.of(market, 'markets')}"
    elif region is not None:
        where = f" in {names.of(region, 'regions')}"
    else:
        where = " everywhere"

    return f"{what} {moves}{where}, fading over {_ticks(get('decay_ticks'))}"


def say_effects(effects: Sequence[Effect], names: Names) -> str:
    """Say a list of effects, which happen in order.

    Parameters
    ----------
    effects : sequence of Effect
        The effects.
    names : Names
        The naming service.

    Returns
    -------
    str
        One sentence, or "nothing happens" for an empty list.
    """
    if not effects:
        return "nothing happens"
    return _joined([say_effect(one, names) for one in effects], "then")


def say_effect(effect: Effect, names: Names) -> str:
    """Say one effect.

    Parameters
    ----------
    effect : Effect
        The effect.
    names : Names
        The naming service.

    Returns
    -------
    str
        A phrase describing the change.
    """
    body = effect.payload
    tag = effect.tag
    get = _getter(body)

    if tag == "adjustStat":
        delta = get("delta")
        whose = names.possessive(get("actor"))
        return f"{_moved(delta, whose, get('stat'))}{_because(get('reason'))}"
    if tag == "setStat":
        whose = names.possessive(get("actor"))
        return f"{whose} {get('stat')} becomes {_value(get('value'))}"
    if tag == "applyModifier":
        whose = names.possessive(get("actor"))
        parts = []
        if get("add") is not None:
            parts.append(f"{'+' if get('add') >= 0 else '−'}{_number(abs(get('add')))}")
        if get("mult") is not None:
            parts.append(f"×{_number(get('mult'))}")
        label = f" ({get('label')})" if get("label") else ""
        return (
            f"{' and '.join(parts)} to {whose} {get('stat')} "
            f"for {_ticks(get('ticks'))}{label}"
        )
    if tag == "setDisposition":
        return f"{names.of(get('actor'), 'entities')} turns {get('to')}"
    if tag in {"giveItem", "takeItem"}:
        verb = "gains" if tag == "giveItem" else "loses"
        item = names.of(get("item"), "entities")
        qty = get("qty")
        return (
            f"{names.of(get('actor'), 'entities')} {verb} "
            f"{item if qty == 1 else f'{qty} {item}'}"
        )
    if tag == "transferContents":
        source = names.of(get("source"), "entities")
        return f"everything {source} has moves to {names.of(get('target'), 'entities')}"
    if tag == "move":
        actor = names.of(get("actor"), "entities")
        return f"{actor} is moved to {names.of(get('to'), 'locations')}"
    if tag == "setFlag":
        entity = names.of(get("entity"), "entities")
        mark = "is flagged" if get("value") else "loses the flag"
        return f"{entity} {mark} `{get('flag')}`"
    if tag == "setVar":
        return f"`{get('name')}` becomes {_value(get('value'))}"
    if tag == "reveal":
        return f"{names.of(get('location'), 'locations')} appears on the map"
    if tag == "say":
        lines = get("lines")
        return (
            f'it says "{lines[0].text}"'
            if len(lines) == 1
            else f"{len(lines)} lines are spoken"
        )
    if tag == "advanceQuest":
        quest = names.of(get("quest"), "quests")
        stage = get("stage")
        return f"{quest} moves to `{stage}`" if stage else f"{quest} moves on"
    if tag == "startCombat":
        against = [names.of(one, "entities") for one in get("against")]
        tail = "" if get("can_flee") else ", and you cannot run"
        return f"a fight starts against {_joined(against, 'and')}{tail}"
    if tag == "attachAlly":
        entity = names.of(get("entity"), "entities")
        until = get("until")
        held = "" if until is None else f" until {say_condition(until, names)}"
        return f"{entity} travels with you{held}"
    if tag == "dismissAlly":
        return f"{names.of(get('entity'), 'entities')} goes their own way"
    if tag == "advanceTime":
        return f"{_ticks(get('ticks'))} pass"
    if tag == "rest":
        pools = get("pools")
        what = _joined(list(pools), "and") if pools else "every pool"
        return f"you rest {_ticks(get('ticks'))}, refilling {what}"
    if tag == "closeRoute":
        route = names.of(get("route"), "routes")
        return f"{route} closes{' for good' if get('permanent') else ''}"
    if tag == "openRoute":
        return f"{names.of(get('route'), 'routes')} reopens"
    if tag == "marketShock":
        return _shock(get, names)
    if tag == "setRouteTicks":
        route = names.of(get("route"), "routes")
        return f"{route} now takes {_ticks(get('ticks'))}"
    if tag == "spawnEntity":
        who = names.of(get("entity"), "entities")
        at = get("at")
        where = " here" if at is None else f" at {names.of(at, 'locations')}"
        lingers = "" if get("transient") else ", and stays"
        return f"{who} appears{where}{lingers}"
    if tag == "spawnFront":
        front = names.of(get("front"), "weatherFronts")
        return f"{front} forms over {names.of(get('at'), 'regions')}"
    if tag == "damage":
        region = get("in_region")
        who = (
            f"everyone in {names.of(region, 'regions')}"
            if region
            else names.of(get("actor") or "player", "entities")
        )
        return f"{who} takes {_number(get('amount'))}{_because(get('reason'))}"
    if tag == "setLight":
        light = get("light")
        if light is None:
            return "the light goes back to whatever the sky is doing"
        return f"the light becomes {_number(light)}"
    if tag == "fireEvent":
        return f"{names.of(get('event'), 'celestialEvents')} happens now"
    if tag == "setPressure":
        event = names.of(get("event"), "pressureEvents")
        return f"{event} is {_percent(get('value'))} of the way to happening"
    if tag == "tellNews":
        count = get("count")
        return (
            f"you hear {'a piece of news' if count == 1 else f'{count} pieces of news'}"
        )
    if tag == "playScene":
        return f"the `{get('scene')}` scene plays"
    if tag == "endGame":
        return "the game ends"
    if tag == "restart":
        return "the game starts over"

    return f"[{tag}] {_arguments(body, names)}"  # pragma: no cover — new tag


def _getter(body: ContentModel) -> Any:
    """Read a payload's fields, tolerating the ones a tag does not have.

    Several tags share one payload — `questComplete` and `questFailed` both
    use `QuestOutcome` — and one renderer covering a family should not have to
    know which fields the family member it was handed carries.

    Parameters
    ----------
    body : ContentModel
        The payload.

    Returns
    -------
    callable
        A function from field name to value, or None.
    """

    def get(name: str) -> Any:
        return getattr(body, name, None)

    return get


def _arguments(body: ContentModel, names: Names) -> str:
    """Fall back to naming a payload's fields, for a tag with no phrasing yet.

    Reached only when the vocabulary grows and this module has not caught up.
    The square brackets are deliberate: an author seeing `[dazzle] actor: the
    player` knows they are looking at a gap in the tool rather than at a
    sentence, and a test keys off the same marker.

    Parameters
    ----------
    body : ContentModel
        The payload.
    names : Names
        The naming service.

    Returns
    -------
    str
        `actor: the player, stat: strength`, behind a bracketed tag.
    """
    said = []
    for name in type(body).model_fields:
        value = getattr(body, name)
        if value is None:
            continue
        collection = _FIELD_COLLECTIONS.get(name)
        shown = (
            names.of(value, collection)
            if collection and isinstance(value, str)
            else value
        )
        said.append(f"{name}: {shown}")
    return ", ".join(said)


def _joined(parts: Sequence[str], joiner: str) -> str:
    """Join phrases the way a person writes a list.

    Parameters
    ----------
    parts : sequence of str
        The phrases.
    joiner : str
        `and`, `or`, `then`.

    Returns
    -------
    str
        `a`, `a and b`, `a, b and c`.
    """
    kept = [part for part in parts if part]
    if not kept:
        return ""
    if len(kept) == 1:
        return kept[0]
    return f"{', '.join(kept[:-1])} {joiner} {kept[-1]}"


def _moved(delta: Any, whose: str, stat: str) -> str:
    """Say a relative change without a verb that has to agree with a stat name.

    "The player's hitpoints goes down by 8" is wrong and "go down" is wrong for
    `strength`, and there is no rule that gets both right — stat names are
    author-chosen and half of them are plural. Putting the number first sidesteps
    the agreement entirely.

    Parameters
    ----------
    delta : object
        The literal or expression.
    whose : str
        The possessive form of the actor.
    stat : str
        The stat's name.

    Returns
    -------
    str
        `8 comes off the player's hitpoints`, `5 goes onto Gorm's speed`.
    """
    if isinstance(delta, Expression):
        return f"{whose} {stat} changes by `{delta.source}`"
    number = float(delta)
    if number < 0:
        return f"{_number(-number)} comes off {whose} {stat}"
    return f"{_number(number)} goes onto {whose} {stat}"


def _value(value: Any) -> str:
    """Say an authored value, literal or expression.

    Parameters
    ----------
    value : object
        The value.

    Returns
    -------
    str
        Its rendering.
    """
    if isinstance(value, Expression):
        return f"`{value.source}`"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return _number(value)
    return str(value)


def _because(reason: str | None) -> str:
    """Attach a reason where the author gave one.

    Parameters
    ----------
    reason : str or None
        The author's reason.

    Returns
    -------
    str
        ` (the club)`, or nothing.
    """
    return f" ({reason})" if reason else ""


def _ticks(count: int) -> str:
    """Say a tick count with its unit.

    Parameters
    ----------
    count : int
        How many ticks.

    Returns
    -------
    str
        `1 tick`, `8 ticks`.
    """
    return f"{count} tick" if count == 1 else f"{count} ticks"


def _percent(fraction: float) -> str:
    """Say a 0-to-1 share as a percentage.

    Parameters
    ----------
    fraction : float
        The share.

    Returns
    -------
    str
        `15%`.
    """
    return f"{_number(fraction * 100)}%"


def _number(value: float) -> str:
    """Render a number without a pointless decimal point.

    Parameters
    ----------
    value : float
        The number.

    Returns
    -------
    str
        `8` rather than `8.0`.
    """
    return str(int(value)) if float(value).is_integer() else str(round(value, 4))
