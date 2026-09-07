/**
 * One object as the engine will see it, beside the form that writes it.
 *
 * The gap a form cannot close on its own is `extends`: the file is **not** the
 * object. A troll that inherits from `fantasy.core:bridge-troll` and writes
 * only `strength: 85` has eighty hitpoints, a combat profile and a response to
 * the dark, and none of that appears anywhere the author can see. A
 * conditional description is the same problem the other way — three lines in a
 * file and one line in play.
 *
 * So this shows the compiled object, and marks what was inherited rather than
 * quietly presenting it as written. An author who cannot tell what they typed
 * from what they got is an author who will retype it.
 *
 * It refetches on every answer, which is what makes it live: the wizard
 * recompiles on demand and never touches the disk, so a preview of unsaved
 * work is true rather than approximately true.
 */

import { useEffect, useState } from "react";

import * as api from "./api";
import { StudioError } from "./api";
import type { Preview as Seen } from "./protocol";

export function Preview({
  collection,
  id,
  /** Bumped by the parent on every answer, to refetch. */
  version,
}: {
  collection: string;
  id: string;
  version: number;
}) {
  const [seen, setSeen] = useState<Seen | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void api
      .preview(collection, id)
      .then((found) => {
        if (live) {
          setSeen(found);
          setFailure(null);
        }
      })
      .catch((error: unknown) => {
        if (live) {
          setFailure(
            error instanceof StudioError ? error.message : "no preview",
          );
        }
      });
    return () => {
      live = false;
    };
  }, [collection, id, version]);

  if (failure !== null) return <p className="dim">{failure}</p>;
  if (seen === null) return null;

  return (
    <aside className="preview" aria-label={`${seen.name}, as the engine sees it`}>
      <h3>{seen.name}</h3>
      {seen.inherits === null ? null : (
        <p className="dim">
          inherits <code>{seen.inherits}</code>
        </p>
      )}

      {seen.built ? null : (
        <div className="preview-broken">
          <p>This will not build yet, so the rest of it cannot be shown.</p>
          <ul>
            {seen.why.map((one) => (
              <li key={one}>{one}</li>
            ))}
          </ul>
        </div>
      )}

      {seen.lines.length === 0 ? null : (
        <ul className="preview-lines">
          {seen.lines.map((line, index) => (
            <li key={`${line.text}-${index}`}>
              <span>{line.text}</span>
              {line.when === "always" ? null : (
                <span className="dim"> — when {line.when}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {seen.facts.length === 0 ? null : (
        <dl className="preview-facts">
          {seen.facts.map((fact) => (
            <div key={fact.label} className={fact.own ? "" : "preview-inherited"}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.value}
                {/* Said, not shaded: an author has to be able to tell what
                    they wrote from what they were given. */}
                {fact.own ? null : <span className="dim"> (inherited)</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {seen.stats.length === 0 ? null : (
        <dl className="preview-facts">
          {seen.stats.map((stat) => (
            <div key={stat.stat}>
              <dt>{stat.stat}</dt>
              <dd>
                {stat.base}
                {stat.max === null ? "" : ` / ${stat.max}`}
                {stat.customizable ? (
                  <span className="dim"> (the player may spend here)</span>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {seen.carries.length === 0 ? null : (
        <p className="dim">
          carries{" "}
          {seen.carries
            .map((one) => (one.qty === 1 ? one.name : `${one.qty} × ${one.name}`))
            .join(", ")}
        </p>
      )}
    </aside>
  );
}
