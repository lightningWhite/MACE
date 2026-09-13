# 7. Combat — Tempo Combat

## The design target

> "I'd like combat to be somewhat skill-based instead of pure chance... some way
> to make it feel like they're really doing good because they actually are good
> or improving."

The acceptance test for this whole system:

> **A player who has fought three trolls beats the fourth more reliably than a
> player who hasn't — with an identical character sheet.**

If that isn't true, the system has failed and should be redesigned. Everything
below exists to make it true.

## The core loop

Combat is a sequence of **exchanges**. Each exchange:

```
   1. TELL          The enemy telegraphs its next move.
                    "The troll hauls the club up over its head."
                    ▸ move type: overhead   ▸ window: 1400ms   ▸ range: 3-6ft

   2. READ          You choose a response. The right response depends on
                    the move type — this is knowledge.
                    [P]arry [D]odge [B]lock [S]trike [R]ecover [F]lee [Br(e)ad]

   3. TIME & CLOSE  When you commit matters, and so does where you're
                    standing — both ride on the same answer. Early is
                    hesitant, late is too late; too far out and a `strike`
                    can't reach at all.

   4. RESOLVE       read correctness × timing precision × range × stats × gear
                    → damage dealt, damage taken, stamina spent, momentum
```

Two axes of skill, and they're genuinely different: **knowing** what beats an
overhead (learnable, permanent, transfers between fights) and **executing** it
under a deadline (practiced, per-fight). Both must matter; neither alone should
be sufficient.

## Reads — the knowledge layer

Moves have a `type`; defenses counter specific types. The counter matrix is
**content, not engine code**, so a sci-fi pack can define entirely different
verbs.

| Enemy move type | Beaten by | Bad answer |
|---|---|---|
| `overhead` (slow, huge) | `dodge` | `block` — it goes through your guard |
| `slash` (wide) | `block` | `dodge` — too wide to step out of |
| `thrust` (fast, precise) | `parry` | `block` — a straight edge slips it |
| `sweep` (low) | `jump` / `dodge` | `parry` — nothing to parry |
| `grapple` | `strike` (interrupt) | any defense — you get grabbed |
| `feint` | *any defense wastes stamina*; correct answer is `strike` | committing to a defense |

Four outcomes per exchange:

| Read | Timing | Result |
|---|---|---|
| Correct | Good | **Counter.** No damage taken, momentum up, an opening for a free strike. |
| Correct | Poor | **Absorbed.** Reduced damage, stamina cost, no opening. |
| Wrong | Good | **Glancing.** Partial damage — good reflexes salvage a bad read. |
| Wrong | Poor | **Clean hit.** Full damage, momentum lost. |

The player learns the matrix in five minutes and then spends the rest of the game
learning *enemies*, which is where the depth is.

## Patterns — the thing you actually learn

An enemy without a pattern is noise, and noise can't be learned. Every combat
profile has weighted **sequences**:

```yaml
- id: bridge-troll-profile
  moves: [club-overhead, club-sweep, troll-grab, troll-roar]
  aggression: 0.7
  feintChance: 0.1
  tellClarity: 0.8
  patterns:
    - sequence: [club-overhead, club-overhead, club-sweep]
      weight: 50
    - sequence: [troll-roar, club-sweep, troll-grab]
      weight: 30
    - sequence: [club-sweep, club-overhead]
      weight: 20
  fleeThreshold: 0.15
```

The engine picks a pattern, plays it out, then picks another. So a troll really
does have habits: it likes to swing twice high then go low. A player who notices
that wins. That is the entire point.

`feintChance` and `tellClarity` are the difficulty dials — a veteran duelist
feints often and telegraphs faintly, and beating one feels earned.

## Timing — the execution layer

The windup window is `move.windupMs`, adjusted by the defender:

```
window   = move.windupMs × (1 + (defender.speed - 50) / 200) × difficultyScale
ideal    = 0.75 × window          # the sweet spot sits late — you must hold nerve
precision = clamp(1 - |t_input - ideal| / (0.5 × window), 0, 1)
```

A speed-70 defender facing a 1400 ms overhead gets 1540 ms. Stats widen the door;
the player still has to walk through it. This is the specific mechanism by which
**character growth and player growth both matter without either making the other
irrelevant** — and it's why stats can never be enough on their own.

`difficultyScale` is where familiarity lands: a character who has read this
profile forty times gets a window 20% wider, which is the character learning
trolls alongside the player.

The same familiarity gates what `combat.begin` says about an opponent's
stats, so a player learns an enemy's numbers the same way they learn its
patterns. A stranger's `strength`/`speed` are never shown, the same as
today; once the reader's own fighter has faced this profile before, a
qualitative read appears ("Hits hard.", "Quick."), sharpening to the exact
numbers once the profile is fully known. Showing every opponent's exact
stats immediately was considered and rejected — it would hand away the
numbers this document spends its whole first half arguing should be earned,
not given.

Committing *after* the window is not a slow answer, it is no answer:
`precision` is zero and the outcome is whatever a wrong read timed badly gets.
Late is late.

The arithmetic runs on integer milliseconds down to a single division, because
an exchange that resolves one way in Python and another in a browser is not an
exchange anybody can balance. Elapsed times are quantized to 10 ms before
anything looks at them, so two machines reading 812 ms and 814 ms agree
(ADR-0004).

Front-ends express the same window differently:

- **PWA:** a shrinking bar with a highlighted sweet zone. Direct, readable,
  learnable.
- **CLI:** the tell prints, a key is read with a monotonic deadline, precision is
  computed from elapsed time. Works in a plain terminal.

Both send the same `combat.input {response, elapsedMs}` action. The engine never
sees a UI, and it never measures anything: the front-end writes what it measured
into the action log and the engine quantizes the recorded number, so a replay
resolves against what was written down rather than against a fresh measurement.

Where a terminal cannot be put in raw mode — a pipe, a recorded session — the
CLI says so and drops to the untimed presentation. A window that is secretly
unfair is worse than no window, and it is the exact failure this system exists
to avoid.

Reaching into your pack is a response like any other: `use:<item>` spends the
exchange, so the move that was coming lands with nobody answering it. That is
what makes the healing draught a decision about *when* rather than a button —
you buy the hitpoints with a hit, and taking one at the wrong moment is how a
fight is lost. It is the same price an order costs, for the same reason.

## Range — closing, holding, and giving ground

Distance is the third thing an exchange resolves against, alongside reading
and timing. It exists so a bow and a sword are actually different weapons
instead of the same swing with a different damage band, and so "get in
close" or "back off" is a decision rather than flavor text ([ADR-0010](decisions/0010-linear-range-in-combat.md)).

Every combatant sits at a `position` in feet along one shared line; the
distance to any other combatant is just the difference. There is no grid,
no facing, no second dimension — deliberately: a full tactical grid was
already weighed and rejected for tempo combat ([ADR-0006](decisions/0006-tempo-combat.md)),
and a single scalar keeps that promise while still making a bow feel
nothing like a dagger.

A fight opens at the edge of whatever the player has armed: the far side of
their weapon's own sweet spot (`sweetMax`, not the harder `max` — starting at
the point a weapon is already down to zero effectiveness would waste
everyone's first exchange). A bow-wielder opens a fight well clear of a
troll's reach; a dagger-wielder opens already close. Nothing about an
unranged weapon changes — its melee default's `sweetMax` sits inside its own
sweet spot, so a fight where nobody has touched `range` still opens exactly
where it always has.

That assumes the player saw it coming. `startCombat: {surprise: true}` skips
weapon-based positioning and opens at melee distance regardless of what's
armed — an ambush doesn't wait for a bow to come up. It changes only where
the fight opens; it is not a free hit or an unanswerable first exchange, both
of which are their own, larger design question this doesn't take on.

A road's own `combat:` encounters get the identical field —
`combat: {against: [...], surprise: true}` in an encounter table entry —
wired through to the same place `startCombat` reaches. It defaults to
`false`: unlike a scene's deliberate `startCombat`, a road encounter might
just as well be bandits blocking the way that the player saw coming, not
wolves out of the brush.

Range is `{min, max, sweetMin, sweetMax}` in feet, and it lives wherever
`damage` already lives for that move — no new rule, just extending the one
`fight.py` already has:

- **Attack moves carry it directly**, next to their `damage`. `club-overhead`,
  `sword-thrust`, and `bite` already have no weapon item behind them in the
  shipped packs — they *are* the weapon, as content — so a troll's sweep and
  a wolf's lunge simply get one more field:

  ```yaml
  - id: club-overhead
    type: overhead
    range: {min: 3, max: 6, sweetMin: 3.5, sweetMax: 5}
    damage: {min: 9, max: 15, type: bludgeon}
    ...
  ```

- **`strike`** — the player's only source of damage, since a playable
  character has defenses and nothing else ([ADR-0008](decisions/0008-the-player-answers.md))
  — is one generic move every profile shares verbatim, and its damage was
  never on the move to begin with: it's `Fighter.weapon_damage`, resolved
  fresh each exchange from whatever's equipped, falling back to a bare-hands
  constant (`UNARMED`) when nothing is. Range follows the identical wire: a
  new `Fighter.weapon_range`, sourced from the equipped item's own `range`
  and falling back to `UNARMED_RANGE` — hands as the default weapon, which
  the engine already does for damage and now does for range too.

  ```yaml
  - id: hunting-bow
    kind: item
    item:
      equip_slot: mainHand
      range: {min: 10, max: 80, sweetMin: 20, sweetMax: 40}
      damage: {min: 4, max: 9, type: pierce}
      moves: [strike]

  - id: dagger
    kind: item
    item:
      equip_slot: mainHand
      range: {min: 1, max: 3, sweetMin: 1.5, sweetMax: 2.5}
      damage: {min: 2, max: 5, type: pierce}
      moves: [parry, strike]
  ```

  A bow's `range` says the weapon itself is ranged — nothing about equipping
  one can be used at 2 ft, because `strike` has no range of its own to
  override it with. (Range doesn't stack the way `strike`'s small bonus
  damage stacks on top of `weapon_damage`: it's one effective band per
  exchange, sourced from whatever's in hand, not two bands combined.)

Outside `[min, max]` the move cannot be attempted at all. Inside it,
effectiveness ramps from 0 at the outer edge to 1.0 across `[sweetMin,
sweetMax]` — the identical clamp shape `precision` already uses for timing:

```
rangeFactor = 1.0                                              if sweetMin ≤ d ≤ sweetMax
            = clamp((d - min) / (sweetMin - min), 0, 1)          if d < sweetMin
            = clamp((max - d) / (max - sweetMax), 0, 1)          if d > sweetMax
```

`rangeFactor` multiplies into resolution alongside `precision`, so a called
shot at the very edge of a bow's range behaves the way a late-committed parry
already does: it can still land, just for less.

Nothing lives on the profile — range is what a move already is (an attack's
own reach, or whatever's equipped for `strike`), and a profile is
temperament, not gear. A duelist's thrust (3–5 ft) and kick (0–2 ft) are
already two different attack moves with their own `damage`; a profile's
`patterns` already teach the player when an enemy needs to close distance
before it can throw one — a pattern that sequences a melee move after a
ranged one now implicitly requires the enemy to close first.

Two things fall out of range riding on `strike` and on attack moves this way:

- **A ranged-only loadout can get stuck, on purpose.** A bow-wielder grappled
  at 2 ft can't `strike` back at all — nothing the bow grants reaches that
  close, and unlike the `ammo: 0` case there's no fallback weapon underneath
  it, because they're still holding the bow. Getting out of that is what
  [switching weapons mid-fight](#reusable-limited-and-gone) is for: spend the
  exchange, draw the dagger. A loadout with no close-range answer at all is a
  real cost of that loadout, not something the engine quietly patches over.
- **A ranged enemy can kite — bounded by the same effort pool everything
  else spends.** An archer whose sweet spot is 20–40 ft now has a real
  reason to retreat instead of standing still, and footwork in `_close_in`
  costs `MOVE_COST` of the mover's own effort pool, charged outright. An
  attacker's own pool is otherwise untouched all fight (only a *defender's*
  chosen response ever spends effort), so in a fight where it never gets to
  answer anything, retreating is a one-way drain: it runs dry, stands, and
  catches its breath instead — the same fallback as having no attack to
  draw at all — before it can afford to run again. `RECOVER_REGEN`
  outstrips `MOVE_COST`, so one rest refills enough for several more
  retreats: this throttles kiting into a running-and-resting rhythm rather
  than forbidding it, and it's the standing beats that let a pursuer close
  the gap for good.

### Moving is part of the answer, not a separate turn

`combat.input` carries an optional `moveBy` — signed feet, positive to close
the distance, negative to open it — alongside the existing `response` and
`elapsedMs`. It resolves in the *same* exchange as whatever was chosen: you
step in while you parry, or back off while you strike. There is no separate
"move" response competing for the turn, because footwork that costs its own
exchange stopped feeling like fighting and started feeling like a chore —
folding it into the answer already being given is what keeps a fight feeling
like one continuous motion.

How far you can move is bounded by speed, with the same shape the timing
window already uses:

```
maxStep = BASE_STEP × (1 + (mover.speed - 50) / 200)
```

Footwork also isn't free: a defender's own `moveBy` costs `MOVE_COST` of
their effort pool, prorated to how far they actually went — a one-foot nudge
barely registers, moving the full step every exchange adds up, the same
"why you can't just spam" the [resources](#resources-why-you-cant-just-spam)
section already covers for every other response.

Enemies move the same way on their own meter turns: when an enemy's action
meter fills and nothing in its current pattern step is in range, that turn is
spent closing or opening distance instead of telegraphing — narrated, not
silent ("The troll closes the distance."). This is the existing
per-combatant meter ([multi-combatant fights](#multi-combatant-fights)),
now sometimes producing a movement beat instead of a tell, not a second race.

`auto` mode's own defender — whoever's answering without a keypress, which
is the player in a fully-`auto` fight and an ally answering on its own in
any mode — moves the same corrective way: only when its own weapon genuinely
can't reach, never to chase the sweet spot every exchange. `auto` stays a
stats-only baseline, not a second player.

### Reusable, limited, and gone

Not every weapon answers twice. `item.ammo` counts uses: `null` is a sword —
unlimited. A number counts down each time `weapon_damage`/`weapon_range`
resolves against that item; a thrown rock is `ammo: 1`, and at zero
`fighter_for`'s gear lookup passes over it, back down to `UNARMED`/
`UNARMED_RANGE` (or the next item held, if slots allow more than one). A
thrown rock is otherwise an ordinary weapon in content terms — it grants
`strike` like a dagger does, it just runs out:

```yaml
- id: skipping-stone
  kind: item
  name: "Fist-sized Rock"
  item:
    equip_slot: mainHand
    ammo: 1
    range: {min: 5, max: 30, sweetMin: 10, sweetMax: 20}
    damage: {min: 2, max: 5, type: blunt}
    moves: [strike]
```

Picking a spent rock back up mid-fight is a world interaction, not a combat
one — it's an item on the ground, handled the way picking up anything else
is, not a new piece of exchange machinery.

**Switching weapons mid-fight is new engine surface, not a reuse of
something that already exists.** `use:<item>` today only covers items with a
`use` block — potions, not equipment. This adds a parallel `equip:<item>`
response, offered only when the inventory holds another weapon-kind item,
costing the exchange the same way `use:<item>` already does: the move that
was coming lands unanswered. It's the actual fix for "my ranged weapon got
closed on" — not a hardcoded fallback, a real decision that costs a beat.

## Resources — why you can't just spam

**Stamina** (`effortPool`) is spent by every action. Attacks cost most, defenses
cost by weight (blocking a heavy overhead is expensive, dodging is cheap but has
a recovery window), and a *wrong* defense costs extra. Stamina regenerates
slowly between exchanges and faster if you spend an exchange doing nothing.

At zero stamina you can only stagger — defenses fail automatically. So combat has
a rhythm: pressure, recover, pressure. It stops being "press the right key
twenty times" and becomes pacing, which is a second, slower skill on top of the
per-exchange one.

**Momentum** rewards streaks: each consecutive successful read multiplies damage
(1.0 → 1.15 → 1.3 → 1.5, capped) and grants openings. A clean hit taken resets it
to 1.0, a glance costs one step, and a right read timed late holds where it is.
Streaks are how a fight builds, and how a skilled player finishes a troll
in eight exchanges where a novice takes twenty-five and loses.

**Recovering** is a response like any other: you spend the exchange breathing,
take the blow that was coming, and get roughly a quarter of your effort pool
back. That is the pacing skill made concrete — it is a *choice to be hit*, and
knowing when to make it is the second, slower thing a player learns.

## Randomness — bounded, on purpose

Randomness exists only to keep fights from being solvable puzzles:

- Pattern selection (from the profile's weights)
- Feint occurrence (`feintChance`)
- Whether a telegraph is legible (`tellClarity`)
- The roll inside a move's own `damage` band — that band *is* the variance, and
  nothing multiplies another wobble on top of it
- Critical openings (~5%, scaled by momentum)

**Nothing rolls to decide whether your read was correct or your timing was good.**
Those are pure functions of the player's input — `outcome_of(correct, precision)`
has nowhere to put a seed, which is the guarantee stated as a signature. A player
who reads and times perfectly cannot lose to dice, and that is what makes
practice feel worth it.

## Three modes, one engine

Not everyone wants a reflex game, and MACE shouldn't lock those people out.
All three modes use the same moves, patterns, counters, stamina, and momentum —
they differ only in how the response is collected.

| Mode | Response collected | For |
|---|---|---|
| `reflex` | Timed window; precision from input time | The default. Full experience. |
| `tactical` | Untimed; `precision` fixed at 0.8, but the tell is shown for fewer characters or with lower clarity, so *reading* is still the challenge | Turn-based players, accessibility, slow connections, play-by-post |
| `auto` | Engine plays both sides from stats and profiles | Testing, replay verification, spectating, background NPC-vs-NPC fights |

Tactical mode preserves the acceptance test: the *knowledge* half of skill is
fully intact, and it's the larger half. Authors set a default in `game.rules`;
players can always override in settings. Achievements and leaderboards, if they
ever exist, record the mode.

## Growth

Skills improve through use, which closes the loop between the two kinds of
mastery:

- Using a weapon raises its `skills` entry, with diminishing returns.
- Weapon skill narrows the gap between poor and good timing (a master's sloppy
  parry still works) and raises damage.
- Successful reads against a *specific* enemy profile grant a small permanent
  "familiarity" bonus with that profile — the character learns trolls too.
- Stats with `growth` improve slowly from use: fleeing raises speed, taking hits
  raises endurance.

Growth is capped low enough that a skilled player with a weak character can still
beat a strong enemy, and a strong character can't autopilot. Roughly: stats
should account for about a third of outcome variance, player decisions two thirds.

## Multi-combatant fights

Fights are 1-vs-N or M-vs-N. Each enemy has its own action meter filling at a
rate proportional to its speed; tells arrive from whoever is ready. Facing three
wolves means three overlapping windows — the pressure comes from parallelism, not
from bigger numbers.

**The player is not in the meter race** ([ADR-0008](decisions/0008-the-player-answers.md)).
Enemies and allies race; the player answers. Their side of a fight is reading,
and what a clean read buys is the opening they hit back through — `strike` is a
defense that answers by hurting. Their speed is spent widening the window rather
than filling a bar, which keeps a fight a conversation about the enemy's habits
rather than two bars racing each other.

Allies act on their own profiles in `auto` mode, and whatever they swing at
answers on `auto` too, so nobody waits on a keypress for a fight they are
watching. The player can spend an exchange on an order instead of answering:
`focus` moves the party's attention to the next enemy still standing. It costs
the exchange — the move that was coming lands unanswered — which is what makes
it a decision rather than a button. It is offered only when there is somebody to
direct and more than one thing to direct them at.

## Fleeing

Always available, never free. Fleeing rolls against the fastest pursuer, costs
stamina, and grants the enemy a free exchange if it fails — and a failed break
earns nothing back, unlike the deliberate choice to recover.

Where it puts you is the author's call and then the road's. An encounter's
`fleeTo` or an effect's own setting names a place. Without one, fleeing
mid-journey pushes you back down the road you came up, with the ticks and the
weather that implies; fleeing in a room leaves you in it, because a room has
nowhere else to put you. Running away should be a decision with a story
attached.

## Where the balance actually sits

Measured against the shipped `fantasy.core` profiles, with `peasants-quest`'s
protagonist — a peasant with 50 hitpoints, strength 32, and a reaping hook.
Four simulated players, identical character sheets, differing only in how often
they pick the right counter and how tightly they hit the sweet spot. 120 fights
per cell; win rate over mean exchanges.

| | novice `.30/.25` | learning `.60/.55` | veteran `.85/.80` | expert `.98/.95` |
|---|---|---|---|---|
| Gorm the bridge troll | 1% / 8.5 | 25% / 9.6 | 69% / 8.1 | 92% / 6.6 |
| one wolf | 30% / 11.1 | 86% / 4.7 | 98% / 3.0 | 100% / 2.5 |
| two wolves | 4% / 14.5 | 49% / 10.5 | 85% / 6.5 | 98% / 4.7 |
| Captain Orin | 0% / 9.1 | 25% / 9.1 | 57% / 7.4 | 81% / 5.9 |

`auto` mode — the stats-only baseline, no player at all — wins 2% against Gorm,
70% against one wolf, 24% against two, and 2% against Orin. It sits between
novice and learning, which is what a stats-only baseline should do.

Three things to read off this:

- **The gradient is monotone in every matchup**, which is the acceptance test
  passing rather than a claim about it. `test_reading_an_enemy_wins_fights`
  guards it.
- **A lone wolf is a fair fight for someone who has never fought.** Gorm and
  Orin are not: they are things to talk past, pay off, or come back to. A
  library whose every enemy is beatable by a novice has no difficulty dial.
- **Perfect play takes no damage at all** and finishes Gorm in exactly eight
  exchanges. Both are pinned by tests, because both are promises this document
  makes.

The tuning constants all live in `mace.engine.combat.resolution` and
`mace.engine.combat.fight`, named and commented, so re-balancing is editing
numbers in one place rather than hunting for them.

## What the author writes

The point of all this machinery is that authoring stays simple. A complete new
enemy:

```yaml
- id: bandit
  kind: actor
  name: "Road Bandit"
  extends: fantasy.core:humanoid-fighter
  stats: {hitpoints: {base: 40}, speed: {base: 55}}
  equipment: {mainHand: fantasy.core:shortsword}
  combat: {profile: fantasy.core:quick-duelist}
```

Everything else — moves, tells, patterns, counters, range — comes from the
library profile. An author who wants a signature enemy writes a custom
profile; an author who wants a bandit gets a good fight for four lines, and
never has to think about `range` unless they want a weapon that behaves
unusually — a move with no `range` given falls back to a close-quarters
default, so nothing about authoring a normal melee enemy changes.

A stat or a move's damage may also be authored relative to the player's own
numbers, instead of an absolute figure meaningful only next to whatever scale
a particular game picked:

```yaml
- id: bridge-troll
  kind: actor
  name: "Bridge Troll"
  stats:
    hitpoints: {base: {relativeToPlayer: {stat: hitpoints, factor: 3}}, max: 200}
combatProfiles:
  - id: troll-style
    moves: [club-overhead]
moves:
  - id: club-overhead
    kind: attack
    type: overhead
    tell: "The troll hauls the club up over its head."
    damage:
      min: {relativeToPlayer: {stat: hitpoints, factor: 0.15}}
      max: {relativeToPlayer: {stat: hitpoints, factor: 0.25}}
```

"3x the player's hitpoints" and "15–25% of the player's hitpoints per hit"
read the same whether a game's hitpoints run 0–10 or 0–10,000, so a library
troll built this way fights sensibly in every game that uses it rather than
needing per-game retuning. Resolved against the player's stat *cap*, not
their current pool — a monster's stats resolve once, at the moment it's
spawned, and a hit's damage resolves fresh on every roll. See
[Schema Reference § RelativeValue](04-schema-reference.md#relativevalue).
