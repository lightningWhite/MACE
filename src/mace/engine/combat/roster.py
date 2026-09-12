"""Who is in a fight, and what each of them can actually do.

The engine's whole knowledge of the counter matrix is here, and it amounts to
one sentence: a defense's `type` is the name a response goes by, and an
attack's `counters` lists the ones that beat it. Nothing else in the engine
knows that `dodge` beats `overhead`, which is what lets a sci-fi pack answer a
plasma lance with `overload` and change no code.

A fighter's moves come from three places, in this order: its combat profile,
extra moves on its own `combat:` block, and whatever it is holding. Carrying a
dagger is how a fighter gets a `parry` to answer with, and losing it is how
they stop having one.
"""

from __future__ import annotations

from dataclasses import dataclass

from mace.content import ContentError, Library
from mace.content.ids import split
from mace.engine.combat.resolution import NEUTRAL_STAT
from mace.engine.context import RuleContext
from mace.engine.state import Combatant, EntityState
from mace.engine.stats import effective, pool_bounds
from mace.model import CombatProfile, Damage, Entity, ItemProps, Move, Range

__all__ = ["FLEE", "RECOVER", "RESERVED_RESPONSES", "Fighter", "fighter_for"]

#: Responses the engine supplies rather than content. `flee` is always
#: available where fleeing is allowed at all, and `recover` is the exchange
#: you spend catching your breath — the pacing half of the combat skill.
FLEE = "flee"
RECOVER = "recover"

#: Spend the exchange directing your allies instead of answering. Offered only
#: when there is somebody to direct and more than one thing to direct them at
#: — an order with one target and nobody to give it to is a button.
FOCUS = "focus"

#: Reach for something in your pack instead of answering. The response carries
#: the item after a colon — `use:fantasy.core:healing-draught` — because unlike
#: an order there is no sensible way to cycle through potions.
USE = "use"

RESERVED_RESPONSES = frozenset({FLEE, RECOVER, FOCUS})

#: The stats combat reads directly, by name, regardless of what a pack calls
#: everything else. Left undeclared, these fall back to `NEUTRAL_STAT` rather
#: than the ordinary "no such stat" zero (`Fighter.stat`) — zero is not a
#: no-op for either of them.
_NEUTRAL_DEFAULTS = frozenset({"strength", "speed"})

#: What a fighter hits with when it is holding nothing. Bare hands are worse
#: than a billhook and better than nothing, which is the only thing this needs
#: to be true.
UNARMED = Damage(min=1.0, max=3.0, type="unarmed")

#: How close or far bare hands work. Grappling range — short, and the sweet
#: spot sits right in the middle of it, because there is no "ideal" distance
#: for a fist beyond "close enough" (docs/07-combat.md § Range).
UNARMED_RANGE = Range(min=0.0, max=4.0, sweet_min=1.0, sweet_max=3.0)


@dataclass(frozen=True, slots=True)
class Fighter:
    """One combatant, with its content and its state resolved together.

    Built fresh for each exchange rather than stored, because everything in it
    is derived: an entity that drops its sword mid-fight has different answers
    on the next exchange, and a `Fighter` that had cached them would be lying.

    Attributes
    ----------
    combatant : Combatant
        The fight-scoped part: meter, pattern, momentum.
    state : EntityState
        The durable part: pools, inventory, what it is holding.
    definition : Entity
        The content it was instantiated from.
    profile : CombatProfile or None
        How it fights. None means it has none and can only take the hit.
    attacks : tuple of tuple
        Qualified id and definition of every attack it knows.
    defenses : tuple of tuple
        The same for defenses.
    weapon : str or None
        Qualified id of what it is hitting with, or None for bare hands.
    weapon_damage : Damage
        That weapon's damage range, or `UNARMED`.
    weapon_range : Range
        That weapon's range, or `UNARMED_RANGE`. What `strike` — the
        damage-carrying defense every profile shares — reads its own range
        from, the same way it already reads `weapon_damage`
        (docs/07-combat.md § Range).
    armor : float
        What its gear takes off every hit.
    """

    combatant: Combatant
    state: EntityState
    definition: Entity
    profile: CombatProfile | None
    attacks: tuple[tuple[str, Move], ...] = ()
    defenses: tuple[tuple[str, Move], ...] = ()
    weapon: str | None = None
    weapon_damage: Damage = UNARMED
    weapon_range: Range = UNARMED_RANGE
    armor: float = 0.0

    @property
    def actor(self) -> str:
        """The entity's instance id.

        Returns
        -------
        str
            The instance id.
        """
        return self.state.instance_id

    @property
    def name(self) -> str:
        """What to call this fighter.

        Returns
        -------
        str
            The entity's name.
        """
        return self.definition.name

    @property
    def responses(self) -> tuple[str, ...]:
        """The defense types this fighter can answer with, in a stable order.

        Returns
        -------
        tuple of str
            Each type once, in the order the moves were gathered.
        """
        seen: dict[str, None] = {}
        for _qualified, move in self.defenses:
            seen.setdefault(move.type, None)
        return tuple(seen)

    def defense(self, response: str) -> tuple[str, Move] | None:
        """The move this fighter would use to answer with a given type.

        Parameters
        ----------
        response : str
            A defense type, such as `parry`.

        Returns
        -------
        tuple or None
            The qualified id and move, or None when it knows no such answer.
        """
        for qualified, move in self.defenses:
            if move.type == response:
                return qualified, move
        return None

    def stat(self, name: str) -> float:
        """One effective stat, environment and modifiers included.

        Parameters
        ----------
        name : str
            The stat.

        Returns
        -------
        float
            Its value, 0 when the entity has no such stat — except
            `strength` and `speed`, which combat reads directly (`power()`,
            `window_ms()`, flee odds). Those two default to `NEUTRAL_STAT`
            instead: an entity that never declared one shouldn't fight at
            half power or on a badly skewed clock just because an author
            didn't know the name was special.
        """
        if name in _NEUTRAL_DEFAULTS and name not in (self.definition.stats or {}):
            return NEUTRAL_STAT
        return effective(self.definition, self.state, name)

    def pool(self, name: str) -> float:
        """The current value of one pool.

        Parameters
        ----------
        name : str
            The pool.

        Returns
        -------
        float
            The stored value.
        """
        return float(self.state.pools.get(name, 0.0))

    def pool_max(self, name: str) -> float:
        """The ceiling of one pool.

        Parameters
        ----------
        name : str
            The pool.

        Returns
        -------
        float
            Its maximum.
        """
        return pool_bounds(self.definition, self.state, name)[1]

    def skill_with(self, item_id: str | None) -> float:
        """How practised this fighter is with what it is holding.

        Parameters
        ----------
        item_id : str or None
            The qualified item id, or None for bare hands.

        Returns
        -------
        float
            The stored skill, 0 to 100.
        """
        if item_id is None:
            return 0.0
        return float(self.state.skills.get(item_id, 0.0))

    def familiarity_with(self, profile: str | None) -> float:
        """How well this fighter knows an opponent's habits, 0 to 1.

        Parameters
        ----------
        profile : str or None
            The qualified profile id of what it is facing.

        Returns
        -------
        float
            0 for a stranger, 1 for something fought many times.
        """
        if profile is None:
            return 0.0
        seen = self.state.familiarity.get(profile, 0)
        return min(1.0, seen / FAMILIARITY_FULL)


#: How many correct reads against one profile count as knowing it. Deliberately
#: reachable in three or four fights: the character is supposed to learn trolls
#: alongside the player, not instead of them.
FAMILIARITY_FULL = 40.0


def fighter_for(
    combatant: Combatant, context: RuleContext, *, cache: dict[str, Entity]
) -> Fighter:
    """Resolve one combatant against the content it is made of.

    Parameters
    ----------
    combatant : Combatant
        The fight-scoped part.
    context : RuleContext
        The playthrough.
    cache : dict
        A per-call cache of qualified item id to definition, so a fight with
        four wolves in it does not look the same dagger up sixteen times.

    Returns
    -------
    Fighter
        The resolved fighter.

    Raises
    ------
    RuleError
        If the combatant's entity is no longer in the session.
    """
    from mace.engine.conditions import RuleError  # noqa: PLC0415

    state = context.state.entities.get(combatant.actor)
    if state is None:  # pragma: no cover — combatants are added with entities
        raise RuleError(f"`{combatant.actor}` is not in this session any more")

    definition = context.definition(state)
    profile = _profile(combatant.profile, context.library)

    gear = _gear(state, context.library, cache)

    references: list[str] = []
    if profile is not None:
        references.extend(profile.moves)
    if definition.combat is not None:
        references.extend(definition.combat.moves)
    for item_id, item in gear:
        home = split(item_id)[0]
        references.extend(
            reference if ":" in reference or home is None else f"{home}:{reference}"
            for reference in item.moves
        )

    home = split(state.definition)[0] or context.state.pack

    attacks: list[tuple[str, Move]] = []
    defenses: list[tuple[str, Move]] = []
    seen: set[str] = set()
    for reference in references:
        found = _move(reference, context.library, within=home)
        if found is None or found[0] in seen:
            continue
        seen.add(found[0])
        (defenses if found[1].kind == "defense" else attacks).append(found)

    weapon: str | None = None
    weapon_damage: Damage = UNARMED
    weapon_range: Range = UNARMED_RANGE
    for item_id, item in gear:
        if item.damage is not None:
            weapon = item_id
            weapon_damage = item.damage
            weapon_range = item.range or UNARMED_RANGE
            break

    return Fighter(
        combatant=combatant,
        state=state,
        definition=definition,
        profile=profile,
        attacks=tuple(attacks),
        defenses=tuple(defenses),
        weapon=weapon,
        weapon_damage=weapon_damage,
        weapon_range=weapon_range,
        armor=sum(float(item.armor or 0.0) for _id, item in gear),
    )


def _gear(
    state: EntityState, library: Library, cache: dict[str, Entity]
) -> list[tuple[str, ItemProps]]:
    """What a fighter is holding, in a stable order.

    An item whose `ammo` has run out is left out entirely — it grants no
    moves, and it cannot be `weapon`/`weapon_damage`/`weapon_range` any more,
    the same as if it had never been equipped. It stays *equipped* (nothing
    here unequips it); a fighter with nothing else to hold falls back to bare
    hands until they spend an exchange on `equip:<item>` to swap it out.

    Parameters
    ----------
    state : EntityState
        The fighter's state.
    library : Library
        The loaded content.
    cache : dict
        Qualified item id to definition, shared across a whole fight so four
        wolves do not look the same dagger up sixteen times.

    Returns
    -------
    list of tuple
        Qualified item id and its `item:` block, slot order.
    """
    held: list[tuple[str, ItemProps]] = []
    for _slot, item_id in sorted(state.equipment.items()):
        item = cache.get(item_id)
        if item is None:
            found = _look_up(library, item_id)
            if found is None:
                continue
            cache[item_id] = item = found
        if item.item is None:
            continue
        props = item.item
        if props.ammo is not None and state.ammo.get(item_id, props.ammo) <= 0:
            continue
        held.append((item_id, props))
    return held


def _look_up(library: Library, qualified: str) -> Entity | None:
    """Find an entity definition by qualified id.

    Parameters
    ----------
    library : Library
        The loaded content.
    qualified : str
        The qualified id.

    Returns
    -------
    Entity or None
        The definition, or None when the content is no longer there.
    """
    pack_id, local_id = split(qualified)
    if pack_id is None:  # pragma: no cover — state ids are always qualified
        return None
    try:
        return library.pack(pack_id).entities.get(local_id)
    except ContentError:  # pragma: no cover — the pack was loaded to get here
        return None


def _profile(qualified: str | None, library: Library) -> CombatProfile | None:
    """Find a combat profile by qualified id.

    Parameters
    ----------
    qualified : str or None
        The qualified id, or None.
    library : Library
        The loaded content.

    Returns
    -------
    CombatProfile or None
        The profile.
    """
    if qualified is None:
        return None
    pack_id, local_id = split(qualified)
    if pack_id is None:  # pragma: no cover — stored ids are qualified
        return None
    try:
        return library.pack(pack_id).combat_profiles.get(local_id)
    except ContentError:  # pragma: no cover
        return None


def _move(reference: str, library: Library, *, within: str) -> tuple[str, Move] | None:
    """Resolve a move reference to its qualified id and definition.

    Parameters
    ----------
    reference : str
        As the author wrote it.
    library : Library
        The loaded content.
    within : str
        The pack the reference was written in.

    Returns
    -------
    tuple or None
        The qualified id and the move, or None when it names nothing.
    """
    try:
        qualified = library.resolve(reference, "moves", within=within)
    except ContentError:
        return None
    pack_id, local_id = split(qualified)
    assert pack_id is not None
    return qualified, library.pack(pack_id).moves[local_id]
