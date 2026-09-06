# Worked Example — A Peasant's Quest

The v0 partial examples in `templates/partialExamples/`, rewritten in the design
described in [`docs/`](../../). This is a *specification by example*: it shows
what a real pack should look like once phase 1 lands, so the schemas and models
have a concrete target.

It is a fragment, not a complete game — enough to show every concept in use.

| File | Shows |
|---|---|
| `pack.yml` | Manifest, dependencies, versioning |
| `game.yml` | Intro, player setup, world/calendar config, win/lose |
| `locations.yml` | Locations, regions, exits, climate overrides, conditional descriptions |
| `routes.yml` | Travel time, waypoints, leg flavor, encounter attachment |
| `entities.yml` | Player, NPC, monster, item, container — all one type, with `extends` |
| `scenes.yml` | Interaction graph with `goto`, `else`, structured conditions and effects |
| `encounters.yml` | Two-stage tables — the "sometimes an ogre, 5% a troll" case |
| `events.yml` | A scheduled eclipse, a volcano that might go, a hillside that might slip |
| `quests.yml` | Staged objectives with a deadline |
| `backgrounds.yml` | Three starting variants for the protagonist |
| `economy.yml` | Goods with elasticity, and a three-market trade network |

Compare against `templates/partialExamples/` to see what changed and why. The
biggest differences: scenes are named and flat, logic is structured instead of
stringly-typed, travel takes time, and everything reusable comes from
`fantasy.core` rather than being redefined here.
