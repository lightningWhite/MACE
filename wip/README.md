# wip/

In-progress games and libraries — content that isn't ready to validate
because you're mid-scene, mid-quest, or trying something to see if it holds
together. Nothing under here is loaded by default.

`mace validate packs/` — what CI and the pre-push pytest hook both run —
never looks in here, and neither does anything else that defaults to
`packs/`. A half-built game can sit broken for as long as it needs to
without failing a push or a check for unrelated work.

It's still a pack directory like any other — same `pack.yml`, same loader,
same wizard — so play or validate it explicitly, naming it alongside the
libraries it depends on:

```bash
mace validate packs/ wip/                          # check it, deliberately
mace play packs/ wip/ --pack the-lost-heir          # play it
mace dev --packs packs/ --games wip/                # author it in the browser
```

Move a game to `packs/games/` once `mace validate packs/ wip/` passes
clean — that's the signal it's done enough to join the checked-in, always-
valid set everyone else's checks run against.
