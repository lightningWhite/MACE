"""Scaffolding: something to rearrange instead of a blank page.

An author staring at an empty world is an author who stops. These produce
content that is **always editable and never mandatory** — a map to move around,
a table to retune — and they are strictly an authoring assist. Nothing here
runs during a session (open question 7): the variety a player experiences comes
from simulation, which is consistent and learnable, and not from generation,
which cannot be balanced and would undermine the replay contract.

Two rules the implementation keeps.

**Genre-neutral.** The engine knows nothing about swords, so neither does this.
A flavour is a list of words and a shape is a graph; the word lists are
scaffolding an author is expected to rename, and the shapes are the same in
every genre because "a road between two settlements" is not a fantasy idea.

**Seeded, not random.** Generation goes through the same RNG service the engine
uses, so "give me another one" is a different seed rather than a dice roll, and
an author who liked the third one can get it back.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mace.engine.rng import RandomSource
from mace.wizard.project import Project

__all__ = [
    "FLAVOURS",
    "PRESETS",
    "Flavour",
    "Preset",
    "start_world",
    "suggest_table",
]


@dataclass(frozen=True, slots=True)
class Preset:
    """One road-feel setting, from the tuning table in the docs.

    Attributes
    ----------
    label : str
        What the author picks.
    chance : float
        The probability that something happens, per roll.
    threat_share : float
        How much of the weight goes to entries that are actually dangerous.
        The rest is atmosphere, and it is the atmosphere that makes the
        threats land — a road where a third of legs produce a fight reads as
        a grind rather than as danger.
    """

    label: str
    chance: float
    threat_share: float


#: The presets from docs/06-travel-and-encounters.md § Tuning guidance, so an
#: author picks a feeling rather than guessing at a float.
PRESETS: tuple[Preset, ...] = (
    Preset("Safe king's highway", 0.10, 0.10),
    Preset("Ordinary country road", 0.25, 0.25),
    Preset("Wild forest track", 0.35, 0.45),
    Preset("Bandit country", 0.45, 0.65),
    Preset("The mountain pass", 0.60, 0.80),
)

#: Which preset a route's `dangerLevel` maps to. Ten steps onto five presets,
#: because `dangerLevel` is a note an author leaves themselves and the presets
#: are the vocabulary the numbers mean something in.
_BY_DANGER: tuple[int, ...] = (0, 0, 1, 1, 2, 2, 2, 3, 3, 4, 4)


@dataclass(frozen=True, slots=True)
class Flavour:
    """Words to build a starter map out of.

    Not a genre system. A flavour is a naming palette and nothing else — the
    shape of the map it produces is identical in all of them, because a hub
    with settlements around it is not a fantasy idea.

    Attributes
    ----------
    id, label : str
        Identity.
    hub : tuple of str
        Names for the biggest place.
    settlements : tuple of str
        Names for the places around it.
    wilds : tuple of str
        Names for the dangerous place at the far end.
    regions : tuple of str
        Names for the regions.
    """

    id: str
    label: str
    hub: tuple[str, ...]
    settlements: tuple[str, ...]
    wilds: tuple[str, ...]
    regions: tuple[str, ...]


FLAVOURS: tuple[Flavour, ...] = (
    Flavour(
        id="settled-land",
        label="A settled land — villages, a market town, a road out",
        hub=("Market Cross", "Ashford", "Kingsbridge"),
        settlements=("Fenmoor", "Little Weld", "Barrow End", "Hollowbeck", "Netherby"),
        wilds=("The Deep Wood", "The High Moor", "The Old Pass"),
        regions=("The Lowlands", "The Marches", "The Uplands"),
    ),
    Flavour(
        id="frontier",
        label="A frontier — a landing, a few holds, and everything else",
        hub=("Landfall", "The Landing", "Waystation One"),
        settlements=("Coldwater", "Second Camp", "The Drift", "Longshore", "Redhill"),
        wilds=("The Waste", "The Breaks", "The Far Side"),
        regions=("The Basin", "The Reach", "The Outer Waste"),
    ),
    Flavour(
        id="stations",
        label="Stations — a hub, its outposts, and the dark between",
        hub=("Central", "Terminus", "The Ring"),
        settlements=("Ceres Dock", "Halfway", "Bright Station", "The Yards", "Anchor"),
        wilds=("The Quiet Sector", "The Drift", "Deep Black"),
        regions=("The Inner Ring", "The Belt", "The Deep"),
    ),
)

#: How many places each size makes, hub included.
SIZES: Mapping[str, int] = {"small": 3, "medium": 5, "large": 8}

#: How long a road is, in ticks, by how far out it goes. Sensible rather than
#: correct: an author retunes these, and a starting number they can react to
#: beats an empty field they have to invent one for.
_NEAR, _FAR = 4, 10


def start_world(
    project: Project,
    *,
    flavour: str = "settled-land",
    size: str = "small",
    seed: str = "mace",
    climate: str | None = None,
) -> list[str]:
    """Put a plausible map into an empty project.

    A hub, some settlements around it, one dangerous place at the far end, a
    road from the hub to each, and a region per band. That shape is chosen
    because it is the smallest map that has a *decision* in it: somewhere safe,
    somewhere worth going, and a road between them long enough to be worth
    thinking about.

    Nothing is overwritten. Ids that already exist are skipped, so running this
    on a project that has been started adds what is missing rather than
    flattening what is there.

    Parameters
    ----------
    project : Project
        The pack to scaffold. Edited in place.
    flavour : str
        Which naming palette to use.
    size : str
        `small`, `medium`, or `large`.
    seed : str
        The generation seed. The same seed makes the same map, so an author
        who liked the third one can get it back.
    climate : str or None
        A climate to give every region, if one of the libraries has a suitable
        one. Regions without a climate simply have no weather.

    Returns
    -------
    list of str
        The ids that were created, in the order they were made.

    Raises
    ------
    KeyError
        If the flavour or size is not one that exists.
    """
    palette = next((one for one in FLAVOURS if one.id == flavour), None)
    if palette is None:
        raise KeyError(f"no flavour `{flavour}`; try {[one.id for one in FLAVOURS]}")
    if size not in SIZES:
        raise KeyError(f"no size `{size}`; try {sorted(SIZES)}")

    stream = RandomSource(seed).stream("wizard.world-starter")
    made: list[str] = []

    regions = _pick(stream, palette.regions, 2)
    for name in regions:
        _add(project, "regions", {"id": _slug(name), "name": name}, made, climate)

    hub = _pick(stream, palette.hub, 1)[0]
    wilds = _pick(stream, palette.wilds, 1)[0]
    settlements = _pick(stream, palette.settlements, SIZES[size] - 2)

    _place(project, hub, regions[0], made, safe=True)
    for name in settlements:
        _place(project, name, regions[0], made, safe=True)
    _place(project, wilds, regions[-1], made, safe=False)

    for name in (*settlements, wilds):
        ticks = _FAR if name == wilds else _NEAR
        _road(project, hub, name, ticks, made)

    return made


def _place(
    project: Project, name: str, region: str, made: list[str], *, safe: bool
) -> None:
    """Add one location, if there is not one by that id already.

    Parameters
    ----------
    project : Project
        The pack.
    name : str
        What to call it.
    region : str
        The region it sits in.
    made : list of str
        Accumulator of what was created.
    safe : bool
        Whether the player can rest here.
    """
    authored: dict[str, Any] = {
        "id": _slug(name),
        "name": name,
        "description": "Rename this, and say what it looks like.",
        "region": _slug(region),
    }
    if safe:
        authored["safe"] = True
    _add(project, "locations", authored, made)


def _road(
    project: Project, origin: str, destination: str, ticks: int, made: list[str]
) -> None:
    """Add one route between two places.

    Parameters
    ----------
    project : Project
        The pack.
    origin, destination : str
        The place names.
    ticks : int
        How long it takes in fair weather.
    made : list of str
        Accumulator.
    """
    local_id = f"{_slug(origin)}-to-{_slug(destination)}"
    _add(
        project,
        "routes",
        {
            "id": local_id,
            "name": f"The road to {destination}",
            "from": _slug(origin),
            "to": _slug(destination),
            "ticks": ticks,
            "dangerLevel": 2 if ticks <= _NEAR else 5,
        },
        made,
    )
    # A route is a road; an exit is the option to walk down it. Both, or the
    # map is a set of places nobody can leave — which the validator says out
    # loud, and a starter map that opens with five notes is not a good start.
    _exit(project, origin, destination, local_id)
    _exit(project, destination, origin, local_id)


def _exit(project: Project, at: str, to: str, route: str) -> None:
    """Give one place the option of walking down one road.

    Parameters
    ----------
    project : Project
        The pack.
    at : str
        The place the exit is on.
    to : str
        Where it leads.
    route : str
        The road it takes.
    """
    body = project.get("locations", _slug(at))
    if body is None:
        return
    exits = list(body.get("exits") or [])
    if any(one.get("to") == _slug(to) for one in exits if isinstance(one, Mapping)):
        return
    exits.append({"to": _slug(to), "route": route})
    project.put("locations", {**body, "exits": exits})


def _add(
    project: Project,
    collection: str,
    authored: Mapping[str, Any],
    made: list[str],
    climate: str | None = None,
) -> None:
    """Put one generated object into the project, without overwriting.

    Parameters
    ----------
    project : Project
        The pack.
    collection : str
        Which collection.
    authored : mapping
        The object.
    made : list of str
        Accumulator of what was created.
    climate : str or None
        A climate to attach, for regions.
    """
    local_id = str(authored["id"])
    if project.get(collection, local_id) is not None:
        return
    body = dict(authored)
    if climate is not None and collection == "regions":
        body["climate"] = climate
    project.put(collection, body)
    made.append(f"{collection}/{local_id}")


def suggest_table(
    project: Project,
    *,
    local_id: str,
    name: str,
    danger: int | None = None,
    preset: Preset | None = None,
) -> dict[str, Any]:
    """Propose an encounter table, drawn from what the libraries already have.

    The entries are not invented: they come from the tables the loaded
    libraries define, split into the ones that are threats and the ones that
    are atmosphere, and reweighted so the threat share matches the preset. That
    keeps every reference real, which is the whole point of the wizard, and it
    means a pack with a good library gets a good suggestion.

    The result is content, not a decision. It is written like anything else and
    an author is expected to retune it — the chance in particular, which is the
    one dial that decides how a road feels.

    Parameters
    ----------
    project : Project
        The pack, for its libraries.
    local_id : str
        The id to give the new table.
    name : str
        What to call it.
    danger : int or None
        A route's `dangerLevel`, 0 to 10, used to pick a preset.
    preset : Preset or None
        A preset chosen outright, which wins over `danger`.

    Returns
    -------
    dict
        The authored encounter table.
    """
    chosen = preset or PRESETS[_BY_DANGER[min(max(danger or 0, 0), 10)]]
    threats, atmosphere = _borrowed(project)

    # The share only means something when both halves exist. A library that
    # offers no fights cannot make a bandit road, and quietly handing back a
    # table whose weights add to 35 would be a table an author had to work out
    # was wrong — so the half that exists takes all of it.
    quiet = 1.0 if not threats else 1 - chosen.threat_share
    loud = 1.0 if not atmosphere else chosen.threat_share
    entries: list[dict[str, Any]] = []
    entries.extend(_weighted(atmosphere, 100 * quiet))
    entries.extend(_weighted(threats, 100 * loud))

    table: dict[str, Any] = {
        "id": local_id,
        "name": name,
        # A table that can roll and has nothing to roll is a load-time error,
        # so a suggestion drawn from libraries that offer nothing comes back
        # switched off rather than broken. The author gets the shape, and the
        # `chance` to turn up once they have written something to put in it.
        "chance": round(chosen.chance, 2) if entries else 0.0,
        "minGapTicks": 4,
        "pressureStep": 0.04,
    }
    if entries:
        table["entries"] = entries
    return table


def _borrowed(project: Project) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every entry the libraries offer, split into threats and atmosphere.

    Parameters
    ----------
    project : Project
        The pack, for its dependencies.

    Returns
    -------
    tuple of (list, list)
        Threat entries and atmosphere entries, each as authored mappings with
        their references qualified — they are being copied out of their own
        pack and into this one, and a bare id would mean something else here.
    """
    threats: list[dict[str, Any]] = []
    atmosphere: list[dict[str, Any]] = []
    for pack in project.dependencies.packs:
        for table in pack.encounter_tables.values():
            for entry in table.entries:
                authored = dict(entry.authored())
                if isinstance(authored.get("scene"), str):
                    authored["scene"] = _qualify(pack.id, str(authored["scene"]))
                if isinstance(authored.get("combat"), Mapping):
                    combat = dict(authored["combat"])
                    combat["against"] = [
                        _qualify(pack.id, str(one)) for one in combat["against"]
                    ]
                    authored["combat"] = combat
                (threats if "combat" in authored else atmosphere).append(authored)
    return threats, atmosphere


def _weighted(entries: Sequence[dict[str, Any]], share: float) -> list[dict[str, Any]]:
    """Spread a share of the total weight evenly across some entries.

    Parameters
    ----------
    entries : sequence of dict
        The entries to reweight.
    share : float
        How much weight they get between them.

    Returns
    -------
    list of dict
        The entries, with `weight` set.
    """
    if not entries:
        return []
    each = round(share / len(entries), 1)
    return [{**entry, "weight": each} for entry in entries]


def _pick(stream: Any, options: Sequence[str], count: int) -> list[str]:
    """Take some names, without repeating one and without running out.

    Parameters
    ----------
    stream : RandomStream
        The seeded stream.
    options : sequence of str
        The palette.
    count : int
        How many are wanted.

    Returns
    -------
    list of str
        The names. A palette shorter than the count is extended by numbering,
        which is ugly on purpose: a `Coldwater 2` on the map is a prompt to
        rename it.
    """
    remaining = list(options)
    taken: list[str] = []
    for number in range(count):
        if remaining:
            taken.append(remaining.pop(stream.below(len(remaining))))
        else:
            taken.append(
                f"{options[number % len(options)]} {number // len(options) + 1}"
            )
    return taken


def _qualify(pack_id: str, reference: str) -> str:
    """Make a reference mean the same thing in another pack.

    Parameters
    ----------
    pack_id : str
        The pack the reference was written in.
    reference : str
        The reference.

    Returns
    -------
    str
        The qualified form.
    """
    return reference if ":" in reference else f"{pack_id}:{reference}"


def _slug(name: str) -> str:
    """Turn a name into a content id.

    Parameters
    ----------
    name : str
        The name.

    Returns
    -------
    str
        `the-deep-wood`.
    """
    kept = [c.lower() if c.isalnum() else "-" for c in name]
    return "-".join(part for part in "".join(kept).split("-") if part) or "untitled"
