# MACE Design Documentation

These documents describe where MACE is **going**. The code is behind them — treat
these as the specification, and the current `src/` as a v0 prototype that is
being migrated toward it.

Read in order if you're new:

| # | Document | What it covers |
|---|----------|----------------|
| 1 | [Vision & Principles](01-vision.md) | What MACE is, who it's for, the design values that settle arguments |
| 2 | [Architecture](02-architecture.md) | Layers, the deterministic core, the event protocol, repo layout |
| 3 | [Content Model](03-content-model.md) | Packs, ids, inheritance, the content/state split, conditions & effects |
| 4 | [Schema Reference](04-schema-reference.md) | Field-by-field reference for every content type, and the `expr` grammar |
| 5 | [World Simulation](05-world-simulation.md) | Clock, calendar, climate, weather fronts, world events |
| 6 | [Travel & Encounters](06-travel-and-encounters.md) | Routes, journeys, encounter tables, probability tuning |
| 7 | [Combat](07-combat.md) | Tempo combat — skill-based, learnable, three play modes |
| 8 | [Economy](08-economy.md) | Goods, markets, price formation, trade flow, haggling |
| 9 | [Authoring & the Wizard](09-authoring-and-wizard.md) | The declarative flow graph shared by CLI and web |
| 10 | [Clients & Interface](10-clients-and-interface.md) | CLI, the PWA, the map view, offline play |
| 11 | [Content Library & Community](11-library-and-community.md) | Reuse, pack registry, contribution and review |
| 12 | [Roadmap](12-roadmap.md) | Phased plan from here to a hosted community |
| 13 | [Open Questions](13-open-questions.md) | Decisions deliberately still open |
| 14 | [How-Tos](14-how-tos.md) | Task-oriented recipes: which field, and wizard or hand-YAML |

Decision records live in [`decisions/`](decisions/) — one file per fork in the
road, with the alternatives that were rejected and why.

[`examples/peasants-quest/`](examples/peasants-quest/) is a fragment written
early on as a specification target — every concept, none of it playable. For
a real, complete, playable game built the current way, open
`packs/games/peasants-quest` — either read it, or run it in the wizard
(docs/14 § "A complete example").

## Vocabulary

Used consistently across all docs and code. If you find these words used loosely
somewhere, that's a bug in the doc.

| Term | Meaning |
|------|---------|
| **Pack** | A distributable folder of content. Either a `library` (reusable parts) or a `game` (playable). |
| **Entity** | Anything in the world with identity: a character, monster, item, door, chest, sign. |
| **Actor** | An entity that can act — has stats, can fight, can hold things. |
| **Location** | A named place on the map. |
| **Route** | A connection between two locations. Has length, terrain, and its own encounters. |
| **Waypoint** | A place passed through mid-route. Not chosen by the player. (The old "sublocation".) |
| **Scene** | A node in an interaction graph: some text, some effects, some choices. |
| **Tick** | The smallest unit of world time. Weather, hunger, and quest timers advance per tick. |
| **Turn** | One player decision. A turn consumes one or more ticks. |
| **Exchange** | One attack/response beat inside combat. Sub-tick. |
| **Stream** | A named, independently-seeded random number sequence. |
| **Event** | A message from the engine to a front-end describing something that happened. |
