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

import type { Action, CombatBegan, CombatTell, ResponsesOffered } from "../protocol";
import { keysFor } from "./keys";
import { TimingBar } from "./TimingBar";

export interface Fight {
  began: CombatBegan;
  tell: CombatTell;
  responses: ResponsesOffered;
  /** `performance.now()` when this tell arrived. */
  openedAt: number;
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

  const answer = useCallback(
    (response: string) => {
      if (busy) return;
      onAnswer(
        timed
          ? {
              kind: "combat.input",
              response,
              elapsedMs: Math.round(performance.now() - fight.openedAt),
            }
          : { kind: "combat.input", response },
      );
    },
    [busy, onAnswer, timed, fight.openedAt],
  );

  // The window ran out. `recover` is the answer that takes the blow on
  // purpose, and the engine is told exactly how much of the window went by.
  const expire = useCallback(() => {
    if (busy) return;
    onAnswer({
      kind: "combat.input",
      response: "recover",
      elapsedMs: fight.tell.windowMs,
    });
  }, [busy, onAnswer, fight.tell.windowMs]);

  // A fight is played with the hands on the keys, and on the same keys the
  // terminal binds: a player should not have to learn them twice.
  const bound = keysFor(fight.responses.options);

  useEffect(() => {
    if (busy) return undefined;
    const keys = new Map(bound.map((one) => [one.key, one.response]));
    const pressed = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const response = keys.get(event.key.toLowerCase());
      if (response !== undefined) {
        event.preventDefault();
        answer(response);
      }
    };
    window.addEventListener("keydown", pressed);
    return () => window.removeEventListener("keydown", pressed);
  }, [bound, answer, busy]);

  const enemies = fight.began.combatants
    .filter((one) => one.side === "enemy")
    .map((one) => one.name)
    .join(", ");

  return (
    <section className="fight" aria-labelledby="fight-heading">
      <h2 id="fight-heading" className="fight-who">
        {enemies}
        {fight.responses.streak > 1 && (
          <span className="streak"> · {fight.responses.streak} read in a row</span>
        )}
      </h2>

      <p className="tell" aria-live="assertive">
        {fight.tell.text}
      </p>
      {fight.tell.type !== "" && <p className="tell-type">({fight.tell.type})</p>}

      {timed && (
        <TimingBar
          key={`${fight.tell.combat}-${fight.openedAt}`}
          windowMs={fight.tell.windowMs}
          startedAt={fight.openedAt}
          onExpire={expire}
        />
      )}

      <ul className="answers">
        {bound.map((one) => (
          <li key={one.response}>
            <button
              type="button"
              className="answer"
              disabled={busy}
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
