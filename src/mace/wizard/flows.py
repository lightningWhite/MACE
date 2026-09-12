"""The flows themselves: what the wizard actually asks, in what order.

Everything here is data. The CLI renders it, the web client will render it,
and neither one contains a question. Adding a field to the content model means
adding a `Step` here — which is also the moment somebody has to write the
sentence of help that explains it, and that is deliberate.

Two things shape the ordering. Identity first, because an object has to exist
before anything can point at it. Then the fields in the order an author thinks
about them rather than the order the model declares them: what a place *is*
comes before which encounter table it rolls, because one of those is a thought
about the world and the other is a knob.
"""

from __future__ import annotations

from mace.wizard.fields import (
    Bool,
    ConditionBuilder,
    EffectBuilder,
    Fixed,
    MapEditor,
    MultiSelect,
    Number,
    RelativeNumber,
    Repeat,
    Select,
    StatAllocator,
    Text,
    TextList,
)
from mace.wizard.flow import Flow, Step
from mace.wizard.query import Distinct, Query

__all__ = ["FLOWS", "flow_for"]

#: A game's difficulty labels. Author-facing convention rather than engine
#: behaviour, which is why they are a fixed list and not content.
DIFFICULTIES = Fixed.of("gentle", "standard", "hard", "brutal")

#: What an entity can be. Five words the engine knows; not content.
ENTITY_KINDS = Fixed.of(
    ("actor", "actor — a person, a monster, anything that acts"),
    ("item", "item — something to carry, wear, or spend"),
    ("fixture", "fixture — scenery you can interact with"),
    ("container", "container — a chest, a sack, a corpse"),
    ("portal", "portal — a door or a gate between places"),
)

COMBAT_MODES = Fixed.of(
    ("tactical", "tactical — untimed, and loses none of the reading"),
    ("reflex", "reflex — a real timing window"),
    ("auto", "auto — the engine plays both sides"),
)

DISPOSITIONS = Fixed.of("friendly", "neutral", "hostile")

SURVIVAL = Fixed.of(
    ("exposure", "exposure — the weather takes something out of you"),
    ("rest", "rest — you have to stop, and stopping costs time"),
    ("hunger", "hunger"),
    ("thirst", "thirst"),
)

ECONOMIES = Fixed.of(
    ("simple", "simple — a price is an item's value, and shops are scenes"),
    ("market", "market — shelves, scarcity, and trade along the roads"),
)


GAME = Flow(
    id="game",
    noun="game",
    title="Game setup",
    collection=None,
    steps=(
        Step(
            id="game.name",
            title="What is this game called?",
            binds="game.name",
            field=Text(placeholder="A Peasant's Quest"),
            help="The title. It goes on the gallery card and nowhere else.",
        ),
        Step(
            id="game.tagline",
            title="One line that makes somebody want to play it",
            binds="game.tagline",
            field=Text(placeholder="Seven days, one road, no choice.", optional=True),
            help=(
                "Not a summary — a hook. This is the line under the title, and "
                "it is usually the only thing anyone reads before deciding."
            ),
            optional=True,
        ),
        Step(
            id="game.introduction",
            title="Write the introduction",
            binds="game.introduction",
            field=TextList(
                min_items=1,
                placeholder="One morning the king's riders come through the barley…",
            ),
            help=(
                "These lines set the stage. The player presses enter between "
                "each one, so break them where you want a beat."
            ),
        ),
        Step(
            id="game.player.entity",
            title="Who does the player play?",
            binds="game.player.entity",
            field=Select(
                options=Query("entities", where={"playable": True}),
                allow_create="entities",
            ),
            help=(
                "An entity marked `playable`. One person, authored once — "
                "backgrounds are how they turn out differently."
            ),
        ),
        Step(
            id="game.player.startLocation",
            title="Where do they wake up?",
            binds="game.player.startLocation",
            field=Select(options=Query("locations"), allow_create="locations"),
            help="The first place the player sees. Make it somewhere they know.",
        ),
        Step(
            id="game.player.creationPoints",
            title="How many creation points does the player get?",
            binds="game.player.creationPoints",
            field=Number(minimum=0, optional=True),
            help=(
                "Spent at character creation on stats you marked "
                "`customizable`. Zero is a fine answer: not every game wants "
                "the player deciding who they are."
            ),
            optional=True,
        ),
        Step(
            id="game.player.backgrounds",
            title="Which backgrounds are on offer?",
            binds="game.player.backgrounds",
            field=MultiSelect(options=Query("backgrounds"), allow_create="backgrounds"),
            help=(
                "Optional. A background is who the protagonist was before the "
                "story started — different stats, different kit, sometimes a "
                "flag that opens a door later."
            ),
            optional=True,
        ),
        Step(
            id="game.world.minutesPerTick",
            title="How many minutes does one tick take?",
            binds="game.world.minutesPerTick",
            field=Number(minimum=1, optional=True),
            help=(
                "The number you enter is minutes: 30 means a tick is half an "
                "hour, 60 means a tick is an hour. It sets the pace of "
                "everything — travel, weather, hunger, the seven days you "
                "have left — but not how many ticks make a day; the "
                "calendar's own `ticksPerDay` decides that. Thirty minutes "
                "suits a game about a week-long journey; a game about one "
                "night wants less. Blank leaves it at thirty."
            ),
            optional=True,
        ),
        Step(
            id="game.world.calendar",
            title="Which calendar runs the year?",
            binds="game.world.calendar",
            field=Select(options=Query("calendars"), optional=True),
            help="Days, seasons, and parts of the day. `mace.core` has one.",
            optional=True,
        ),
        Step(
            id="game.world.startTick",
            title="What time does the game open at?",
            binds="game.world.startTick",
            field=Number(minimum=0, optional=True),
            help="In ticks from midnight on day one. Mid-morning reads well.",
            optional=True,
        ),
        Step(
            id="game.world.startSeason",
            title="What season is it?",
            binds="game.world.startSeason",
            field=Text(placeholder="autumn", optional=True),
            help="A season your calendar defines.",
            optional=True,
        ),
        Step(
            id="game.world.startRegion",
            title="Which region seeds the weather?",
            binds="game.world.startRegion",
            field=Select(options=Query("regions"), optional=True),
            help="Where the sky starts. Usually the region the player is in.",
            optional=True,
        ),
        Step(
            id="game.rules.vitalPool",
            title="Which pool means life?",
            binds="game.rules.vitalPool",
            field=Text(placeholder="hitpoints", optional=True),
            help=(
                "When it empties, the player is done. Name it whatever your "
                "world calls it — the engine has no opinion, and blank leaves "
                "it at `hitpoints`."
            ),
            optional=True,
        ),
        Step(
            id="game.rules.effortPool",
            title="Which pool does fighting cost?",
            binds="game.rules.effortPool",
            field=Text(placeholder="stamina", optional=True),
            help=(
                "Every move in combat is paid for out of this. Blank leaves "
                "it at `stamina`."
            ),
            optional=True,
        ),
        Step(
            id="game.rules.combatMode",
            title="How is combat played by default?",
            binds="game.rules.combatMode",
            field=Select(options=COMBAT_MODES, optional=True),
            help="The player can override this. Pick what your game is about.",
            optional=True,
        ),
        Step(
            id="game.rules.deathIsPermanent",
            title="Does death end the playthrough?",
            binds="game.rules.deathIsPermanent",
            field=Bool(optional=True),
            help=(
                "No sends the player to a scene instead, which is how a game "
                "about a journey survives one bad night on the road."
            ),
            optional=True,
        ),
        Step(
            id="game.rules.survival",
            title="Which survival systems are on?",
            binds="game.rules.survival",
            field=MultiSelect(options=SURVIVAL),
            help=(
                "Exposure and rest are what give the weather teeth. Hunger and "
                "thirst are off unless your game is about rations."
            ),
            optional=True,
        ),
        Step(
            id="game.rules.economy",
            title="How does money work?",
            binds="game.rules.economy",
            field=Select(options=ECONOMIES, optional=True),
            help=(
                "`simple` is enough for a story game: an item is worth its "
                "value and a shop is a scene you write. `market` runs the "
                "whole thing — a place is cheap because it grows the stuff, "
                "and closing a road makes it dear somewhere else."
            ),
            optional=True,
        ),
        Step(
            id="game.rules.currency",
            title="What is trade paid in?",
            binds="game.rules.currency",
            field=Select(
                options=Query("entities", where={"kind": "item"}),
                allow_create="entities",
                optional=True,
            ),
            help=(
                "Only needed for a `market` economy, which has to settle a "
                "price the engine works out in something the player carries. "
                "Gold, ration chits, whatever your world spends."
            ),
            optional=True,
        ),
        Step(
            id="game.difficulty",
            title="How hard is it, roughly?",
            binds="game.difficulty",
            field=Select(options=DIFFICULTIES, optional=True),
            help="A label for the gallery. It changes nothing in the engine.",
            optional=True,
        ),
        Step(
            id="game.quests",
            title="Which quests start with the game?",
            binds="game.quests",
            field=MultiSelect(options=Query("quests"), allow_create="quests"),
            help=(
                "Quests not listed here have to be started by a scene. A quest "
                "in neither place is one nobody will ever see."
            ),
            optional=True,
        ),
        Step(
            id="game.winConditions",
            title="What does winning mean?",
            binds="game.winConditions",
            field=ConditionBuilder(),
            help=(
                "Checked after every action. A game with no win conditions and "
                "no quests cannot be won, which the validator will tell you."
            ),
        ),
        Step(
            id="game.loseConditions",
            title="What does losing mean?",
            binds="game.loseConditions",
            field=ConditionBuilder(),
            help=(
                "Usually the vital pool running out, and often a deadline as "
                "well. Both can be true at once."
            ),
            optional=True,
        ),
        Step(
            id="game.onWin",
            title="Which scene plays when they win?",
            binds="game.onWin",
            field=Select(options=Query("scenes"), allow_create="scenes", optional=True),
            help="The last thing anybody reads. Worth writing properly.",
            optional=True,
        ),
        Step(
            id="game.onLose",
            title="Which scene plays when they lose?",
            binds="game.onLose",
            field=Select(options=Query("scenes"), allow_create="scenes", optional=True),
            help="",
            optional=True,
        ),
    ),
)


LOCATION = Flow(
    id="location",
    noun="place",
    title="A place",
    collection="locations",
    identity=("location.name",),
    steps=(
        Step(
            id="location.name",
            title="What is this place called?",
            binds="locations[{id}].name",
            field=Text(placeholder="The Old Bridge"),
            help="What the player reads at the top of the screen.",
        ),
        Step(
            id="location.description",
            title="What does it look like?",
            binds="locations[{id}].description",
            field=TextList(
                min_items=1,
                placeholder="A stone span over black water, and moss on everything.",
            ),
            help=(
                "One line is enough. Write more than one and you can make them "
                "conditional later — the bridge at night, the bridge in rain."
            ),
        ),
        Step(
            id="location.region",
            title="Which region is it in?",
            binds="locations[{id}].region",
            field=Select(
                options=Query("regions"), allow_create="regions", optional=True
            ),
            help=(
                "Regions are what the weather happens to. A place with no "
                "region gets the world's default sky."
            ),
            optional=True,
        ),
        Step(
            id="location.submapOf",
            title="Is this actually inside somewhere else?",
            binds="locations[{id}].submapOf",
            field=Select(options=Query("locations"), optional=True),
            help=(
                "A castle's dungeon naming the castle. A place with this set "
                "gets no pin of its own on the world map — it's drawn on its "
                "hub's own small map instead, alongside anything else that "
                "names the same hub."
            ),
            optional=True,
        ),
        Step(
            id="location.indoors",
            title="Is it indoors?",
            binds="locations[{id}].indoors",
            field=Bool(optional=True),
            help="Indoors means the weather cannot reach you. It still exists.",
            optional=True,
        ),
        Step(
            id="location.safe",
            title="Can the player rest here?",
            binds="locations[{id}].safe",
            field=Bool(optional=True),
            help=(
                "A game with nowhere safe is a game where the player can never "
                "recover, which is a decision rather than an oversight."
            ),
            optional=True,
        ),
        Step(
            id="location.entities",
            title="Who and what is here?",
            binds="locations[{id}].entities",
            field=MultiSelect(options=Query("entities"), allow_create="entities"),
            help="Anything that should be standing here when the game begins.",
            optional=True,
        ),
        Step(
            id="location.scenes",
            title="What can the player do here?",
            binds="locations[{id}].scenes",
            field=MultiSelect(options=Query("scenes"), allow_create="scenes"),
            help=(
                "Scenes offered as options on arrival. Anything a person here "
                "carries is offered too, so this is for the place itself."
            ),
            optional=True,
        ),
        Step(
            id="location.onArrive",
            title="Does anything happen the moment they walk in?",
            binds="locations[{id}].onArrive",
            field=Select(options=Query("scenes"), allow_create="scenes", optional=True),
            help="A scene that plays before the player is offered anything.",
            optional=True,
        ),
        Step(
            id="location.encounters",
            title="Which encounter table does this place roll?",
            binds="locations[{id}].encounters",
            field=Select(options=Query("encounterTables"), optional=True),
            help="Most places roll nothing. Roads are where the danger lives.",
            optional=True,
        ),
        Step(
            id="location.exits",
            title="Where can you go from here?",
            binds="locations[{id}].exits",
            field=Repeat(
                of="exit",
                steps=(
                    Step(
                        id="exit.to",
                        title="Where does it lead?",
                        binds="exits.to",
                        field=Select(
                            options=Query("locations"), allow_create="locations"
                        ),
                    ),
                    Step(
                        id="exit.route",
                        title="By which road?",
                        binds="exits.route",
                        field=Select(
                            options=Query("routes"),
                            allow_create="routes",
                            optional=True,
                        ),
                        help=(
                            "Leave it blank and the loader makes a one-tick "
                            "road, which is fine for a door between two rooms "
                            "and wrong for a day's walk."
                        ),
                        optional=True,
                    ),
                    Step(
                        id="exit.label",
                        title="What should the option say?",
                        binds="exits.label",
                        field=Text(placeholder="Take the north road", optional=True),
                        help="Blank gives you `Travel to <place>`.",
                        optional=True,
                    ),
                    Step(
                        id="exit.when",
                        title="Is it ever closed?",
                        binds="exits.when",
                        field=ConditionBuilder(),
                        help="Leave it empty and the way is always open.",
                        optional=True,
                    ),
                ),
            ),
            help=(
                "Exits are how the map is drawn. A place with none is a place "
                "the player can walk into and never leave."
            ),
            optional=True,
        ),
        Step(
            id="location.mapPosition",
            title="Where does it sit on the map?",
            binds="locations[{id}].mapPosition",
            field=MapEditor(optional=True),
            help=(
                "Only for the map view. Leave it blank and the layout works "
                "itself out from the routes."
            ),
            optional=True,
        ),
    ),
)


ENTITY = Flow(
    id="entity",
    noun="entity",
    title="A person, a creature, or a thing",
    collection="entities",
    identity=("entity.name",),
    steps=(
        Step(
            id="entity.name",
            title="What is it called?",
            binds="entities[{id}].name",
            field=Text(placeholder="Gorm"),
            help="What the player sees. Proper names are fine.",
        ),
        Step(
            id="entity.kind",
            title="What sort of thing is it?",
            binds="entities[{id}].kind",
            field=Select(options=ENTITY_KINDS),
            help=(
                "One model covers all of them; `kind` only says which optional "
                "blocks apply. It does not switch on special engine behaviour."
            ),
        ),
        Step(
            id="entity.description",
            title="What does the player notice about it?",
            binds="entities[{id}].description",
            field=TextList(
                placeholder="Moss in its hair, and the patient look of "
                "something that gets paid eventually.",
            ),
            help="One good line beats three ordinary ones.",
            optional=True,
        ),
        Step(
            id="entity.extends",
            title="Is it a version of something that already exists?",
            binds="entities[{id}].extends",
            field=Select(options=Query("entities"), optional=True),
            help=(
                "Inheriting from a library's `soldier` takes the stats, the "
                "combat profile, and the gear, and leaves you writing only "
                "what makes this one *this* one."
            ),
            optional=True,
        ),
        Step(
            id="entity.tags",
            title="How would you group it?",
            binds="entities[{id}].tags",
            field=MultiSelect(options=Distinct("entities", "tags"), free_text=True),
            help=(
                "Free labels — `human`, `undead`, `peasant`. Encounter tables "
                "and weather responses match on these."
            ),
            optional=True,
        ),
        Step(
            id="entity.stats",
            title="What is it made of?",
            binds="entities[{id}].stats",
            field=StatAllocator(),
            help=(
                "Pools it can lose (hitpoints, stamina) and abilities it "
                "brings (strength, speed). Mark a stat `customizable` if the "
                "player may spend creation points on it."
            ),
            optional=True,
        ),
        Step(
            id="entity.disposition",
            title="How does it feel about the player?",
            binds="entities[{id}].disposition",
            field=Select(options=DISPOSITIONS, optional=True),
            help="Where it starts. Scenes can change it.",
            optional=True,
        ),
        Step(
            id="entity.combat.profile",
            title="How does it fight?",
            binds="entities[{id}].combat.profile",
            field=Select(options=Query("combatProfiles"), optional=True),
            help=(
                "The profile is the pattern the player learns to read. Two "
                "creatures sharing one are two creatures that fight the same, "
                "which is usually what you want."
            ),
            optional=True,
        ),
        Step(
            id="entity.combat.moves",
            title="Does it know any extra moves, beyond its profile?",
            binds="entities[{id}].combat.moves",
            field=MultiSelect(options=Query("moves"), allow_create="moves"),
            help=(
                "On top of whatever its combat profile already grants — a "
                "veteran with the same style as every other guard, but one "
                "move they alone have picked up."
            ),
            optional=True,
        ),
        Step(
            id="entity.item.weight",
            title="How much does it weigh?",
            binds="entities[{id}].item.weight",
            field=Number(minimum=0, integer=False, optional=True),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.stackable",
            title="Do copies of it stack into one inventory entry?",
            binds="entities[{id}].item.stackable",
            field=Bool(optional=True),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.equipSlot",
            title="What slot does it go in, if it can be worn or wielded?",
            binds="entities[{id}].item.equipSlot",
            field=Text(placeholder="mainHand", optional=True),
            help="Free-form — a name your own pack's equip slots agree on.",
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.damage.min",
            title="Minimum damage, if it's a weapon?",
            binds="entities[{id}].item.damage.min",
            field=RelativeNumber(minimum=0, optional=True),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.damage.max",
            title="Maximum damage, if it's a weapon?",
            binds="entities[{id}].item.damage.max",
            field=RelativeNumber(minimum=0, optional=True),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.damage.type",
            title="What kind of damage does it deal?",
            binds="entities[{id}].item.damage.type",
            field=Text(placeholder="slash", optional=True),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.armor",
            title="How much damage does it stop, if it's worn?",
            binds="entities[{id}].item.armor",
            field=Number(minimum=0, integer=False, optional=True),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.moves",
            title="Does holding it grant any moves?",
            binds="entities[{id}].item.moves",
            field=MultiSelect(options=Query("moves"), allow_create="moves"),
            help=(
                "A weapon is how a fighter gets a `thrust` to answer with; a "
                "shield is how they get a `block`."
            ),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.use.effects",
            title="What happens when it's used from the inventory?",
            binds="entities[{id}].item.use.effects",
            field=EffectBuilder(),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.use.consumed",
            title="Is it used up?",
            binds="entities[{id}].item.use.consumed",
            field=Bool(optional=True),
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.item.baseValue",
            title="What's it worth?",
            binds="entities[{id}].item.baseValue",
            field=Number(minimum=0, integer=False, optional=True),
            help="The price anchor a `simple` or `market` economy prices around.",
            optional=True,
            visible_when=("entity.kind", "item"),
        ),
        Step(
            id="entity.inventory",
            title="What is it carrying?",
            binds="entities[{id}].inventory",
            field=Repeat(
                of="stack",
                steps=(
                    Step(
                        id="stack.item",
                        title="Which item?",
                        binds="inventory.item",
                        field=Select(
                            options=Query("entities", where={"kind": "item"}),
                            allow_create="entities",
                        ),
                    ),
                    Step(
                        id="stack.qty",
                        title="How many?",
                        binds="inventory.qty",
                        field=Number(minimum=1, optional=True),
                        optional=True,
                    ),
                ),
            ),
            optional=True,
        ),
        Step(
            id="entity.scenes",
            title="What can the player do with it?",
            binds="entities[{id}].scenes",
            field=MultiSelect(options=Query("scenes"), allow_create="scenes"),
            help=(
                "Scenes offered wherever this thing is. A character with none "
                "is scenery — which the validator will mention."
            ),
            optional=True,
        ),
        Step(
            id="entity.playable",
            title="Can the player be this?",
            binds="entities[{id}].playable",
            field=Bool(optional=True),
            help="Only the protagonist needs this.",
            optional=True,
        ),
    ),
)


ROUTE = Flow(
    id="route",
    noun="road",
    title="A road between two places",
    collection="routes",
    identity=("route.from", "route.to", "route.ticks"),
    steps=(
        Step(
            id="route.from",
            title="Where does it start?",
            binds="routes[{id}].from",
            field=Select(options=Query("locations"), allow_create="locations"),
        ),
        Step(
            id="route.to",
            title="Where does it end?",
            binds="routes[{id}].to",
            field=Select(options=Query("locations"), allow_create="locations"),
        ),
        Step(
            id="route.ticks",
            title="How long does it take?",
            binds="routes[{id}].ticks",
            field=Number(minimum=1),
            help=(
                "In ticks, in fair weather. This is the number that makes a "
                "detour a decision, so it is worth being deliberate about."
            ),
        ),
        Step(
            id="route.name",
            title="What is the road called?",
            binds="routes[{id}].name",
            field=Text(placeholder="The North Road", optional=True),
            optional=True,
        ),
        Step(
            id="route.terrain",
            title="What is it made of?",
            binds="routes[{id}].terrain",
            field=Select(options=Query("terrains"), optional=True),
            help=(
                "Terrain is how badly the surface takes the weather. Rain on a "
                "paved highway is an inconvenience; rain on a forest track is "
                "mud to the ankles."
            ),
            optional=True,
        ),
        Step(
            id="route.dangerLevel",
            title="How dangerous is it, from 0 to 10?",
            binds="routes[{id}].dangerLevel",
            field=Number(minimum=0, maximum=10, optional=True),
            help=(
                "Used by the encounter-table suggestion, and by nothing else. "
                "It is a note to yourself that the tool can read."
            ),
            optional=True,
        ),
        Step(
            id="route.encounters",
            title="What might happen on the way?",
            binds="routes[{id}].encounters",
            field=Select(options=Query("encounterTables"), optional=True),
            help=(
                "A road with no table is a road where nothing ever happens, "
                "and journeys along it will feel empty."
            ),
            optional=True,
        ),
        Step(
            id="route.legDescriptions",
            title="What does the journey look like?",
            binds="routes[{id}].legDescriptions",
            field=TextList(
                placeholder="The barley gives out and the wood starts.",
            ),
            help=(
                "One line per leg of the journey, in order. This is where a "
                "two-day walk stops being a loading screen."
            ),
            optional=True,
        ),
        Step(
            id="route.bidirectional",
            title="Does it work both ways?",
            binds="routes[{id}].bidirectional",
            field=Bool(optional=True),
            help="Almost always yes. A cliff you can only climb down is no.",
            optional=True,
        ),
    ),
)


REGION = Flow(
    id="region",
    noun="region",
    title="A stretch of the map that shares its weather",
    collection="regions",
    identity=("region.name",),
    steps=(
        Step(
            id="region.name",
            title="What is this region called?",
            binds="regions[{id}].name",
            field=Text(placeholder="The Fenmoor Lowlands"),
            help="What a front is named after when it rolls in from here.",
        ),
        Step(
            id="region.description",
            title="How does it read from a distance?",
            binds="regions[{id}].description",
            field=TextList(placeholder="A grey smear of cloud over the hills."),
            help="Named at a distance — a front seen from the next valley over.",
            optional=True,
        ),
        Step(
            id="region.climate",
            title="Which climate governs it?",
            binds="regions[{id}].climate",
            field=Select(
                options=Query("climates"), allow_create="climates", optional=True
            ),
            help=(
                "Without one, this region has no weather — the right answer "
                "for an undercity or a station interior. Pick one a "
                "dependency already brought in, or create a new one."
            ),
            optional=True,
        ),
        Step(
            id="region.neighbors",
            title="Which regions border it?",
            binds="regions[{id}].neighbors",
            field=MultiSelect(options=Query("regions"), allow_create="regions"),
            help=(
                "The map weather fronts walk across. A front that crosses a "
                "range one way and not the other is allowed — list the "
                "border only from the side it is felt."
            ),
            optional=True,
        ),
        Step(
            id="region.elevation",
            title="How high above the map's baseline?",
            binds="regions[{id}].elevation",
            field=Number(integer=False, optional=True),
            help="Colder with altitude, which turns the same rain into snow.",
            optional=True,
        ),
        Step(
            id="region.encounters",
            title="Does anything happen just from being here?",
            binds="regions[{id}].encounters",
            field=Select(options=Query("encounterTables"), optional=True),
            help=(
                "Rolled anywhere in the region, on top of the route's or the "
                "location's. Region-wide flavor: you hear wolves."
            ),
            optional=True,
        ),
    ),
)


SCENE = Flow(
    id="scene",
    noun="scene",
    title="Something that happens",
    collection="scenes",
    identity=("scene.say",),
    steps=(
        Step(
            id="scene.prompt",
            title="What does the option say?",
            binds="scenes[{id}].prompt",
            field=Text(placeholder="Speak to the troll", optional=True),
            help=(
                "How this scene is offered in a menu. A scene with no prompt "
                "is one that another scene or choice jumps straight to, "
                "rather than one a player picks from a list."
            ),
            optional=True,
        ),
        Step(
            id="scene.when",
            title="When is it available?",
            binds="scenes[{id}].when",
            field=ConditionBuilder(),
            help="Empty means always.",
            optional=True,
        ),
        Step(
            id="scene.say",
            title="What does the player read?",
            binds="scenes[{id}].say",
            field=TextList(
                min_items=1,
                placeholder='"Toll," it says. "Ten gold, or swim."',
            ),
            help="One line per beat. The player presses enter between them.",
        ),
        Step(
            id="scene.effects",
            title="What does it change?",
            binds="scenes[{id}].effects",
            field=EffectBuilder(),
            help=(
                "Applied in order, after the lines are said. This is where a "
                "scene stops being text and starts being a decision."
            ),
            optional=True,
        ),
        Step(
            id="scene.choices",
            title="What can they do about it?",
            binds="scenes[{id}].choices",
            field=Repeat(
                of="choice",
                steps=(
                    Step(
                        id="choice.prompt",
                        title="What does the option say?",
                        binds="choices.prompt",
                        field=Text(placeholder="Pay the toll (10 gold)"),
                    ),
                    Step(
                        id="choice.when",
                        title="When can they take it?",
                        binds="choices.when",
                        field=ConditionBuilder(),
                        help="Empty means always.",
                        optional=True,
                    ),
                    Step(
                        id="choice.showWhenUnavailable",
                        title="Show it greyed out when they cannot?",
                        binds="choices.showWhenUnavailable",
                        field=Bool(optional=True),
                        help=(
                            "Showing what you are missing is usually better "
                            "than hiding it — a player who never sees the "
                            "option never learns the gold was the point."
                        ),
                        optional=True,
                    ),
                    Step(
                        id="choice.unavailableHint",
                        title="What should it say when they cannot?",
                        binds="choices.unavailableHint",
                        field=Text(
                            placeholder="You don't have ten gold.", optional=True
                        ),
                        optional=True,
                    ),
                    Step(
                        id="choice.goto",
                        title="Which scene does it lead to?",
                        binds="choices.goto",
                        field=Select(
                            options=Query("scenes"),
                            allow_create="scenes",
                            optional=True,
                        ),
                        optional=True,
                    ),
                    Step(
                        id="choice.effects",
                        title="Or does it just do something?",
                        binds="choices.effects",
                        field=EffectBuilder(),
                        help=(
                            "A choice needs to lead somewhere or change "
                            "something: pick a scene above, add an effect "
                            "here, or both."
                        ),
                        optional=True,
                    ),
                ),
            ),
            optional=True,
        ),
        Step(
            id="scene.goto",
            title="Or does it lead straight on?",
            binds="scenes[{id}].goto",
            field=Select(options=Query("scenes"), allow_create="scenes", optional=True),
            help=(
                "A scene either jumps onward or offers a choice. Not both — "
                "they are two answers to the same question."
            ),
            optional=True,
        ),
        Step(
            id="scene.once",
            title="Does it only happen once?",
            binds="scenes[{id}].once",
            field=Bool(optional=True),
            optional=True,
        ),
        Step(
            id="scene.else",
            title="What happens instead, once it has?",
            binds="scenes[{id}].else",
            field=Select(options=Query("scenes"), allow_create="scenes", optional=True),
            help=(
                "The fallback when this scene's own conditions fail. This is "
                "what stops a talked-out character going silent."
            ),
            optional=True,
        ),
    ),
)


QUEST = Flow(
    id="quest",
    noun="quest",
    title="Something to be doing",
    collection="quests",
    identity=("quest.name",),
    steps=(
        Step(
            id="quest.name",
            title="What is the quest called?",
            binds="quests[{id}].name",
            field=Text(placeholder="The King's Summons"),
        ),
        Step(
            id="quest.summary",
            title="What is it, in one line?",
            binds="quests[{id}].summary",
            field=Text(
                placeholder="Reach Hagan's Castle before the seventh day.",
                optional=True,
            ),
            optional=True,
        ),
        Step(
            id="quest.stages",
            title="What are the stages?",
            binds="quests[{id}].stages",
            field=Repeat(
                of="stage",
                steps=(
                    Step(
                        id="stage.id",
                        title="A short name for this stage",
                        binds="stages.id",
                        field=Text(placeholder="on-the-road"),
                        help="Lower case, hyphens. Conditions refer to it.",
                    ),
                    Step(
                        id="stage.journal",
                        title="What does the journal say while it is current?",
                        binds="stages.journal",
                        field=Text(
                            placeholder="Six days left. The bridge is next.",
                        ),
                        help=(
                            "Write it in the player's voice. This is the only "
                            "place a stuck player looks."
                        ),
                    ),
                    Step(
                        id="stage.complete",
                        title="What finishes it?",
                        binds="stages.complete",
                        field=ConditionBuilder(),
                    ),
                    Step(
                        id="stage.fail",
                        title="What fails the whole quest?",
                        binds="stages.fail",
                        field=ConditionBuilder(),
                        optional=True,
                    ),
                    Step(
                        id="stage.deadlineTicks",
                        title="Is there a deadline?",
                        binds="stages.deadlineTicks",
                        field=Number(minimum=1, optional=True),
                        help="In ticks from when the stage began.",
                        optional=True,
                    ),
                    Step(
                        id="stage.onEnter",
                        title="Does anything happen when it starts?",
                        binds="stages.onEnter",
                        field=EffectBuilder(),
                        optional=True,
                    ),
                ),
            ),
            help=(
                "Stages are what turn a win condition into a plot. Each one "
                "is a thing to be doing now and a line in the journal saying "
                "what."
            ),
        ),
        Step(
            id="quest.onComplete",
            title="What happens when it is done?",
            binds="quests[{id}].onComplete",
            field=EffectBuilder(),
            optional=True,
        ),
        Step(
            id="quest.onFail",
            title="What happens when it is failed?",
            binds="quests[{id}].onFail",
            field=EffectBuilder(),
            optional=True,
        ),
    ),
)


MOVE_KINDS = Fixed.of(
    ("attack", "attack — telegraphed, then the player answers"),
    ("defense", "defense — one of the answers a player can pick"),
)

MOVE = Flow(
    id="move",
    noun="move",
    title="A move a fighter can make",
    collection="moves",
    identity=("move.type",),
    steps=(
        Step(
            id="move.name",
            title="What should we call it?",
            binds="moves[{id}].name",
            field=Text(placeholder="Overhead smash", optional=True),
            help="Falls back to its id if you leave this blank.",
            optional=True,
        ),
        Step(
            id="move.kind",
            title="Attack or defense?",
            binds="moves[{id}].kind",
            field=Select(options=MOVE_KINDS),
        ),
        Step(
            id="move.type",
            title="What kind of move is it?",
            binds="moves[{id}].type",
            field=Text(placeholder="overhead"),
            help=(
                "Free-form — this is the vocabulary a defense's `counters` "
                "names, not a fixed engine list."
            ),
        ),
        Step(
            id="move.tell",
            title="How is it telegraphed?",
            binds="moves[{id}].tell",
            field=TextList(
                placeholder="The troll hauls the club up over its head.",
            ),
            help="Shown plainly the first few times a player faces this move.",
            optional=True,
            visible_when=("move.kind", "attack"),
        ),
        Step(
            id="move.vagueTell",
            title="What if the tell isn't read clearly yet?",
            binds="moves[{id}].vagueTell",
            field=TextList(placeholder="The troll's shoulders bunch."),
            help=(
                "Shown instead of the plain tell under low familiarity — "
                "vague on purpose, so learning the move means something."
            ),
            optional=True,
            visible_when=("move.kind", "attack"),
        ),
        Step(
            id="move.windupMs",
            title="How long is the windup, in milliseconds?",
            binds="moves[{id}].windupMs",
            field=Number(minimum=1),
            help="1000 is an ordinary swing; slower moves telegraph longer.",
        ),
        Step(
            id="move.counters",
            title="What beats it?",
            binds="moves[{id}].counters",
            field=MultiSelect(options=Distinct("moves", "type"), free_text=True),
            help="The defense `type`s that answer this move correctly.",
            optional=True,
        ),
        Step(
            id="move.damage.min",
            title="Minimum damage?",
            binds="moves[{id}].damage.min",
            field=RelativeNumber(minimum=0, optional=True),
            optional=True,
        ),
        Step(
            id="move.damage.max",
            title="Maximum damage?",
            binds="moves[{id}].damage.max",
            field=RelativeNumber(minimum=0, optional=True),
            optional=True,
        ),
        Step(
            id="move.damage.type",
            title="What kind of damage?",
            binds="moves[{id}].damage.type",
            field=Text(placeholder="bludgeon", optional=True),
            optional=True,
        ),
        Step(
            id="move.cost",
            title="What does it cost in effort?",
            binds="moves[{id}].cost",
            field=Number(minimum=0, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="move.mitigation",
            title="How much does a clean read stop?",
            binds="moves[{id}].mitigation",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help="0 to 1 — a well-read defense stops this share of the damage.",
            optional=True,
            visible_when=("move.kind", "defense"),
        ),
        Step(
            id="move.feint",
            title="Is this the pack's feint — a windup that means nothing?",
            binds="moves[{id}].feint",
            field=Bool(optional=True),
            optional=True,
            visible_when=("move.kind", "defense"),
        ),
        Step(
            id="move.effects",
            title="What happens when it lands?",
            binds="moves[{id}].effects",
            field=EffectBuilder(),
            optional=True,
        ),
        Step(
            id="move.tags",
            title="How would you group it?",
            binds="moves[{id}].tags",
            field=MultiSelect(options=Distinct("moves", "tags"), free_text=True),
            optional=True,
        ),
    ),
)

COMBAT_PROFILE = Flow(
    id="combatProfile",
    noun="combat profile",
    title="How something fights",
    collection="combatProfiles",
    identity=("combatProfile.name",),
    steps=(
        Step(
            id="combatProfile.name",
            title="What should we call this way of fighting?",
            binds="combatProfiles[{id}].name",
            field=Text(placeholder="Bridge troll", optional=True),
            help="Falls back to its id if you leave this blank.",
            optional=True,
        ),
        Step(
            id="combatProfile.moves",
            title="Which moves can it make?",
            binds="combatProfiles[{id}].moves",
            field=MultiSelect(options=Query("moves"), allow_create="moves"),
            help="Every attack and defense this fighter has an answer with.",
            optional=True,
        ),
        Step(
            id="combatProfile.patterns",
            title="Does it favor any sequences?",
            binds="combatProfiles[{id}].patterns",
            field=Repeat(
                of="pattern",
                steps=(
                    Step(
                        id="pattern.sequence",
                        title="Which moves, in order?",
                        binds="patterns.sequence",
                        field=MultiSelect(options=Query("moves")),
                    ),
                    Step(
                        id="pattern.weight",
                        title="How much more likely than the others?",
                        binds="patterns.weight",
                        field=Number(minimum=0, integer=False, optional=True),
                        optional=True,
                    ),
                    Step(
                        id="pattern.when",
                        title="Only under some condition?",
                        binds="patterns.when",
                        field=ConditionBuilder(),
                        optional=True,
                    ),
                ),
            ),
            help=(
                "Left empty, it picks a legal move at random each turn. A "
                "pattern is a sequence it favors — weighted against the "
                "others, or only under some condition."
            ),
            optional=True,
        ),
        Step(
            id="combatProfile.aggression",
            title="How readily does it press a bad attack?",
            binds="combatProfiles[{id}].aggression",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="combatProfile.feintChance",
            title="How often does a windup mean nothing?",
            binds="combatProfiles[{id}].feintChance",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help="Needs at least one move marked as the feint to do anything.",
            optional=True,
        ),
        Step(
            id="combatProfile.tellClarity",
            title="How legible is its telegraph?",
            binds="combatProfiles[{id}].tellClarity",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="combatProfile.fleeThreshold",
            title="At what share of its health does it flee?",
            binds="combatProfiles[{id}].fleeThreshold",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="combatProfile.tags",
            title="How would you group it?",
            binds="combatProfiles[{id}].tags",
            field=MultiSelect(
                options=Distinct("combatProfiles", "tags"), free_text=True
            ),
            optional=True,
        ),
    ),
)


WEATHER_CONDITION = Flow(
    id="weatherCondition",
    noun="weather condition",
    title="One state of the sky",
    collection="weatherConditions",
    identity=("weatherCondition.name",),
    steps=(
        Step(
            id="weatherCondition.name",
            title="What should we call it?",
            binds="weatherConditions[{id}].name",
            field=Text(placeholder="drizzle", optional=True),
            help="Falls back to its id if you leave this blank.",
            optional=True,
        ),
        Step(
            id="weatherCondition.description",
            title="What does it look like when it starts?",
            binds="weatherConditions[{id}].description",
            field=TextList(placeholder="A thin rain starts."),
            help="One line is enough. Write more and you can make them "
            "conditional later — the same rain, but read differently at night.",
            optional=True,
        ),
        Step(
            id="weatherCondition.intensityMin",
            title="Weakest it ever gets?",
            binds="weatherConditions[{id}].intensityRange.min",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help="0 to 1. Scales `modify`, and how hard the front-end phrases it.",
            optional=True,
        ),
        Step(
            id="weatherCondition.intensityMax",
            title="Strongest it ever gets?",
            binds="weatherConditions[{id}].intensityRange.max",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="weatherCondition.visibility",
            title="How much light does it let through?",
            binds="weatherConditions[{id}].visibility",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help="0 to 1, multiplied into the day part's own light.",
            optional=True,
        ),
        Step(
            id="weatherCondition.travelMultiplier",
            title="How much does it slow the road?",
            binds="weatherConditions[{id}].travelMultiplier",
            field=Number(minimum=0, integer=False, optional=True),
            help="1 is no change. A storm might be 1.8 — a three-tick road "
            "becomes a five-tick slog.",
            optional=True,
        ),
        Step(
            id="weatherCondition.blocksTravel",
            title="Does it close the roads outright?",
            binds="weatherConditions[{id}].blocksTravel",
            field=Bool(optional=True),
            optional=True,
        ),
        Step(
            id="weatherCondition.modify",
            title="Does it change anyone caught out in it?",
            binds="weatherConditions[{id}].modify",
            field=Repeat(
                of="adjustment",
                steps=(
                    Step(
                        id="adjustment.stat",
                        title="Which stat?",
                        binds="adjustment.stat",
                        field=Text(placeholder="stealth"),
                    ),
                    Step(
                        id="adjustment.add",
                        title="Flat adjustment?",
                        binds="adjustment.add",
                        field=Number(integer=False, optional=True),
                        optional=True,
                    ),
                    Step(
                        id="adjustment.mult",
                        title="Multiplier, applied after the flat adjustment?",
                        binds="adjustment.mult",
                        field=Number(integer=False, optional=True),
                        optional=True,
                    ),
                ),
            ),
            help="Held for as long as this condition does. Needs at least an "
            "`add` or a `mult`.",
            optional=True,
        ),
        Step(
            id="weatherCondition.tags",
            title="How would you group it?",
            binds="weatherConditions[{id}].tags",
            field=MultiSelect(
                options=Distinct("weatherConditions", "tags"), free_text=True
            ),
            help="`wet`, `cold`, `dark`, `windy`, `severe` — what entities "
            "and encounter tables match on.",
            optional=True,
        ),
        Step(
            id="weatherCondition.freezesTo",
            title="What does it become below freezing?",
            binds="weatherConditions[{id}].freezesTo",
            field=Select(
                options=Query("weatherConditions"),
                allow_create="weatherConditions",
                optional=True,
            ),
            help="The same wet draw is rain above zero and this below it.",
            optional=True,
        ),
    ),
)


WEATHER_FRONT = Flow(
    id="weatherFront",
    noun="weather front",
    title="A weather system that crosses the map",
    collection="weatherFronts",
    identity=("weatherFront.name",),
    steps=(
        Step(
            id="weatherFront.name",
            title="What should we call it?",
            binds="weatherFronts[{id}].name",
            field=Text(placeholder="a westerly", optional=True),
            help="A phrase, not a noun — it's read inside a sentence, `a "
            "storm out of the west`. Falls back to its id.",
            optional=True,
        ),
        Step(
            id="weatherFront.weight",
            title="How likely is this kind, relative to the others?",
            binds="weatherFronts[{id}].weight",
            field=Number(minimum=0, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="weatherFront.when",
            title="Only under some condition?",
            binds="weatherFronts[{id}].when",
            field=ConditionBuilder(),
            optional=True,
        ),
        Step(
            id="weatherFront.seasons",
            title="Which seasons can it form in?",
            binds="weatherFronts[{id}].seasons",
            field=MultiSelect(free_text=True),
            help="A season your calendar defines. Leave blank for any.",
            optional=True,
        ),
        Step(
            id="weatherFront.intensityMin",
            title="Weakest a new one ever forms?",
            binds="weatherFronts[{id}].intensityRange.min",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="weatherFront.intensityMax",
            title="Strongest a new one ever forms?",
            binds="weatherFronts[{id}].intensityRange.max",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="weatherFront.speedTicks",
            title="How many ticks in each region before it hops onward?",
            binds="weatherFronts[{id}].speedTicks",
            field=Number(minimum=1, optional=True),
            optional=True,
        ),
        Step(
            id="weatherFront.lifespanTicks",
            title="How long does it live?",
            binds="weatherFronts[{id}].lifespanTicks",
            field=Number(minimum=1, optional=True),
            optional=True,
        ),
        Step(
            id="weatherFront.hopsMin",
            title="Fewest regions its heading crosses?",
            binds="weatherFronts[{id}].hops.min",
            field=Number(minimum=1, optional=True),
            optional=True,
        ),
        Step(
            id="weatherFront.hopsMax",
            title="Most regions its heading crosses?",
            binds="weatherFronts[{id}].hops.max",
            field=Number(minimum=1, optional=True),
            optional=True,
        ),
        Step(
            id="weatherFront.biases",
            title="Which conditions does it favor?",
            binds="weatherFronts[{id}].biases",
            field=Repeat(
                of="bias",
                steps=(
                    Step(
                        id="bias.condition",
                        title="Which condition?",
                        binds="bias.condition",
                        field=Select(
                            options=Query("weatherConditions"),
                            allow_create="weatherConditions",
                        ),
                    ),
                    Step(
                        id="bias.weight",
                        title="Multiplier — above 1 makes it likelier, below "
                        "1 rarer?",
                        binds="bias.weight",
                        field=Number(minimum=0, integer=False),
                    ),
                ),
            ),
            help="On top of the region's own transition weights. Scales "
            "with the front's own intensity as it ages.",
            optional=True,
        ),
        Step(
            id="weatherFront.aheadBias",
            title="How much warning does the region ahead get?",
            binds="weatherFronts[{id}].aheadBias",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help="0 to 1. 0 means it arrives without warning.",
            optional=True,
        ),
        Step(
            id="weatherFront.omen",
            title="What does the player see when it's one region away?",
            binds="weatherFronts[{id}].omen",
            field=TextList(placeholder="The wind has come round to the west."),
            help="Ordinary narration, never a system message.",
            optional=True,
        ),
    ),
)


TERRAIN = Flow(
    id="terrain",
    noun="terrain",
    title="A road surface, and what weather does to it",
    collection="terrains",
    identity=("terrain.name",),
    steps=(
        Step(
            id="terrain.name",
            title="What should we call it?",
            binds="terrains[{id}].name",
            field=Text(placeholder="Forest track", optional=True),
            help="Falls back to its id if you leave this blank.",
            optional=True,
        ),
        Step(
            id="terrain.travelMultiplier",
            title="How slow is it in fair weather?",
            binds="terrains[{id}].travelMultiplier",
            field=Number(minimum=0, integer=False, optional=True),
            help="1 is an ordinary road. A mountain path is slow before "
            "anything falls on it.",
            optional=True,
        ),
        Step(
            id="terrain.inWeather",
            title="How much worse does weather make it?",
            binds="terrains[{id}].inWeather",
            field=Repeat(
                of="condition",
                steps=(
                    Step(
                        id="inWeather.tag",
                        title="Which weather tag?",
                        binds="inWeather.tag",
                        field=Text(placeholder="wet"),
                    ),
                    Step(
                        id="inWeather.multiplier",
                        title="Extra multiplier, on top of the weather's own?",
                        binds="inWeather.multiplier",
                        field=Number(minimum=0, integer=False),
                    ),
                ),
            ),
            help="Only the worst matching tag applies, not the product — a "
            "wet, cold, windy night should be bad, not impossible.",
            optional=True,
        ),
        Step(
            id="terrain.tags",
            title="How would you group it?",
            binds="terrains[{id}].tags",
            field=MultiSelect(options=Distinct("terrains", "tags"), free_text=True),
            optional=True,
        ),
    ),
)


TEMPERATURE_UNITS = Fixed.of("celsius", "fahrenheit")


CLIMATE = Flow(
    id="climate",
    noun="climate",
    title="How weather behaves somewhere",
    collection="climates",
    identity=("climate.name",),
    steps=(
        Step(
            id="climate.name",
            title="What should we call it?",
            binds="climates[{id}].name",
            field=Text(placeholder="Temperate Lowlands", optional=True),
            help="Falls back to its id if you leave this blank.",
            optional=True,
        ),
        Step(
            id="climate.stepTicks",
            title="How many ticks between chain steps?",
            binds="climates[{id}].stepTicks",
            field=Number(minimum=1, optional=True),
            help="One reconsiders the sky every tick, which is twitchy at "
            "thirty minutes a tick. Two is an hour, and reads much better.",
            optional=True,
        ),
        Step(
            id="climate.frontFrequency",
            title="How often does a front form, per tick, across the whole map?",
            binds="climates[{id}].frontFrequency",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help="Small on purpose — 0.02 to 0.04 keeps one or two alive at "
            "a time, however many regions the map has.",
            optional=True,
        ),
        Step(
            id="climate.freezingPoint",
            title="Below what temperature does weather freeze?",
            binds="climates[{id}].freezingPoint",
            field=Number(integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="climate.lapseRate",
            title="How many degrees are lost per hundred units of elevation?",
            binds="climates[{id}].lapseRate",
            field=Number(integer=False, optional=True),
            optional=True,
        ),
        Step(
            id="climate.temperatureUnit",
            title="What scale are the temperatures written in?",
            binds="climates[{id}].temperatureUnit",
            field=Select(options=TEMPERATURE_UNITS, optional=True),
            optional=True,
        ),
        Step(
            id="climate.fronts",
            title="What kinds of front can form here?",
            binds="climates[{id}].fronts",
            field=MultiSelect(
                options=Query("weatherFronts"), allow_create="weatherFronts"
            ),
            optional=True,
        ),
        Step(
            id="climate.seasons",
            title="What is each season like?",
            binds="climates[{id}].seasons",
            field=Repeat(
                of="season",
                steps=(
                    Step(
                        id="season.id",
                        title="Which season?",
                        binds="season.id",
                        field=Text(placeholder="autumn"),
                        help="A season your calendar defines.",
                    ),
                    Step(
                        id="season.temperature.min",
                        title="Coldest a day gets?",
                        binds="season.temperature.min",
                        field=Number(integer=False, optional=True),
                        optional=True,
                    ),
                    Step(
                        id="season.temperature.max",
                        title="Warmest a day gets?",
                        binds="season.temperature.max",
                        field=Number(integer=False, optional=True),
                        optional=True,
                    ),
                ),
            ),
            help="A season the calendar has and the climate does not falls "
            "back to the transition matrix alone. Set what each season "
            "favors below, once its seasons are listed here.",
            optional=True,
        ),
        Step(
            id="climate.seasonWeights",
            title="Which conditions does each season favor?",
            binds="climates[{id}].seasonWeights",
            field=Repeat(
                of="weight",
                steps=(
                    Step(
                        id="seasonWeight.season",
                        title="Which season?",
                        binds="seasonWeight.season",
                        field=Text(placeholder="autumn"),
                    ),
                    Step(
                        id="seasonWeight.condition",
                        title="Which condition?",
                        binds="seasonWeight.condition",
                        field=Select(
                            options=Query("weatherConditions"),
                            allow_create="weatherConditions",
                        ),
                    ),
                    Step(
                        id="seasonWeight.weight",
                        title="Relative preference?",
                        binds="seasonWeight.weight",
                        field=Number(minimum=0, integer=False),
                    ),
                ),
            ),
            help="A condition weighted 0 cannot happen that season, however "
            "the chain gets there. One row here adds or replaces a single "
            "season's preference for a single condition — existing rows for "
            "seasons and conditions this does not name are untouched.",
            optional=True,
        ),
        Step(
            id="climate.transitions",
            title="How does the sky actually move?",
            binds="climates[{id}].transitions",
            field=Repeat(
                of="transition",
                steps=(
                    Step(
                        id="transition.source",
                        title="From which condition?",
                        binds="transition.source",
                        field=Select(
                            options=Query("weatherConditions"),
                            allow_create="weatherConditions",
                        ),
                    ),
                    Step(
                        id="transition.target",
                        title="To which condition?",
                        binds="transition.target",
                        field=Select(
                            options=Query("weatherConditions"),
                            allow_create="weatherConditions",
                        ),
                    ),
                    Step(
                        id="transition.weight",
                        title="Relative weight, among this source's other " "targets?",
                        binds="transition.weight",
                        field=Number(minimum=0, integer=False),
                    ),
                ),
            ),
            help="A condition with no row here holds until something else "
            "moves it. Clear does not become a blizzard — it becomes "
            "overcast, then drizzle, then rain.",
            optional=True,
        ),
        Step(
            id="climate.sequences",
            title="Does anything ever run as a scripted story instead?",
            binds="climates[{id}].sequences",
            field=Repeat(
                of="sequence",
                steps=(
                    Step(
                        id="sequence.id",
                        title="What should we call it?",
                        binds="sequence.id",
                        field=Text(placeholder="the-big-storm"),
                    ),
                    Step(
                        id="sequence.weight",
                        title="How likely is the chain to enter it, rather "
                        "than take an ordinary step?",
                        binds="sequence.weight",
                        field=Number(minimum=0, integer=False, optional=True),
                        help="0 means only an effect can start it.",
                        optional=True,
                    ),
                    Step(
                        id="sequence.when",
                        title="Only under some condition?",
                        binds="sequence.when",
                        field=ConditionBuilder(),
                        optional=True,
                    ),
                    Step(
                        id="sequence.steps",
                        title="The conditions, in order, one per line?",
                        binds="sequence.steps",
                        field=TextList(placeholder="storm 3"),
                        help="One line per step — `storm 3` holds a storm "
                        "for 3 ticks; bare `clear` holds for one.",
                    ),
                ),
            ),
            help="A three-day storm that breaks on the fourth morning is a "
            "story beat, and a Markov chain will not reliably produce one. "
            "Once chosen, a sequence plays out uninterrupted.",
            optional=True,
        ),
    ),
)


ENCOUNTER_TABLE = Flow(
    id="encounterTable",
    noun="encounter table",
    title="What might happen on the road",
    collection="encounterTables",
    identity=("table.name",),
    steps=(
        Step(
            id="table.name",
            title="What is this table called?",
            binds="encounterTables[{id}].name",
            field=Text(placeholder="Forest Road"),
        ),
        Step(
            id="table.extends",
            title="Build on another table?",
            binds="encounterTables[{id}].extends",
            field=Select(options=Query("encounterTables"), optional=True),
            help="A bandit-country road is a country road with worse entries.",
            optional=True,
        ),
        Step(
            id="table.chance",
            title="How likely is something to happen, per leg?",
            binds="encounterTables[{id}].chance",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help="The one dial. 0 for nothing here yet; 1 for every time.",
            optional=True,
        ),
        Step(
            id="table.minGapTicks",
            title="Is there a floor between encounters?",
            binds="encounterTables[{id}].minGapTicks",
            field=Number(minimum=0, optional=True),
            help=(
                "Ticks. Pure independent rolls can produce three ambushes in "
                "a row, and that feels broken even when it is fair."
            ),
            optional=True,
        ),
        Step(
            id="table.pressureStep",
            title="Does an empty roll make the next one likelier?",
            binds="encounterTables[{id}].pressureStep",
            field=Number(minimum=0, maximum=1, integer=False, optional=True),
            help=(
                "Tightens the variance without changing the long-run rate. "
                "0 turns it off."
            ),
            optional=True,
        ),
        Step(
            id="table.entries",
            title="What can happen?",
            binds="encounterTables[{id}].entries",
            field=Repeat(
                of="entry",
                steps=(
                    Step(
                        id="entry.id",
                        title="A short name for this entry",
                        binds="entries.id",
                        field=Text(placeholder="wolf-pack"),
                        help="Lower case, hyphens. Tracks cooldowns and caps.",
                    ),
                    Step(
                        id="entry.weight",
                        title="How likely, relative to the rest?",
                        binds="entries.weight",
                        field=Number(minimum=0, integer=False, optional=True),
                        help=(
                            "Not a probability — 5 against a total of 100 is "
                            "the five-percent troll."
                        ),
                        optional=True,
                    ),
                    Step(
                        id="entry.when",
                        title="When is it eligible?",
                        binds="entries.when",
                        field=ConditionBuilder(),
                        optional=True,
                    ),
                    Step(
                        id="entry.scene",
                        title="Which scene plays?",
                        binds="entries.scene",
                        field=Select(
                            options=Query("scenes"),
                            allow_create="scenes",
                            optional=True,
                        ),
                        help="Leave blank for a straight fight instead.",
                        optional=True,
                    ),
                    Step(
                        id="entry.combatAgainst",
                        title="Who does the player fight?",
                        binds="entries.combat.against",
                        field=MultiSelect(
                            options=Query("entities", where={"kind": "actor"}),
                            allow_create="entities",
                        ),
                        help="Leave blank if a scene plays instead.",
                        optional=True,
                    ),
                    Step(
                        id="entry.combatFleeTo",
                        title="Where does fleeing lead?",
                        binds="entries.combat.fleeTo",
                        field=Select(
                            options=Query("entities", reserved=True), optional=True
                        ),
                        help="Left blank, fleeing sends them back the way they came.",
                        optional=True,
                    ),
                    Step(
                        id="entry.once",
                        title="Does it ever repeat?",
                        binds="entries.once",
                        field=Bool(optional=True),
                        help="On, it can only ever fire once in a playthrough.",
                        optional=True,
                    ),
                    Step(
                        id="entry.cooldownTicks",
                        title="How long before it can recur?",
                        binds="entries.cooldownTicks",
                        field=Number(minimum=0, optional=True),
                        optional=True,
                    ),
                    Step(
                        id="entry.maxPerGame",
                        title="A cap looser than 'never repeats'?",
                        binds="entries.maxPerGame",
                        field=Number(minimum=1, optional=True),
                        optional=True,
                    ),
                ),
            ),
            help=(
                "Most entries should not be fights — weather, strangers and "
                "wildlife are what make a road feel alive rather than a grind."
            ),
            optional=True,
        ),
    ),
)


BACKGROUND = Flow(
    id="background",
    noun="background",
    title="Who the protagonist was",
    collection="backgrounds",
    identity=("background.name",),
    steps=(
        Step(
            id="background.name",
            title="What is this background called?",
            binds="backgrounds[{id}].name",
            field=Text(placeholder="Poacher"),
        ),
        Step(
            id="background.description",
            title="Sell it in one line",
            binds="backgrounds[{id}].description",
            field=Text(
                placeholder="You know the wood better than the man who owns it.",
            ),
            help=(
                "This is the whole of the pitch — it is what the player reads "
                "while deciding. Worth more effort than the numbers."
            ),
        ),
        Step(
            id="background.stats",
            title="What does it do to their stats?",
            binds="backgrounds[{id}].stats",
            field=StatAllocator(),
            help=(
                "Relative to the protagonist's own numbers, so raising their "
                "base strength later raises every background's with it."
            ),
            optional=True,
        ),
        Step(
            id="background.inventory",
            title="What do they start with?",
            binds="backgrounds[{id}].inventory",
            field=Repeat(
                of="stack",
                steps=(
                    Step(
                        id="stack.item",
                        title="Which item?",
                        binds="inventory.item",
                        field=Select(
                            options=Query("entities", where={"kind": "item"}),
                            allow_create="entities",
                        ),
                    ),
                    Step(
                        id="stack.qty",
                        title="How many?",
                        binds="inventory.qty",
                        field=Number(minimum=1, optional=True),
                        optional=True,
                    ),
                ),
            ),
            optional=True,
        ),
        Step(
            id="background.grantsFlag",
            title="What does it let a scene recognise later?",
            binds="backgrounds[{id}].grantsFlag",
            field=Text(placeholder="served-before", optional=True),
            help=(
                "A flag on the protagonist. This is the cheap, good part: one "
                "conditional line somewhere and the captain remembers your "
                "face."
            ),
            optional=True,
        ),
        Step(
            id="background.openingScene",
            title="Do they open on a different scene?",
            binds="backgrounds[{id}].openingScene",
            field=Select(options=Query("scenes"), allow_create="scenes", optional=True),
            help="Played instead of the start location's arrival scene.",
            optional=True,
        ),
    ),
)


#: Every flow the wizard knows, by the collection it authors.
FLOWS: dict[str, Flow] = {
    "backgrounds": BACKGROUND,
    "climates": CLIMATE,
    "combatProfiles": COMBAT_PROFILE,
    "encounterTables": ENCOUNTER_TABLE,
    "entities": ENTITY,
    "locations": LOCATION,
    "moves": MOVE,
    "quests": QUEST,
    "regions": REGION,
    "routes": ROUTE,
    "scenes": SCENE,
    "terrains": TERRAIN,
    "weatherConditions": WEATHER_CONDITION,
    "weatherFronts": WEATHER_FRONT,
}


def flow_for(collection: str) -> Flow:
    """The flow that builds one collection.

    Parameters
    ----------
    collection : str
        The collection name.

    Returns
    -------
    Flow
        Its flow.

    Raises
    ------
    KeyError
        If nothing authors that collection yet, and the wizard says so
        rather than pretending.
    """
    return FLOWS[collection]
