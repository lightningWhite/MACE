/**
 * Which game to author, before there is a task list to show.
 *
 * `mace dev` opens with nothing picked — which game to work on is a browser
 * decision now, not a command-line argument. This is that choice: every
 * authorable game pack, plus a form for a new one, drawn with the same list
 * styling the play side's own chooser uses (`../panels/Opening.tsx`), since
 * it is the same kind of decision for a different purpose.
 */

import { useEffect, useState } from "react";

import * as api from "./api";
import { StudioError } from "./api";
import type { AuthorableGame, Frame } from "./protocol";

export function GamePicker({
  onOpened,
  onCancel,
}: {
  /** Called once a pack is open, with its first frame. */
  onOpened: (frame: Frame) => void;
  /** Omitted when there is nothing to go back to yet — the very first pack. */
  onCancel?: () => void;
}) {
  const [games, setGames] = useState<AuthorableGame[] | null>(null);
  const [libraries, setLibraries] = useState<AuthorableGame[]>([]);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void api
      .games()
      .then(({ games: found }) => setGames(found))
      .catch((error: unknown) =>
        setFailure(
          error instanceof StudioError ? error.message : "could not list games",
        ),
      );
    // A missing dependency directory just means a new game has nothing to
    // depend on — not fatal to the rest of the picker.
    void api
      .libraries()
      .then(({ libraries: found }) => setLibraries(found))
      .catch(() => undefined);
  }, []);

  function settle(reply: Promise<Frame>): void {
    setBusy(true);
    setFailure(null);
    reply
      .then(onOpened)
      .catch((error: unknown) =>
        setFailure(error instanceof StudioError ? error.message : "that did not work"),
      )
      .finally(() => setBusy(false));
  }

  return (
    <main className="studio">
      <h1>Which game?</h1>
      {failure === null ? null : (
        <p className="studio-failure" role="alert">
          {failure}
        </p>
      )}

      {games === null ? (
        <p className="empty">Looking…</p>
      ) : games.length === 0 ? (
        <p className="empty">Nothing here yet — start the first one below.</p>
      ) : (
        <ul className="games">
          {games.map((game) => (
            <li key={game.id}>
              <button
                type="button"
                className="game"
                disabled={busy}
                onClick={() => settle(api.openGame(game.id))}
              >
                <span className="game-name">{game.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {creating ? (
        <NewGame
          libraries={libraries}
          busy={busy}
          onCreate={(name, requires) => settle(api.newGame(name, requires))}
          onCancel={() => setCreating(false)}
        />
      ) : (
        <button type="button" disabled={busy} onClick={() => setCreating(true)}>
          + start a new game
        </button>
      )}

      {onCancel === undefined ? null : (
        <button type="button" disabled={busy} onClick={onCancel}>
          Never mind
        </button>
      )}
    </main>
  );
}

function NewGame({
  libraries,
  busy,
  onCreate,
  onCancel,
}: {
  libraries: AuthorableGame[];
  busy: boolean;
  onCreate: (name: string, requires: Record<string, string>) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  return (
    <form
      className="make"
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = name.trim();
        if (trimmed === "") return;
        const requires: Record<string, string> = {};
        for (const id of picked) requires[id] = "^0.1";
        onCreate(trimmed, requires);
      }}
    >
      <label>
        Its name
        <input
          className="field-input"
          value={name}
          disabled={busy}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      {libraries.length === 0 ? null : (
        <fieldset>
          <legend>What does it build on?</legend>
          {libraries.map((library) => (
            <label key={library.id} className="field-check">
              <input
                type="checkbox"
                checked={picked.includes(library.id)}
                disabled={busy}
                onChange={() =>
                  setPicked((current) =>
                    current.includes(library.id)
                      ? current.filter((one) => one !== library.id)
                      : [...current, library.id],
                  )
                }
              />
              <span>{library.name}</span>
            </label>
          ))}
        </fieldset>
      )}

      <button type="submit" disabled={busy || name.trim() === ""}>
        Create
      </button>
      <button type="button" disabled={busy} onClick={onCancel}>
        Never mind
      </button>
    </form>
  );
}
