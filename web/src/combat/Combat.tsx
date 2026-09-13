/**
 * The fight.
 *
 * It takes over the narrative pane, as docs/10 asks: the tell in words and
 * prominently, because this is a text game and the tell is prose; the window
 * draining beside it; the answers as buttons; and the two resources being
 * managed always visible.
 *
 * The one rule this file has to hold is fairness across front-ends. The
 * terminal spends the window on a wrong key as readily as on a right one —
 * "a terminal that quietly gave the time back would be a kinder window than
 * the browser's, which is the one thing a second front-end must never be" —
 * so the browser does the same. A window that runs out unanswered sends
 * `recover` with the time that actually went by, which is a deliberate choice
 * to take the hit, and is what the terminal sends too.
 *
 * In `tactical` mode there is no clock at all: no bar, no elapsed time, and
 * the engine gives the answer its untimed precision. Everything else is
 * identical, which is the whole accessibility argument for the mode.
 */

import { useCallback, useEffect, useState } from "react";

import type { Action, CombatBegan, CombatTell, Gauge, ResponsesOffered } from "../protocol";
import { keysFor } from "./keys";
import { RangeBar } from "./RangeBar";
import { TimingBar } from "./TimingBar";

/** Feet per press — clamped server-side by the mover's own speed regardless
 * of what's requested, so this only needs to be a reasonable step. */
export const MOVE_STEP = 1;

export interface Fight {
  began: CombatBegan;
  tell: CombatTell;
  responses: ResponsesOffered;
  /** `performance.now()` when this tell arrived. */
  openedAt: number;
  /**
   * `game.rules.vitalPool`, running, for everyone in the fight — keyed by
   * actor. Seeded from `began.combatants` and kept current by `stat.changed`
   * events the caller folds in as they arrive.
   */
  vitals: Record<string, Gauge>;
}

/**
 * One combatant's vital pool — a monster's hitpoints, or an ally's — and
 * what the player's own familiarity with it has earned them, if anything.
 */
function VitalBar({
  name,
  gauge,
  reads = [],
}: {
  name: string;
  gauge: Gauge;
  reads?: string[];
}) {
  const cap = gauge.maximum ?? gauge.value;
  const filled = cap > 0 ? Math.max(0, Math.min(1, gauge.value / cap)) : 0;
  return (
    <li className="combatant">
      <span className="combatant-name">{name}</span>
      <div
        className="bar bar-foe"
        role="meter"
        aria-label={`${name} ${gauge.stat}`}
        aria-valuenow={Math.round(gauge.value)}
        aria-valuemin={0}
        aria-valuemax={Math.round(cap)}
      >
        <div className="bar-fill" style={{ inlineSize: `${filled * 100}%` }} />
      </div>
      {reads.length > 0 && (
        <p className="combatant-read">{reads.join(" ")}</p>
      )}
    </li>
  );
}

/**
 * The two resources a fight is spent out of.
 *
 * Stamina is a pool and gets a bar; its cap is the character sheet's, because
 * the game's rules name which pool is the effort one and only the projection
 * knows what it tops out at.
 *
 * Momentum is not a pool. `combat.responses` carries the *multiplier* a run
 * of clean reads has earned — 1.0 through 1.5 — so it is shown as one, in
 * words. A bar would need a ceiling the wire does not state, and inventing
 * one would draw a resource that does not exist.
 */
function Resources({
  stamina,
  of,
  momentum,
}: {
  stamina: number;
  of: number | null;
  momentum: number;
}) {
  const filled = of !== null && of > 0 ? Math.max(0, Math.min(1, stamina / of)) : 0;
  return (
    <div className="resources">
      <div className="resource">
        <span className="resource-name">
          stamina <span className="dim">{Math.round(stamina)}</span>
        </span>
        {of !== null && (
          <div
            className="bar bar-effort"
            role="meter"
            aria-label="stamina"
            aria-valuenow={Math.round(stamina)}
            aria-valuemin={0}
            aria-valuemax={Math.round(of)}
          >
            <div className="bar-fill" style={{ inlineSize: `${filled * 100}%` }} />
          </div>
        )}
      </div>
      <p className={momentum > 1 ? "momentum momentum-up" : "momentum"}>
        momentum ×{momentum.toFixed(2).replace(/0$/, "")}
      </p>
    </div>
  );
}

export function Combat({
  fight,
  onAnswer,
  busy,
  staminaOf,
}: {
  fight: Fight;
  onAnswer: (action: Action) => void;
  busy: boolean;
  /** The cap on the effort pool, from the character sheet. */
  staminaOf: number | null;
}) {
  const [wheels, setWheels] = useState(true);
  const timed = fight.began.mode === "reflex";

  // A timed fight opens with the clock already draining the instant its tell
  // reaches this component — plenty of warning in a slow-paced exchange, none
  // at all for the very first tell of a fight a reader hasn't seen yet. Gate
  // just that one moment behind a click: `fight.began` is the same object
  // reference for every exchange of one fight (see `App.tsx`'s `absorb`) and
  // a fresh one for the next fight, so comparing against it needs no reset.
  // Untimed (`tactical`) fights have no clock to protect the reader from, so
  // this never applies to them.
  const [startedFight, setStartedFight] = useState<CombatBegan | null>(null);
  const gated = timed && fight.began !== startedFight;

  // The window opens when the player clicks past the gate above, not when
  // the tell arrived — otherwise the time spent reading it before that click
  // would silently count against the very window it was meant to protect.
  // `null` once the gate has already been passed lets `openedAt` below fall
  // straight back to `fight.openedAt`, the same clock every later exchange
  // in this fight already uses.
  const [openedOverride, setOpenedOverride] = useState<number | null>(null);
  const openedAt = openedOverride ?? fight.openedAt;

  const beginFight = useCallback(() => {
    setStartedFight(fight.began);
    setOpenedOverride(performance.now());
  }, [fight.began]);

  // Feet closed (positive) or opened (negative) this exchange so far. Reset
  // whenever a new tell arrives — footwork doesn't carry over between
  // exchanges any more than a keypress does. Real time keeps passing while
  // this accumulates: nudging it doesn't pause `TimingBar`, so moving and
  // answering really do share one countdown (docs/07-combat.md § Range).
  const [moveBy, setMoveBy] = useState(0);
  useEffect(() => {
    setMoveBy(0);
    setOpenedOverride(null);
  }, [fight.tell.combat, fight.openedAt]);

  const nudge = useCallback(
    (by: number) => {
      if (busy || gated) return;
      setMoveBy((current) => current + by);
    },
    [busy, gated],
  );

  const answer = useCallback(
    (response: string) => {
      if (busy || gated) return;
      onAnswer({
        kind: "combat.input",
        response,
        ...(timed ? { elapsedMs: Math.round(performance.now() - openedAt) } : {}),
        ...(moveBy ? { moveBy } : {}),
      });
    },
    [busy, gated, onAnswer, timed, openedAt, moveBy],
  );

  // The window ran out. `recover` is the answer that takes the blow on
  // purpose, and the engine is told exactly how much of the window went by
  // — footwork already spent still counts, the same as a keypress that
  // arrived too late still gets its elapsed time recorded.
  const expire = useCallback(() => {
    if (busy) return;
    onAnswer({
      kind: "combat.input",
      response: "recover",
      elapsedMs: fight.tell.windowMs,
      ...(moveBy ? { moveBy } : {}),
    });
  }, [busy, onAnswer, fight.tell.windowMs, moveBy]);

  // A fight is played with the hands on the keys, and on the same keys the
  // terminal binds: a player should not have to learn them twice.
  const bound = keysFor(fight.responses.options);

  useEffect(() => {
    if (busy || gated) return undefined;
    const keys = new Map(bound.map((one) => [one.key, one.response]));
    const pressed = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        nudge(MOVE_STEP);
        return;
      }
      if (event.key === "-" || event.key === "_") {
        event.preventDefault();
        nudge(-MOVE_STEP);
        return;
      }
      const response = keys.get(event.key.toLowerCase());
      if (response !== undefined) {
        event.preventDefault();
        answer(response);
      }
    };
    window.addEventListener("keydown", pressed);
    return () => window.removeEventListener("keydown", pressed);
  }, [bound, answer, busy, gated, nudge]);

  const foes = fight.began.combatants.filter((one) => one.side === "enemy");
  const enemies = foes.map((one) => one.name).join(", ");

  return (
    <section className="fight" aria-labelledby="fight-heading">
      <h2 id="fight-heading" className="fight-who">
        {enemies}
        {fight.responses.streak > 1 && (
          <span className="streak"> · {fight.responses.streak} read in a row</span>
        )}
      </h2>

      <ul className="combatants">
        {foes.map((one) => (
          <VitalBar
            key={one.actor}
            name={one.name}
            gauge={fight.vitals[one.actor] ?? one.vital}
            reads={one.reads}
          />
        ))}
      </ul>

      <p className="tell" aria-live="assertive">
        {fight.tell.text}
      </p>
      {fight.tell.type !== "" && <p className="tell-type">({fight.tell.type})</p>}

      {gated && (
        <div className="fight-gate">
          <p className="dim">
            Read the tell, then begin — the window opens on your mark. The
            answers below are already laid out so you can find them first.
          </p>
          <button type="button" className="primary" onClick={beginFight} autoFocus>
            Begin the fight
          </button>
        </div>
      )}

      {!gated && timed && (
        <TimingBar
          key={`${fight.tell.combat}-${fight.openedAt}`}
          windowMs={fight.tell.windowMs}
          startedAt={openedAt}
          onExpire={expire}
        />
      )}

      {/* Shown even while gated — disabled, not hidden — so a reader can
          find the keys and the layout with their hands before the window
          they'd be spending to do that starts (see the note beside `gated`
          above). `nudge` and `answer` already no-op while gated regardless;
          `disabled` here is what tells a reader that, rather than leaving a
          button that looks live but silently isn't. */}
      <RangeBar
        range={fight.responses.weaponRange}
        distance={Math.max(0, fight.tell.distance - moveBy)}
      />
      <div className="range-controls">
        <button
          type="button"
          className="answer-key range-step"
          disabled={busy || gated}
          onClick={() => nudge(-MOVE_STEP)}
          aria-label="open the distance"
        >
          −
        </button>
        <span>
          distance{" "}
          {Math.round(Math.max(0, fight.tell.distance - moveBy) * 10) / 10}ft
        </span>
        <button
          type="button"
          className="answer-key range-step"
          disabled={busy || gated}
          onClick={() => nudge(MOVE_STEP)}
          aria-label="close the distance"
        >
          +
        </button>
      </div>

      <ul className="answers">
        {bound.map((one) => (
          <li key={one.response}>
            <button
              type="button"
              className="answer"
              disabled={busy || gated}
              onClick={() => answer(one.response)}
            >
              <span className="answer-key" aria-hidden="true">
                {one.key}
              </span>
              {one.label}
            </button>
          </li>
        ))}
      </ul>

      <Resources
        stamina={fight.responses.stamina}
        of={staminaOf}
        momentum={fight.responses.momentum}
      />

      {fight.began.matrix.length > 0 && (
        <div className="matrix">
          <button
            type="button"
            className="matrix-toggle"
            aria-expanded={wheels}
            onClick={() => setWheels((on) => !on)}
          >
            {wheels ? "Hide what beats what" : "What beats what"}
          </button>
          {wheels && (
            <dl className="counters">
              {fight.began.matrix.map((row) => (
                <div key={row.type} className="counter">
                  <dt>{row.type}</dt>
                  <dd>{row.beatenBy.join(" or ") || "nothing you have"}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </section>
  );
}
