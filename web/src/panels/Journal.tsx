/**
 * The journal: what the player is trying to do.
 *
 * Hidden quests are absent from the projection, so there is nothing here to
 * grey out. A greyed line saying `??? — hidden` is most of the secret.
 */

import type { Entry } from "../protocol";

export function Journal({ journal }: { journal: Entry[] }) {
  return (
    <section className="panel" aria-labelledby="journal-heading">
      <h2 id="journal-heading">Journal</h2>
      {journal.length === 0 ? (
        <p className="empty">Nothing is asked of you yet.</p>
      ) : (
        <ul className="quests">
          {journal.map((entry) => (
            <li key={entry.quest} className={`quest quest-${entry.status}`}>
              <p className="quest-name">
                {entry.name}
                {entry.status !== "active" && (
                  <span className="dim"> — {entry.status}</span>
                )}
              </p>
              {entry.journal !== null && (
                <p className="quest-stage">{entry.journal}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
