/**
 * Before the first tick: which game, and who you are in it.
 *
 * The question is not built here. `GET /api/games/{pack}/creation` returns a
 * projection with the backgrounds already phrased in English — "strength +8",
 * "2 × bread" — because only the engine knows what a background grants, and a
 * client that spelled it out itself would be reading content and would drift
 * from the terminal's wording. This renders that projection and hands back a
 * `{background, spend}`.
 *
 * The offer is asked for again whenever the background changes, so the points
 * are spent against the numbers the player will actually start with. A poacher
 * deciding where his last five points go should be looking at his stealth.
 */

import { useEffect, useState } from "react";

import { creationFor, listGames } from "../api";
import type { CreationOffer, GameSummary, Made, SaveRecord } from "../protocol";
import { PRESSURES } from "../protocol";

export function Opening({
  saved,
  onBegin,
  onResume,
  onForget,
  failure,
}: {
  saved: SaveRecord | null;
  onBegin: (
    pack: string,
    character: Made | null,
    timePressure: number,
  ) => void;
  onResume: (save: SaveRecord) => void;
  onForget: () => void;
  failure: string | null;
}) {
  const [games, setGames] = useState<GameSummary[] | null>(null);
  const [pack, setPack] = useState<string | null>(null);
  const [offer, setOffer] = useState<CreationOffer | null>(null);
  const [background, setBackground] = useState<string | null>(null);
  const [spend, setSpend] = useState<Record<string, number>>({});
  const [pressure, setPressure] = useState(1);
  const [trouble, setTrouble] = useState<string | null>(null);

  useEffect(() => {
    listGames()
      .then(({ games: found }) => {
        setGames(found);
        if (found.length === 1 && found[0] !== undefined) setPack(found[0].id);
      })
      .catch((error: Error) => setTrouble(error.message));
  }, []);

  useEffect(() => {
    if (pack === null) return;
    setSpend({});
    creationFor(pack, background ?? undefined)
      .then(setOffer)
      .catch((error: Error) => setTrouble(error.message));
  }, [pack, background]);

  const spent = Object.values(spend).reduce((total, points) => total + points, 0);
  const left = (offer?.points ?? 0) - spent;

  function move(stat: string, by: number, room: number): void {
    setSpend((current) => {
      const now = (current[stat] ?? 0) + by;
      if (now < 0 || now > room || (by > 0 && left <= 0)) return current;
      return { ...current, [stat]: now };
    });
  }

  function begin(): void {
    if (pack === null) return;
    const asked = offer?.asksAnything ?? false;
    onBegin(pack, asked ? { background, spend } : null, pressure);
  }

  const chooser = games !== null && games.length > 1;
  const ready =
    pack !== null &&
    offer !== null &&
    (!offer.asksAnything || offer.backgrounds.length === 0 || background !== null);

  return (
    <main className="opening">
      <h1>MACE</h1>

      {trouble !== null && <p className="trouble">{trouble}</p>}
      {failure !== null && <p className="trouble">{failure}</p>}

      {saved !== null && (
        <section className="resume">
          <p>
            You left a playthrough of <strong>{saved.pack}</strong> after{" "}
            {saved.actions.length}{" "}
            {saved.actions.length === 1 ? "action" : "actions"}.
          </p>
          <div className="row">
            <button type="button" className="primary" onClick={() => onResume(saved)}>
              Carry on
            </button>
            <button type="button" onClick={onForget}>
              Start again
            </button>
          </div>
        </section>
      )}

      {games === null && trouble === null && <p className="empty">Looking…</p>}

      {chooser && (
        <section>
          <h2>Choose a world</h2>
          <ul className="games">
            {games.map((game) => (
              <li key={game.id}>
                <button
                  type="button"
                  className={game.id === pack ? "game chosen" : "game"}
                  aria-pressed={game.id === pack}
                  onClick={() => {
                    setPack(game.id);
                    setBackground(null);
                  }}
                >
                  <span className="game-name">{game.name}</span>
                  {game.description !== null && (
                    <span className="game-blurb">{game.description}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {offer?.asksAnything === true && (
        <>
          {offer.backgrounds.length > 0 && (
            <section>
              <h2>Who are you?</h2>
              <ul className="backgrounds">
                {offer.backgrounds.map((one) => (
                  <li key={one.id}>
                    <button
                      type="button"
                      className={one.id === background ? "game chosen" : "game"}
                      aria-pressed={one.id === background}
                      onClick={() => setBackground(one.id)}
                    >
                      <span className="game-name">{one.name}</span>
                      <span className="game-blurb">{one.description}</span>
                      <span className="grants">{one.grants.join(" · ")}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {offer.points > 0 && offer.stats.length > 0 && (
            <section>
              <h2>
                Spend your points <span className="dim">{left} left</span>
              </h2>
              <ul className="spend">
                {offer.stats.map((stat) => {
                  const put = spend[stat.stat] ?? 0;
                  return (
                    <li key={stat.stat}>
                      <span className="spend-name">{stat.stat}</span>
                      <span className="spend-value">
                        {Math.round(stat.base) + put}
                        {put > 0 && <span className="dim"> (+{put})</span>}
                      </span>
                      <span className="row">
                        <button
                          type="button"
                          aria-label={`less ${stat.stat}`}
                          disabled={put === 0}
                          onClick={() => move(stat.stat, -1, stat.room)}
                        >
                          −
                        </button>
                        <button
                          type="button"
                          aria-label={`more ${stat.stat}`}
                          disabled={left <= 0 || put >= stat.room}
                          onClick={() => move(stat.stat, +1, stat.room)}
                        >
                          +
                        </button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </>
      )}

      <section>
        <h2>The clock</h2>
        <p className="dim aside">
          Fights telegraph, and you answer inside a window. This sets how long
          that window is — it changes nothing else about the fight.
        </p>
        <ul className="pressures">
          {PRESSURES.map((option) => (
            <li key={option.value}>
              <button
                type="button"
                className={option.value === pressure ? "game chosen" : "game"}
                aria-pressed={option.value === pressure}
                onClick={() => setPressure(option.value)}
              >
                <span className="game-name">{option.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <button type="button" className="primary begin" disabled={!ready} onClick={begin}>
        Begin
      </button>
    </main>
  );
}
