/**
 * The wizard, in a browser.
 *
 * Three screens, and you can leave any of them — the same three the terminal
 * walks, because they come from the same projection:
 *
 *     the task list  →  a section  →  one object
 *
 * There is no model of the pack here. Every screen is `frame.screen`, which
 * the studio projected, and the header is `frame.desk`, which it recomputed.
 * The one thing this file decides is what to do when the wizard says no.
 *
 * Nothing blocks. A section can be left half-done, an object can be left with
 * one answer in it, and saving is explicit and always allowed — an author has
 * to be able to stop mid-thought.
 */

import { useCallback, useEffect, useState } from "react";

import * as api from "./api";
import { StudioError } from "./api";
import { Field } from "./Field";
import { MapEditor } from "./MapEditor";
import { SceneGraph } from "./SceneGraph";
import {
  isObject,
  isSection,
  type Frame,
  type ObjectScreen,
  type Problem,
  type SectionScreen,
  type Task,
} from "./protocol";

/** Which screen the client is showing, and what it takes to fetch it again. */
type Where =
  | { at: "desk" }
  | { at: "section"; section: string }
  | { at: "object"; collection: string; id: string | null; section: string | null };

const MARKS: Record<string, string> = {
  empty: "○",
  started: "◐",
  done: "✓",
};

export function Studio() {
  const [frame, setFrame] = useState<Frame | null>(null);
  const [where, setWhere] = useState<Where>({ at: "desk" });
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string[] | null>(null);

  /**
   * Run one call and take in what came back.
   *
   * Every reply carries the desk, so the header is never stale and no screen
   * has to remember to refresh it. A refusal leaves the screen exactly where
   * it was: being told a name is taken should not lose the form.
   */
  const run = useCallback(
    async (call: () => Promise<Frame>, next?: Where) => {
      setBusy(true);
      setFailure(null);
      try {
        const answered = await call();
        setFrame(answered);
        if (next !== undefined) setWhere(next);
      } catch (error) {
        setFailure(
          error instanceof StudioError ? error.message : "something went wrong",
        );
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  useEffect(() => {
    void run(api.desk);
  }, [run]);

  if (frame === null) {
    return (
      <main className="studio">
        <p className="empty">{failure ?? "Opening the pack…"}</p>
      </main>
    );
  }

  const screen = frame.screen;

  return (
    <main className="studio">
      <Header
        frame={frame}
        busy={busy}
        onSave={() =>
          void run(async () => {
            const done = await api.save();
            setSaved(
              isSaved(done) ? done.screen.saved : [],
            );
            return done;
          })
        }
      />

      {failure === null ? null : (
        <p className="studio-failure" role="alert">
          {failure}
        </p>
      )}
      {frame.unreadable.length === 0 ? null : (
        <ul className="studio-unreadable" role="status">
          {frame.unreadable.map((one) => (
            <li key={one}>{one}</li>
          ))}
        </ul>
      )}
      {saved === null ? null : (
        <p className="studio-saved" role="status">
          {saved.length === 0
            ? "Nothing had changed."
            : `Saved ${saved.join(", ")}.`}
        </p>
      )}

      {where.at !== "desk" ? (
        <button
          type="button"
          className="studio-back"
          onClick={() =>
            void (where.at === "object" && where.section !== null
              ? run(() => api.section(where.section as string), {
                  at: "section",
                  section: where.section as string,
                })
              : run(api.desk, { at: "desk" }))
          }
        >
          ← back
        </button>
      ) : null}

      {where.at === "desk" ? (
        <Desk
          tasks={frame.desk.tasks}
          onOpen={(task) => {
            if (task.section === "game") {
              void run(() => api.object("game"), {
                at: "object",
                collection: "game",
                id: null,
                section: null,
              });
              return;
            }
            void run(() => api.section(task.section), {
              at: "section",
              section: task.section,
            });
          }}
        />
      ) : null}

      {isSection(screen) ? (
        <Section
          screen={screen}
          busy={busy}
          onRefresh={() => void run(() => api.section(screen.section))}
          onOpen={(collection, id) =>
            void run(() => api.object(collection, id), {
              at: "object",
              collection,
              id,
              section: screen.section,
            })
          }
          onCreate={(collection, name) =>
            void run(() => api.create(collection, name, screen.section), {
              at: "object",
              collection,
              id: null,
              section: screen.section,
            })
          }
          onDelete={(collection, id) =>
            void run(async () => {
              await api.remove(collection, id);
              return api.section(screen.section);
            })
          }
        />
      ) : null}

      {isObject(screen) ? (
        <ObjectForm
          screen={screen}
          busy={busy}
          onAnswer={(step, value) =>
            void run(async () => {
              await api.answer(screen.collection, step, value, screen.id);
              return api.object(screen.collection, screen.id);
            })
          }
        />
      ) : null}
    </main>
  );
}

function Header({
  frame,
  busy,
  onSave,
}: {
  frame: Frame;
  busy: boolean;
  onSave: () => void;
}) {
  const { desk, dirty } = frame;
  return (
    <header className="studio-head">
      <div>
        <h1>{desk.name}</h1>
        <p className="dim">
          {desk.percent}% complete ·{" "}
          {desk.problems === 0
            ? "no problems"
            : `${desk.problems} problem${desk.problems === 1 ? "" : "s"}`}
          {desk.errors === 0 ? "" : `, ${desk.errors} of them errors`}
          {dirty.length === 0 ? "" : ` · unsaved: ${dirty.join(", ")}`}
        </p>
      </div>
      <button type="button" className="studio-save" disabled={busy} onClick={onSave}>
        Save
      </button>
    </header>
  );
}

function Desk({
  tasks,
  onOpen,
}: {
  tasks: Task[];
  onOpen: (task: Task) => void;
}) {
  return (
    <ul className="task-list">
      {tasks.map((task) => (
        <li key={task.section}>
          <button
            type="button"
            className="task"
            onClick={() => onOpen(task)}
            aria-label={`${task.title} — ${task.state}`}
          >
            {/* The mark and the word both, because nothing is carried by a
                glyph alone any more than by a colour. */}
            <span className="task-mark" aria-hidden="true">
              {MARKS[task.state] ?? "·"}
            </span>
            <span className="task-title">{task.title}</span>
            <span className="task-summary dim">{task.summary}</span>
            <span className="task-note">{task.note}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Section({
  screen,
  busy,
  onOpen,
  onCreate,
  onDelete,
  onRefresh,
}: {
  screen: SectionScreen;
  busy: boolean;
  onOpen: (collection: string, id: string) => void;
  onCreate: (collection: string, name: string) => void;
  onDelete: (collection: string, id: string) => void;
  onRefresh: () => void;
}) {
  const [naming, setNaming] = useState("");
  const [making, setMaking] = useState(screen.creates[0] ?? "");

  return (
    <section className="studio-section">
      <h2>{screen.title}</h2>
      <p className="dim">{screen.help}</p>

      {/* The world map is the one section a browser can do something with
          that a terminal cannot, so it gets the thing a browser is for. The
          list below it stays: dragging is a way to place a location, not a
          way to write everything else about one. */}
      {/* The two screens a browser draws that a terminal cannot. Neither
          replaces the list under it: they are ways *in*, and a graph that
          were the only way to reach a scene would be worse than the list. */}
      {screen.section === "scenes" ? (
        <SceneGraph onOpen={(id) => onOpen("scenes", id)} />
      ) : null}
      {screen.section === "world" ? (
        <MapEditor
          busy={busy}
          onChanged={onRefresh}
          onOpen={(id) =>
            onOpen(
              screen.objects.find((one) => one.id === id)?.collection ??
                "locations",
              id,
            )
          }
        />
      ) : null}

      {screen.objects.length === 0 ? (
        <p className="empty">Nothing here yet.</p>
      ) : (
        <ul className="object-list">
          {screen.objects.map((one) => (
            <li key={`${one.collection}/${one.id}`}>
              <button
                type="button"
                className="object"
                aria-label={`Open ${one.label}`}
                onClick={() => onOpen(one.collection, one.id)}
              >
                <span className="object-label">{one.label}</span>
                <span className="dim">{one.id}</span>
                {one.unfinished ? (
                  <span className="object-unfinished">unfinished</span>
                ) : null}
              </button>
              <button
                type="button"
                className="object-delete"
                disabled={busy}
                onClick={() => onDelete(one.collection, one.id)}
                aria-label={`Delete ${one.label}`}
              >
                delete
              </button>
            </li>
          ))}
        </ul>
      )}

      {screen.creates.length === 0 ? (
        <p className="dim">This one is hand-written for now — no flow yet.</p>
      ) : (
        <form
          className="make"
          onSubmit={(event) => {
            event.preventDefault();
            if (naming.trim() === "") return;
            onCreate(making, naming.trim());
            setNaming("");
          }}
        >
          {screen.creates.length > 1 ? (
            <select
              className="field-input"
              value={making}
              aria-label="What kind?"
              onChange={(event) => setMaking(event.target.value)}
            >
              {screen.creates.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          ) : null}
          <input
            className="field-input"
            value={naming}
            placeholder="What is the new one called?"
            aria-label="What is the new one called?"
            disabled={busy}
            onChange={(event) => setNaming(event.target.value)}
          />
          <button type="submit" disabled={busy || naming.trim() === ""}>
            Make it
          </button>
        </form>
      )}

      <Problems problems={screen.problems} />
    </section>
  );
}

function ObjectForm({
  screen,
  busy,
  onAnswer,
}: {
  screen: ObjectScreen;
  busy: boolean;
  onAnswer: (step: string, value: unknown) => void;
}) {
  return (
    <section className="studio-object">
      <h2>{screen.label}</h2>
      {screen.id === null ? null : <p className="dim">{screen.id}</p>}
      <div className="fields">
        {screen.steps.map((step) => (
          <Field
            key={step.id}
            step={step}
            busy={busy}
            onAnswer={(value) => onAnswer(step.id, value)}
          />
        ))}
      </div>
    </section>
  );
}

function Problems({ problems }: { problems: Problem[] }) {
  if (problems.length === 0) return null;
  return (
    <ul className="problems">
      {problems.map((one, index) => (
        <li key={`${one.severity}-${index}`} className={`problem-${one.severity}`}>
          <span className="problem-severity">{one.severity}</span>
          <span>{one.message}</span>
          {one.object === null ? null : <span className="dim"> — {one.object}</span>}
        </li>
      ))}
    </ul>
  );
}

/** Narrower than the protocol's guard: it reads the whole frame, not a screen. */
function isSaved(frame: Frame): frame is Frame & { screen: { saved: string[] } } {
  return frame.screen !== null && "saved" in frame.screen;
}
