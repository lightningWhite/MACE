# ADR-0010 — Linear range as a combat axis

**Status:** Accepted

## Context

[Tempo combat](../07-combat.md) resolves an exchange as `read × precision ×
stats × gear`, with distance nowhere in it — every weapon is implicitly
"in range" the instant a fight starts. That's fine for a shortsword duel but
flattens a bow, a spear, and a thrown rock into the same thing with a
different damage band, and it means "get in close" or "keep your distance"
can never be a real decision.

[ADR-0006](0006-tempo-combat.md) already weighed a spatial axis and rejected
it, but as **tactical grid combat** — positions, facing, zones of control. The
idea on the table now is much smaller: a single scalar, feet of distance, with
an effective band and a sweet spot inside it, the same shape the timing window
already uses. This ADR asks whether that lighter version is worth doing, given
the earlier rejection was specifically about the grid, not about range itself.

[ADR-0008](0008-the-player-answers.md) also constrains the shape: the player
is not in the action-meter race and has no attack moves, only defenses —
`strike` is the one defense that carries damage, modelled as an interrupt.
Range has to hang off of that, not off of a player "attack" that doesn't
exist.

## Decision

**Range is `{min, max, sweetMin, sweetMax}` in feet, and it lives wherever
damage already lives for that same move.** That split already exists in
`roster.py`/`fight.py` and range should follow it exactly rather than invent
a second rule:

- **Attack-kind moves carry `range` directly**, the same place they already
  carry `damage` — `club-overhead`, `sword-thrust`, `bite` are all baked-in
  content with no equipped item behind them at all in the shipped packs, so
  there is nothing for range to default *from*.
- **`strike`** — the player's only source of damage (ADR-0008) — is one
  generic, weapon-agnostic move shared by every profile verbatim. Its damage
  already isn't on the move; it's `Fighter.weapon_damage`, resolved fresh
  each exchange from whatever's equipped and falling back to a constant,
  `UNARMED`, when nothing is. `strike`'s range follows the identical path:
  a new `Fighter.weapon_range`, sourced from the equipped item's `range`
  (a new optional field on `ItemProps`) and falling back to a new
  `UNARMED_RANGE` constant sitting next to `UNARMED`. This *is* "hands as a
  default weapon" — the engine already has this pattern for damage; range
  just needed to be told to use it too.

Range does not stack the way `strike`'s small bonus damage stacks on top of
`weapon_damage` — there is one effective band per exchange, not two added
together, so `strike` itself carries no `range` field of its own.

Whether unarmed capability is "applicable to the character" needs no new
mechanism: it's already gated by whether a fighter's profile lists `strike`
(or any weapon-agnostic move) at all. A fighter with no such move never
touches `UNARMED_RANGE`, armed or not — the same way it never touches
`UNARMED` today.

Whatever range applies, a move whose distance falls outside `[min, max]`
cannot be attempted at all; inside it, effectiveness ramps from 0 at the
outer edge to 1.0 across `[sweetMin, sweetMax]` — the same clamp shape
`precision` already uses for timing, so a range factor composes into
resolution as one more multiplicative term rather than a second,
differently-shaped system:

```
read × precision × rangeFactor × stats × gear
```

Nothing lives on the profile — a profile is temperament (patterns, feints,
aggression), and range would be a strange thing to vary by temperament rather
than by what a move already is. A duelist's thrust (3–5 ft) and kick (0–2 ft)
are already two different attack moves with their own `damage`; they simply
also get their own `range` now, and a profile's existing `patterns` already
teach the player when an enemy needs to close distance before it can throw
one.

**Distance is a scalar per combatant**, not a grid position. Every
`Combatant` gets a `position: float` (feet, along one shared line); the
distance between any two combatants is `abs(a.position - b.position)`. This
is fight-only ephemeral state — it lives in `CombatState`/`Combatant`
(session state), never in content, per the content/state split in
`CLAUDE.md`.

**A fight opens at the edge of whatever the player has armed** — `begin()`
resolves the player's `Fighter` before any enemy `Combatant` is constructed
(`fighter_for` only needs the entity and its gear, not a fight already under
way), reads `weapon_range.sweetMax`, and places every enemy that far out. Not
the harder `max` — that's the point a weapon is already down to zero
effectiveness, and starting every fight there would waste everyone's first
exchange, armed or not. `sweetMax` is deliberately what "at range" means
here: the far edge of where a weapon is still fully effective. Because an
unranged move or weapon's `range` already falls back to `UNARMED_RANGE`
(`min=0, max=4, sweetMin=1, sweetMax=3`), an unarmed or ordinary-melee fight
opens at `sweetMax=3` — inside its own sweet band — so the "no-op for
existing content" property from the read-side wiring holds here too: nothing
that has never touched `range` sees a different starting distance than it
implicitly always had.

**Movement rides along with the answer the player was already giving**, not a
separate action. `combat.input` gains an optional `moveBy` (signed feet),
resolved in the same exchange as the response, clamped to a max step that
widens with `speed` using the identical formula shape the timing window
already uses:

```
maxStep = BASE_STEP × (1 + (mover.speed - 50) / 200)
```

This is the piece that makes the mechanic "exciting and dynamic" rather than
a chore: closing the gap or backing off is bundled into the same beat as
parrying or striking, not a turn spent on footwork instead of fighting. It
also keeps ADR-0008 intact — the player still only ever answers a tell; they
never get a turn of their own to spend on movement alone.

Enemies move on their own meter turns, the same way: when an enemy's meter
fills and nothing in its current pattern step is in range, it spends that
turn closing or opening distance (narrated — "the troll closes the
distance") instead of telegraphing. No new race is introduced; this is the
existing per-combatant meter, now sometimes producing a movement beat instead
of a tell.

**Some weapons are consumed by use.** `ItemProps` gains `ammo: int | None` —
`None` means unlimited (a sword), a number counts down each time a move that
reads `weapon_damage`/`weapon_range` resolves, and hitting zero drops
`fighter_for`'s gear lookup past that item, back to `UNARMED`/
`UNARMED_RANGE` (or the next held item, if slots allow more than one).

**Switching weapons mid-fight is new engine surface**, not a reuse of
something that already exists: `combat.yml`'s `use:<item>` response only
covers items with a `use` block (potions), not equipping. This adds a
parallel `equip:<item>` response — same shape, same cost (the exchange, the
same way `use:<item>` already spends it) — gated to weapon-kind items in
inventory. It's the actual answer to "a ranged fighter got closed on": swap
to the dagger, don't rely on a hardcoded fallback.

## Alternatives considered

**A 2D grid with facing and zones of control** — ADR-0006's rejected option,
revisited and rejected again for the same reasons: it's a different game, it
doesn't fit a text medium, and it multiplies authoring cost (every profile
would need positioning logic, not just moves). A 1D scalar keeps the
"author writes four lines and gets a fight" promise in `07-combat.md` intact —
range/sweet-spot on a move is two more numbers, not a new content type.

**Range on the move, uniformly, for every move including `strike`.** The
first draft. Rejected on direct feedback: it buries "a bow is a ranged
weapon" as something inferable only by reading whatever `strike` happens to
resolve against, and it invents a new rule instead of reusing one that
already exists — `strike`'s *damage* isn't on the move either, it comes from
`weapon_damage`. Range should follow the same wire, not a new one.

**Range on the item, uniformly, with moves inheriting a default and
sometimes overriding it.** The second draft — item default, move override,
for every move. Rejected once it became clear enemy attack moves
(`club-overhead`, `sword-thrust`, `bite`) have no backing item in the shipped
content at all and already carry `damage` directly; giving them an "item
default" they can never use would be a rule with no referent for most of the
content that needs range. Splitting by move kind — attacks carry it directly,
`strike` inherits it via `weapon_range` — isn't a compromise between the two
drafts, it's just following the split the engine already made for damage.

**A separate `rangeKind: melee | ranged | thrown` label on the item**,
alongside the numeric band. Rejected as a redundant source of truth: `range`
already says whether a weapon is ranged (its `min` is past melee distance) or
not, and a second, hand-authored field can only ever drift from the numbers
or restate them. Anything that wants to group weapons as "ranged" for a UI —
the wizard's item picker, say — can derive it from `range.min` instead of
reading a label an author might get wrong.

**Movement as its own response, costing the exchange like `recover`.** This
was the first draft. Rejected on direct feedback: it makes footwork compete
with fighting for the same slot instead of feeling like part of the same
motion, which is the opposite of "exciting and dynamic." Bundling `moveBy`
into every response (including a plain `parry`) costs nothing extra and reads
as "I stepped back while I blocked," which is how the user described wanting
it to feel.

**Picking up a spent thrown weapon mid-fight.** Considered and deferred, not
rejected outright — it's a world/inventory interaction (an item on the
ground), not a new combat-exchange concept, and folding it into the exchange
loop is exactly the kind of scope creep ADR-0006 already pushed back on once.
If it turns out to matter in play, it can be added later as a response that
costs the exchange, same as switching does now.

## Consequences

- **Enemy attack legality now depends on distance, so pattern authoring gets
  one more constraint**: a pattern that sequences a melee move after a ranged
  one implicitly requires the enemy to close first, and the engine plays that
  as a movement beat rather than silently teleporting. Library profiles need a
  pass to make sure their move ranges are coherent with their patterns.
- **`Fighter.weapon_range` and `UNARMED_RANGE` are new fields next to
  `weapon_damage`/`UNARMED` in `roster.py`**, resolved by `fighter_for` the
  same way and at the same point. `strike` inherits a range from whatever is
  equipped, so switching to a bow changes not just damage but *when* the
  interrupt is even available — a bow-wielder can't `strike` a grappler at
  2 ft, and has nothing without the `equip:<item>` response to swap to
  something closer. This is new texture on the "reads vs. gear" balance and
  needs the same kind of measurement `07-combat.md`'s balance table already
  does for the timing system. A player who never carries a sidearm and gets
  rushed while holding a bow can genuinely lose the ability to answer with
  damage until they spend an exchange fixing it — that is meant to be a real
  cost of the loadout, not a bug to patch over with an unconditional fallback.
- **Ranged enemies can now kite.** An archer profile whose sweet spot is
  20–40 ft has a real reason to retreat rather than stand still, which is
  good texture but needs a bound — either arena/room edges on `position`, or
  a per-profile willingness-to-retreat-only-so-far dial — so a fight can't
  turn into an archer backpedaling for `MAX_EXCHANGES`.
- **A new event/UI surface, built on both front-ends.** `combat.tell` and
  `combat.resolve` carry `distance`; `combat.responses` carries `weaponRange`
  — the same number `strike` itself reads, so the bar can't draw something
  the engine doesn't actually reward, the discipline `TimingBar` already
  holds for the window. The CLI's `+`/`-` (`=`/`_` as unshifted aliases)
  nudge a running total that keeps the countdown open rather than ending it;
  the web client's `RangeBar` is `TimingBar`'s static counterpart — a band
  and a sweet zone that don't drain, plus a marker that moves as the same
  accumulator changes, spent out of the identical clock.
- **Determinism**: `moveBy` is recorded on the action like `elapsedMs` is, so
  a replay resolves against what was written down, not a re-derived value —
  same discipline ADR-0004 already requires for timing.
- **`auto` mode's movement policy is corrective, not optimizing.** The
  attacker side already had one — `_close_in`, an enemy closes or gives
  ground when nothing in its pattern can reach at all. `_auto_answer` now
  does the same for whoever is defending (the player in a full-`auto` fight,
  an ally answering on its own in any mode): `_auto_move` only acts when its
  own `weapon_range` genuinely can't reach, not to chase the sweet spot every
  exchange. A stats-only baseline that never got stuck out of its own
  weapon's range, but also never micromanaged position, is the useful
  baseline to balance the real one against.
- **`equip:<item>` is a new reserved response** alongside `FLEE`/`RECOVER`/
  `FOCUS`/`USE` in `roster.py`, and `responses_for` needs to offer it only
  when the inventory actually holds another weapon-kind item — the same
  restraint `FOCUS` already gets (offered only when there's someone to
  direct and something to direct them at).
- **Weapon-based engagement assumes the player saw the fight coming**, which
  an ambush by definition didn't give them time to do. `StartCombat` gains
  `surprise: bool`, threaded through `_start_combat`/`begin()`, that skips
  resolving the player's `Fighter` for positioning and opens at the melee
  default (`UNARMED_RANGE.sweetMax`) outright. Scoped deliberately narrow —
  it changes only where the fight opens, not whether the first exchange is
  answerable at all. A fuller "surprise round" (an unanswered opening blow,
  say) is a separate mechanic this doesn't attempt. `CombatEncounter` (road
  ambushes, as opposed to an authored scene's `startCombat`) doesn't get the
  same field yet — left for a follow-up if it turns out to matter, rather
  than growing this change to cover every path a fight can start from.
