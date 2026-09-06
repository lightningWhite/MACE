# Packs

Content. No code lives here.

| Pack | Kind | What it is |
|---|---|---|
| `mace.core` | library | Genre-neutral scenes any game can reach into. Nothing here knows what century it is. |
| `fantasy.core` | library | Trolls, bread, gold, and the archetypes a fantasy game extends. |
| `games/peasants-quest` | game | Four locations, a troll who wants paying, and seven days to reach the castle. |

```bash
mace validate packs/                              # what CI runs
mace play packs/ --pack peasants-quest            # play it
mace play packs/ --pack peasants-quest --seed x   # the same seed replays exactly
```

A pack is any directory with a `pack.yml`. File organization inside one is
free — the loader globs and merges by id, so one file per location and one file
for all of them are equally correct. Point your editor at
[`schemas/`](../schemas/) for completion while writing.

See [docs/03](../docs/03-content-model.md) for the content model and
[docs/11](../docs/11-library-and-community.md) for what makes a library pack
worth depending on.
