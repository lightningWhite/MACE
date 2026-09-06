# 10. Content Library & Community

> "I'd like people to be able to add to the library of objects, places,
> characters, environment conditions, etc. Then as people build new games, they
> can reuse stuff and modify it as needed."

Reuse is a *design* problem before it's an infrastructure problem. Namespacing
and `extends` (see [Content Model](03-content-model.md)) are the mechanism; this
document is about what gets put in the libraries and how contributions work.

## The pack hierarchy

```
mace.core          Genre-neutral. Stat conventions, day parts, calendars,
                   base weather conditions, the counter matrix, generic scenes
                   (buy/sell, rest, search). Nothing here says "sword."
     │
     ├── fantasy.core     Medieval fantasy: trolls, orcs, taverns, temperate and
     │                    alpine climates, roads, forest encounter tables
     ├── scifi.core       Ship decks, vacuum, ion storms, hull breaches, drones
     └── modern.core      Cities, streets, vehicles, contemporary hazards
              │
              └── games/*  Playable games, each depending on what it needs
```

`scifi.core` exists partly to prove the engine is genre-neutral. If building it
requires touching the engine, the engine has fantasy assumptions baked in and
that's a bug. It's a deliberate design check, not just content.

## What belongs in a library

The test: **would a second author plausibly want this exact thing?**

| Good library content | Belongs in a game pack instead |
|---|---|
| `bridge-troll` — a generic troll statblock | `gorm` — *the* troll on *your* bridge, with dialog about your king |
| `tavern-keeper` with haggle and rumor scenes | The innkeeper who knows where the amulet is |
| `temperate` climate, `blizzard` condition | "The Long Winter of 'S3" as a scripted sequence |
| `forest-road-encounters` as a tunable table | The specific ambush that starts act two |
| `quick-duelist` combat profile | The final boss's unique pattern |

The rule of thumb: **libraries hold nouns and behaviors; games hold names, plot,
and place.** A library entity should be usable without reading the game it came
from.

## Making library content extendable

Library authors should design for override, and the wizard should nudge them
toward it:

- **Keep names generic and descriptions neutral.** `"A hulking creature with
  moss in its hair."` extends well. `"Gorm, who has guarded this bridge since
  your grandfather's day."` does not.
- **Split statblock from personality.** Ship `bridge-troll` (stats, combat,
  no scenes) and `bridge-troll-encounter` (a scene that uses it) separately, so
  authors can take one without the other.
- **Leave hooks.** A library scene can `goto` an id the game is expected to
  define, declared via `expects:` in the pack manifest so validation catches a
  missing hook rather than a dangling reference.
- **Tag generously.** Tags are how encounter tables, effects, and environment
  responses select things in bulk. An untagged entity is hard to reuse.
- **Version honestly.** Changing an id or removing a field is a major bump.
  Content is an API.

## Repository layout for the community

```
packs/
├── mace.core/
├── fantasy.core/
├── scifi.core/
└── games/
    ├── peasants-quest/          maintained in-tree as the reference game
    └── community/
        ├── the-drowned-city/
        └── station-nine/
```

Contributed games live in-tree first. A repo you can clone and immediately play a
dozen worlds from is the whole appeal, and it keeps quality visible. A separate
registry only becomes necessary when the repo gets too big to clone comfortably —
which is a good problem and a long way off.

## Contribution flow

1. Fork, build with the wizard, `mace validate` locally.
2. Open a PR with the pack.
3. CI runs:
   - **Schema validation** on every file.
   - **Reference integrity** — no dangling ids across the whole pack graph.
   - **Reachability** — the win condition is achievable via at least one path
     through the scene/quest graph; no orphaned content.
   - **Autoplay smoke test** — N seeded playthroughs in `auto` combat mode with a
     random-choice agent. Catches crashes, softlocks, and unwinnable states that
     no human would find quickly. This is the highest-value check by far.
   - **Balance report** — posted as a PR comment, not a gate: expected difficulty
     curve, encounter rates, whether the player can be starved of a required item.
4. Human review for tone, licensing, and content policy.

The autoplay test is what makes accepting community content tractable — a
maintainer should not have to play a stranger's four-hour game to know it works.

## Licensing

- **Engine:** MIT (already established in `LICENSE`).
- **Content packs:** default CC-BY-4.0, declared per pack in `pack.yml`. A pack
  may choose otherwise; the field is required so it's never ambiguous.
- Contributors must own what they submit. No text lifted from published games or
  novels, no assets with unclear provenance. The PR template asks explicitly.
- Packs declaring incompatible licenses can't depend on each other; the validator
  checks this and fails loudly.

## Content policy

An open community repo needs a stated line, and it's easier to write now than
during an argument. Games may be dark — this is a genre about violence and peril.
They may not be vehicles for real-world hate, sexual content involving minors,
harassment of real people, or malware in a pack. `CONTRIBUTING.md` and a
`CODE_OF_CONDUCT.md` should carry this before the first outside PR arrives.

## Discovery

Once there are more than a handful of games, the play menu (CLI and web) reads
pack manifests to offer: name, tagline, author, tags, estimated play time,
difficulty, and last update. All of that already exists in `pack.yml` — which is
why those fields are in the schema from the start rather than added later.

## The long road to multiplayer

Deliberately not designed in detail yet, but the architecture is chosen so it
isn't a rewrite:

- Deterministic simulation + action logs means a server can be authoritative and
  clients can predict.
- Named RNG streams mean two players' independent events don't desync each other.
- The content/state split means one world definition can back many sessions.

The likely first step is **asynchronous shared worlds** — several players'
sessions in one persistent world, where your choices leave traces others find:
the bridge you burned, the troll you killed, the message you left at the shrine.
That's achievable without real-time netcode and fits the medium far better than
synchronous play. See [Open Questions](13-open-questions.md).
