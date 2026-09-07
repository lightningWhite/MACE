/**
 * Start me at the Troll Bridge, at midnight, in a blizzard.
 *
 * The single most important thing for keeping an author going, and the one
 * the v0 wizard could not offer at all: nothing was playable until everything
 * was done. Here the pack is played **as it stands** — unsaved changes and
 * all — because the wizard compiles in memory and never needs the disk.
 *
 * Every field on this form is a session-opening parameter, the way the seed
 * is, so what it opens is an ordinary playthrough rather than a special mode.
 * That is why it hands off: the answer is a session id, and the *game* client
 * plays it, in a tab of its own so the wizard stays where the author left it.
 *
 * The pickers arrive resolved, like every other picker in the studio. A
 * browser cannot ask the catalog where the bridge is in the middle of drawing
 * a form.
 */

import { useEffect, useState } from "react";

import * as api from "./api";
import { StudioError } from "./api";
import type { Option, Rehearsal, Setup } from "./protocol";

/** Where the game client picks a playtest up. See `web/src/main.tsx`. */
export function playing(session: string): string {
  return `${import.meta.env.BASE_URL}#play/${encodeURIComponent(session)}`;
}

export function Playtest({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState<Rehearsal | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api
      .rehearsal()
      .then((offered) => {
        setForm(offered);
        setSetup(offered.setup);
      })
      .catch((error: unknown) => {
        setFailure(
          error instanceof StudioError ? error.message : "no playtest form",
        );
      });
  }, []);

  if (failure !== null && form === null) {
    return <p className="studio-failure">{failure}</p>;
  }
  if (form === null || setup === null) {
    return <p className="dim">Working out where you could start…</p>;
  }

  const change = (fields: Partial<Setup>) =>
    setSetup({ ...setup, ...fields });

  function play() {
    if (setup === null) return;
    setBusy(true);
    setFailure(null);
    api
      .playtest(setup)
      .then((opened) => {
        // A tab of its own. The wizard holds the project in memory on the
        // server, so navigating away would not lose an author's work — but it
        // would lose the screen they were on, and playtesting is something
        // you do *beside* the thing you are editing.
        window.open(playing(opened.session), "_blank", "noopener");
        onClose();
      })
      .catch((error: unknown) => {
        setFailure(
          error instanceof StudioError ? error.message : "it would not start",
        );
      })
      .finally(() => setBusy(false));
  }

  return (
    <section className="playtest" aria-label="Playtest">
      <h2>Playtest</h2>
      <p className="dim">
        The pack as it stands, unsaved changes and all. It opens in a tab of
        its own.
      </p>

      <div className="playtest-fields">
        <label>
          Seed
          <input
            type="text"
            value={setup.seed}
            onChange={(event) => change({ seed: event.target.value })}
          />
        </label>

        <label>
          Start where
          <Picker
            options={form.locations}
            value={setup.startLocation}
            fallback="wherever the game starts"
            onPick={(value) => change({ startLocation: value })}
          />
        </label>

        <label>
          At what tick
          <input
            type="number"
            min={0}
            value={setup.startTick ?? ""}
            placeholder="when the game starts"
            onChange={(event) =>
              change({
                startTick:
                  event.target.value === ""
                    ? null
                    : Number(event.target.value),
              })
            }
          />
        </label>

        <label>
          In what weather
          <Picker
            options={form.weather}
            value={setup.weather}
            fallback="whatever the climate rolls"
            onPick={(value) => change({ weather: value })}
          />
        </label>
      </div>

      <Kit
        options={form.items}
        carried={setup.items}
        onChange={(items) => change({ items })}
      />

      {failure === null ? null : (
        <p className="studio-failure" role="alert">
          {failure}
        </p>
      )}

      <div className="playtest-buttons">
        <button type="button" disabled={busy} onClick={play}>
          Play it
        </button>
        <button type="button" className="quiet" onClick={onClose}>
          Not now
        </button>
      </div>
    </section>
  );
}

/** One picker, with "leave it to the game" as a real answer rather than a blank. */
function Picker({
  options,
  value,
  fallback,
  onPick,
}: {
  options: Option[];
  value: string | null;
  fallback: string;
  onPick: (value: string | null) => void;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(event) => onPick(event.target.value === "" ? null : event.target.value)}
    >
      <option value="">{fallback}</option>
      {options.map((one) => (
        <option key={one.value} value={one.value}>
          {one.label}
          {one.note === "this pack" ? "" : ` (${one.note})`}
        </option>
      ))}
    </select>
  );
}

/**
 * What to start with in your pockets.
 *
 * "With a magic sword" is half of every awkward corner worth testing, and
 * walking to where the sword is first is how people stop testing it.
 */
function Kit({
  options,
  carried,
  onChange,
}: {
  options: Option[];
  carried: Record<string, number>;
  onChange: (items: Record<string, number>) => void;
}) {
  if (options.length === 0) return null;
  return (
    <fieldset className="playtest-kit">
      <legend>Starting with</legend>
      {options.map((one) => (
        <label key={one.value}>
          <input
            type="checkbox"
            checked={(carried[one.value] ?? 0) > 0}
            onChange={(event) => {
              const next = { ...carried };
              if (event.target.checked) next[one.value] = 1;
              else delete next[one.value];
              onChange(next);
            }}
          />
          {one.label}
        </label>
      ))}
    </fieldset>
  );
}
