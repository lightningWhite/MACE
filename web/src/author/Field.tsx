/**
 * One step of a flow, drawn.
 *
 * A step is a title, some help, a control, and a line saying what the answer
 * currently reads as. Most of them hand straight off to `Control`. Four do
 * not, because they hold *several* of something and an author needs to see the
 * list and take one thing out of it: conditions, effects, repeats, and
 * statblocks. Those are the fields the terminal drives with a little loop of
 * its own, and this is that loop drawn instead of printed.
 *
 * The lists come down as `step.entries`, already rendered into English by the
 * wizard. A browser has no model and no naming service, so it must not be the
 * thing deciding what `{hasItem: {item: gold, qty: 10}}` says.
 */

import { useState } from "react";

import { Cascade } from "./Cascade";
import { Control } from "./Control";
import type { Allocated, Entry, Piece, Step, StepSpec } from "./protocol";

interface Props {
  step: Step;
  /** Called with the authored value. `null` clears the field. */
  onAnswer: (value: unknown) => void;
  busy: boolean;
}

/** One step's control, with its title, help, and current reading. */
export function Field({ step, onAnswer, busy }: Props) {
  return (
    <div className="field">
      <div className="field-head">
        <label className="field-title" htmlFor={`field-${step.id}`}>
          {step.title}
          {step.optional ? <span className="dim"> — optional</span> : null}
        </label>
        {step.help === "" ? null : <p className="field-help">{step.help}</p>}
      </div>
      <Body step={step} onAnswer={onAnswer} busy={busy} />
      <p className="field-reading">
        <span className="dim">now: </span>
        {step.described}
      </p>
    </div>
  );
}

function Body({ step, onAnswer, busy }: Props) {
  const id = `field-${step.id}`;

  switch (step.field.kind) {
    case "conditions":
    case "effects":
      return <Pieces step={step} onAnswer={onAnswer} busy={busy} />;
    case "repeat":
      return <Entries step={step} onAnswer={onAnswer} busy={busy} />;
    case "stat-allocator":
      return <Statblock step={step} onAnswer={onAnswer} busy={busy} />;
    default:
      return (
        <Control
          id={id}
          field={step.field}
          value={step.value}
          busy={busy}
          onChange={onAnswer}
        />
      );
  }
}

// ── Conditions and effects ───────────────────────────────────────────────────

/**
 * A list of built conditions or effects, and a way to add one.
 *
 * A `single` condition field holds one rather than a list — a description
 * line's `when` is one condition — so adding replaces rather than appends,
 * and the button says so.
 */
function Pieces({ step, onAnswer, busy }: Props) {
  const [building, setBuilding] = useState(false);
  const kind = step.field.kind === "conditions" ? "conditions" : "effects";
  const single = step.field.single === true;
  const held = (step.entries ?? []) as Piece[];

  const add = (authored: Record<string, unknown>) => {
    setBuilding(false);
    const next = [...held.map((one) => one.authored), authored];
    onAnswer(single ? authored : next);
  };

  const drop = (index: number) => {
    if (single) return onAnswer(null);
    const next = held.filter((_one, at) => at !== index).map((one) => one.authored);
    onAnswer(next.length === 0 ? null : next);
  };

  return (
    <div className="pieces">
      {held.length === 0 ? (
        <p className="dim">
          {kind === "conditions" ? "No conditions — always." : "Nothing happens."}
        </p>
      ) : (
        <ul className="piece-list">
          {held.map((one, index) => (
            <li key={`${one.said}-${index}`}>
              <span>{one.said}</span>
              <button
                type="button"
                className="piece-drop"
                disabled={busy}
                onClick={() => drop(index)}
                aria-label={`Remove ${one.said}`}
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {building ? (
        <Cascade kind={kind} onBuilt={add} onCancel={() => setBuilding(false)} />
      ) : (
        <button
          type="button"
          className="piece-add"
          disabled={busy}
          onClick={() => setBuilding(true)}
        >
          {single && held.length > 0
            ? `Change this ${kind === "conditions" ? "condition" : "effect"}`
            : `Add ${kind === "conditions" ? "a condition" : "an effect"}`}
        </button>
      )}
    </div>
  );
}

// ── Repeats ──────────────────────────────────────────────────────────────────

/** A list of sub-objects — exits, choices, stages — each with its own flow. */
function Entries({ step, onAnswer, busy }: Props) {
  const [adding, setAdding] = useState(false);
  const held = (step.entries ?? []) as Entry[];
  const noun = step.field.of ?? "entry";
  const steps = step.field.steps ?? [];

  const add = (values: Record<string, unknown>) => {
    setAdding(false);
    onAnswer([...held.map((one) => one.values), values]);
  };

  const drop = (index: number) => {
    const next = held.filter((_one, at) => at !== index).map((one) => one.values);
    onAnswer(next.length === 0 ? null : next);
  };

  return (
    <div className="pieces">
      {held.length === 0 ? (
        <p className="dim">No {noun}s yet.</p>
      ) : (
        <ul className="piece-list">
          {held.map((one, index) => (
            <li key={`${one.summary}-${index}`}>
              <span>{one.summary}</span>
              <button
                type="button"
                className="piece-drop"
                disabled={busy}
                onClick={() => drop(index)}
                aria-label={`Remove ${noun} ${index + 1}`}
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <EntryForm
          noun={noun}
          steps={steps}
          busy={busy}
          onDone={add}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <button
          type="button"
          className="piece-add"
          disabled={busy || steps.length === 0}
          onClick={() => setAdding(true)}
        >
          Add {noun === "entry" ? "an entry" : `a ${noun}`}
        </button>
      )}
    </div>
  );
}

/**
 * One repeat entry's own little flow.
 *
 * The entry is keyed by each sub-step's binding leaf, which is what the
 * terminal writes too — the sub-steps bind into the entry, not into the
 * object, so `locations[{id}].exits` gets `{to: castle, route: road}`.
 */
function EntryForm({
  noun,
  steps,
  busy,
  onDone,
  onCancel,
}: {
  noun: string;
  steps: StepSpec[];
  busy: boolean;
  onDone: (values: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const missing = steps.filter(
    (one) => !one.optional && !answered(values[leafOf(one.binds)]),
  );

  return (
    <div className="cascade">
      <p className="cascade-question">A new {noun}</p>
      {steps.map((one) => (
        <div className="field" key={one.id}>
          <label className="field-title" htmlFor={`entry-${one.id}`}>
            {one.title}
            {one.optional ? <span className="dim"> — optional</span> : null}
          </label>
          {one.help === "" ? null : <p className="field-help">{one.help}</p>}
          <Control
            id={`entry-${one.id}`}
            field={one.field}
            value={values[leafOf(one.binds)] ?? null}
            busy={busy}
            onChange={(value) =>
              setValues((current) => ({ ...current, [leafOf(one.binds)]: value }))
            }
          />
        </div>
      ))}
      <div className="cascade-actions">
        <button
          type="button"
          disabled={busy || missing.length > 0}
          onClick={() => onDone(strip(values))}
        >
          Add it
        </button>
        <button type="button" className="cascade-cancel" onClick={onCancel}>
          never mind
        </button>
        {missing.length === 0 ? null : (
          <span className="dim">still needs {missing[0]?.title.toLowerCase()}</span>
        )}
      </div>
    </div>
  );
}

// ── Statblocks ───────────────────────────────────────────────────────────────

/**
 * Named numbers, against a budget where there is one.
 *
 * Genre-neutral, like the field: `stats` is a list of suggestions drawn from
 * what the pack already uses, and an author is free to invent
 * `hull-integrity` beside them.
 */
function Statblock({ step, onAnswer, busy }: Props) {
  const held = (step.entries ?? []) as Allocated[];
  const [naming, setNaming] = useState("");
  const points = step.field.points ?? 0;
  const spent = held.reduce((total, one) => total + one.base, 0);
  const suggested = (step.field.stats ?? []).filter(
    (one) => !held.some((had) => had.stat === one),
  );

  const write = (next: Allocated[]) => {
    if (next.length === 0) return onAnswer(null);
    onAnswer(
      Object.fromEntries(
        next.map((one) => [
          one.stat,
          one.max === null ? { base: one.base } : { base: one.base, max: one.max },
        ]),
      ),
    );
  };

  const change = (stat: string, key: "base" | "max", value: number | null) => {
    write(
      held.map((one) =>
        one.stat === stat
          ? { ...one, [key]: key === "base" ? (value ?? 0) : value }
          : one,
      ),
    );
  };

  return (
    <div className="pieces">
      {points === 0 ? null : (
        <p className="dim">
          {spent} of {points} points spent.
        </p>
      )}
      {held.length === 0 ? <p className="dim">No stats yet.</p> : null}
      <ul className="statblock">
        {held.map((one) => (
          <li key={one.stat}>
            <span className="statblock-name">{one.stat}</span>
            <input
              className="field-input field-number"
              type="number"
              aria-label={`${one.stat} base`}
              value={one.base}
              disabled={busy}
              onChange={(event) =>
                change(one.stat, "base", Number(event.target.value))
              }
            />
            <span className="dim">/</span>
            <input
              className="field-input field-number"
              type="number"
              aria-label={`${one.stat} cap`}
              placeholder="cap"
              value={one.max ?? ""}
              disabled={busy}
              onChange={(event) =>
                change(
                  one.stat,
                  "max",
                  event.target.value === "" ? null : Number(event.target.value),
                )
              }
            />
            <button
              type="button"
              className="piece-drop"
              disabled={busy}
              onClick={() => write(held.filter((had) => had.stat !== one.stat))}
              aria-label={`Remove ${one.stat}`}
            >
              remove
            </button>
          </li>
        ))}
      </ul>

      <form
        className="make"
        onSubmit={(event) => {
          event.preventDefault();
          const name = naming.trim();
          if (name === "" || held.some((one) => one.stat === name)) return;
          write([...held, { stat: name, base: 0, max: null }]);
          setNaming("");
        }}
      >
        <input
          className="field-input"
          value={naming}
          list={`stats-${step.id}`}
          placeholder="strength"
          aria-label="Which stat?"
          disabled={busy}
          onChange={(event) => setNaming(event.target.value)}
        />
        <datalist id={`stats-${step.id}`}>
          {suggested.map((one) => (
            <option key={one} value={one} />
          ))}
        </datalist>
        <button type="submit" disabled={busy || naming.trim() === ""}>
          Add a stat
        </button>
      </form>
    </div>
  );
}

/** The field name a sub-step binds to — the last segment of its binding. */
function leafOf(binds: string): string {
  const parts = binds.split(".");
  return parts[parts.length - 1] ?? binds;
}

function answered(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" || Array.isArray(value)) return value.length > 0;
  return true;
}

/** Drop the questions the author left blank, so the file holds only answers. */
function strip(values: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => answered(value)),
  );
}
