# MACE — Modular Adventure Creation Engine

**An engine and authoring toolkit for living, text-driven adventure worlds.**

MACE lets anyone build a text adventure by answering questions instead of writing
code — and lets anyone else play it, in a terminal or a browser. Games are
**data, not code**: a folder of YAML describing a map, its people, its weather,
and its trouble.

The engine is genre-neutral. Medieval fantasy is the first content library, not a
constraint — a generation ship, a drowned city, or a dust-bowl noir are the same
structures with different packs.

> **Status: early.** The design is settled and written down in [`docs/`](docs/);
> the code is a v0 prototype catching up to it. See the
> [roadmap](docs/12-roadmap.md) for what exists and what's next.

---

## What makes it different

**The world runs whether you act or not.** A tick of world time passes; weather
transitions along a real climate model; storm fronts cross the map from region to
region. Travelling the north road takes six ticks — three hours — so leaving at
dusk means arriving in the dark, and a storm coming down out of the range means
arriving late, soaked, and slow. Play the same game twice and the journeys
differ. → [World Simulation](docs/05-world-simulation.md)

**Some things you can see coming. Some you can only feel building.** An eclipse
is on the calendar — find an almanac and you'll know the date, and can plan a
quest around it. The volcano is not on any calendar. It has a hidden pressure
that has been rising all game, and all you get is omens: a grey cast on the snow,
a tremor you could almost doubt, the birds leaving the range all at once. You
can know it's close. You can't know it's Tuesday. That's the decision.
→ [World Events](docs/05-world-simulation.md#layer-5--world-events)

**Roads are dangerous, plausibly.** Every route carries an encounter table.
Sometimes an ogre — but only at dusk, and only when it isn't raining. Five
percent of the time, a troll. Most of the time, a caravan, a shrine, a change in
the weather, or nothing at all. Tuned so a journey feels alive rather than like a
grind. → [Travel & Encounters](docs/06-travel-and-encounters.md)

**Combat rewards skill, not dice.** Enemies telegraph their moves; you read the
tell, pick the counter that beats it, and commit within a timing window. Enemies
have *patterns* you can learn. Your stats set how wide the window is and how hard
you hit — you decide what happens inside it. The design target is explicit: a
player who has fought three trolls should beat the fourth more reliably than one
who hasn't, with an identical character sheet. (A no-timing `tactical` mode keeps
all the depth for players who don't want reflex play.)
→ [Combat](docs/07-combat.md)

**Nothing gets built twice.** Content lives in versioned, namespaced packs.
Import `fantasy.core:bridge-troll`, override the two fields you want different,
and get on with your story. → [Content Library](docs/11-library-and-community.md)

**Authoring is answering questions.** The wizard is the product, not a
convenience wrapper. Every reference is picked from a list of things that exist,
every mistake is caught when you make it, and you can playtest from any point in
your world at any time — "start me at the bridge, at midnight, in a blizzard."
→ [Authoring & the Wizard](docs/09-authoring-and-wizard.md)

---

## What a game looks like

```yaml
# The road north: six ticks of travel, a troll halfway, and weather that bites.
- id: north-road
  from: fenmoor
  to: hagans-castle
  ticks: 6
  waypoints:
    - {location: troll-bridge, atTick: 3, encounters: bridge-encounters}
  encounters: forest-road-encounters
  legDescriptions:
    - {text: "Crows argue in the branches overhead.", when: {dayPart: [day]}}
    - {text: "The rain finds every gap in your cloak.", when: {weatherTag: [wet]}}
```

```yaml
# Sometimes an ogre. Five percent of the time, a troll. Usually, nothing much.
- id: forest-road-encounters
  chance: 0.30
  minGapTicks: 4
  entries:
    - {id: quiet-stretch,  weight: 40, scene: nothing-much-happens}
    - {id: caravan,        weight: 30, when: [{dayPart: [dawn, day]}], scene: caravan-offers-a-ride}
    - {id: ogre-ambush,    weight: 20, when: [{dayPart: [dusk, night]}], scene: ogre-ambush}
    - {id: wandering-troll, weight: 5, once: true, scene: troll-on-the-road}
```

A full worked example is in
[`docs/examples/peasants-quest/`](docs/examples/peasants-quest/).

---

## Documentation

Start with the [documentation index](docs/README.md).

| | |
|---|---|
| [Vision & Principles](docs/01-vision.md) | What this is for, and the values that settle arguments |
| [Architecture](docs/02-architecture.md) | The deterministic core, the event protocol, repo layout |
| [Content Model](docs/03-content-model.md) | Packs, ids, inheritance, conditions and effects |
| [Schema Reference](docs/04-schema-reference.md) | Every content type, field by field |
| [World Simulation](docs/05-world-simulation.md) | Clock, climate, weather fronts, world events |
| [Travel & Encounters](docs/06-travel-and-encounters.md) | Routes, journeys, probability tuning |
| [Combat](docs/07-combat.md) | Tempo combat |
| [Economy](docs/08-economy.md) | Goods, markets, trade flow, haggling |
| [Authoring & the Wizard](docs/09-authoring-and-wizard.md) | How games get made |
| [Clients & Interface](docs/10-clients-and-interface.md) | CLI, the PWA, the map, offline play |
| [Library & Community](docs/11-library-and-community.md) | Reuse, contribution, review |
| [Roadmap](docs/12-roadmap.md) | Phased plan |
| [Open Questions](docs/13-open-questions.md) | What's deliberately still undecided |
| [Decision Records](docs/decisions/) | Forks in the road, and why we went the way we did |

---

## Development

```bash
git clone git@github.com:lightningWhite/MACE.git
cd MACE

python3 -m venv env                 # apt install python3-venv, if needed
source env/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'             # or: pip install -r requirements.txt

pre-commit install --hook-type pre-commit --hook-type pre-push
pre-commit run --all-files
pytest
```

Deactivate with `deactivate` when you're done.

Requires **Python 3.12+**. `black`, `ruff`, and `mypy` run on commit; `pytest`
runs on push.

**Playing.** The first playable game pack, and the first working commands:

```bash
mace play packs/ --pack peasants-quest
mace play packs/ --pack peasants-quest --seed autumn   # replays identically
```

**Checking content.**  It loads every pack under a
directory, resolves inheritance and references, and reports what's wrong at
three severities — errors break the game, warnings are almost certainly
mistakes, notes are worth a look:

```bash
mace validate packs/
mace validate --errors-only packs/     # what CI cares about
```

**Running the v0 prototype wizard** (superseded by the design in
[docs/09](docs/09-authoring-and-wizard.md), but it runs). It writes generated
games into `packs/games/`:

```bash
cd src && python3 wizard.py
```

**The v0 templates** in [`templates/`](templates/) documented the original
design. The generated JSON Schemas in [`schemas/`](schemas/) now describe the
real one — point your editor at them for completion while authoring.

---

## Contributing

Not yet accepting outside content packs — the schemas aren't stable, so anything
built now would break. Once [phase 1](docs/12-roadmap.md#phase-1--the-content-pipeline)
lands, the plan is a repo full of worlds anyone can clone and play, with CI that
validates and autoplays every submitted pack.

Ideas and design arguments are very welcome in the meantime, especially against
the [open questions](docs/13-open-questions.md).

## License

Engine: [MIT](LICENSE). Content packs declare their own license in `pack.yml`,
defaulting to CC-BY-4.0.

---

<sub>MACE originally stood for "Magic and Combat Environment." It was re-expanded
to "Modular Adventure Creation Engine" once the engine stopped being about only
magic and combat.</sub>
