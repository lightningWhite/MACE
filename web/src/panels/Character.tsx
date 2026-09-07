/**
 * The character panel: who you are and what is left of you.
 *
 * Which stats are pools and which are abilities is the game's decision, not
 * this component's — `role` comes from the projection, which reads it from
 * the game's rules. A client that hard-coded "hitpoints goes beside a heart"
 * would be a client that only works for fantasy games.
 */

import type { Gauge, Sheet } from "../protocol";

function Pool({ gauge }: { gauge: Gauge }) {
  const cap = gauge.maximum ?? gauge.value;
  const filled = cap > 0 ? Math.max(0, Math.min(1, gauge.value / cap)) : 0;
  return (
    <div className="pool">
      <div className="pool-label">
        <span>{gauge.stat}</span>
        <span className="pool-count">
          {Math.round(gauge.value)}
          <span className="dim">/{Math.round(cap)}</span>
        </span>
      </div>
      <div
        className={`bar bar-${gauge.role}`}
        role="meter"
        aria-label={gauge.stat}
        aria-valuenow={Math.round(gauge.value)}
        aria-valuemin={0}
        aria-valuemax={Math.round(cap)}
      >
        <div className="bar-fill" style={{ inlineSize: `${filled * 100}%` }} />
      </div>
    </div>
  );
}

/**
 * How much the weather has taken out of the player.
 *
 * The projection carries a number and says the player should never see it,
 * so this is where the number becomes a word.
 */
function exposureReads(exposure: number): string | null {
  if (exposure < 0.15) return null;
  if (exposure < 0.4) return "chilled";
  if (exposure < 0.7) return "soaked through";
  return "in a bad way";
}

export function Character({ sheet }: { sheet: Sheet }) {
  const pools = sheet.stats.filter((gauge) => gauge.role !== "ability");
  const abilities = sheet.stats.filter((gauge) => gauge.role === "ability");
  const exposure = exposureReads(sheet.exposure);

  return (
    <section className="panel" aria-labelledby="character-heading">
      <h2 id="character-heading">{sheet.name}</h2>
      {pools.map((gauge) => (
        <Pool key={gauge.stat} gauge={gauge} />
      ))}
      <dl className="abilities">
        {abilities.map((gauge) => (
          <div key={gauge.stat} className="ability">
            <dt>{gauge.stat.slice(0, 3)}</dt>
            <dd>{Math.round(gauge.value)}</dd>
          </div>
        ))}
      </dl>
      {exposure !== null && <p className="exposure">You are {exposure}.</p>}
    </section>
  );
}
