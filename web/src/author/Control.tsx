/**
 * One field type, drawn as a control. Value in, value out.
 *
 * Deliberately unaware of steps, so the same controls serve a step on an
 * object and a question inside the cascade — an author picking an item for
 * `hasItem` should be picking from the same list, in the same widget, as an
 * author picking one for an inventory entry.
 *
 * Two rules run through it.
 *
 * **Nothing is typed that could be picked.** A `select` is a list the wizard
 * resolved, never a text box, because a reference typed by hand is the
 * dangling reference `Query` exists to make impossible.
 *
 * **A kind this file does not know is shown, not hidden.** A field type added
 * in `mace.wizard.fields` before it is drawn here says so. Rendering nothing
 * would lose an author's content silently.
 */

import { useEffect, useState } from "react";

import type { FieldSpec } from "./protocol";

export interface ControlProps {
  id: string;
  field: FieldSpec;
  value: unknown;
  busy: boolean;
  /** Called with the authored value. `null` clears it. */
  onChange: (value: unknown) => void;
}

export function Control(props: ControlProps) {
  switch (props.field.kind) {
    case "text":
      return <TextControl {...props} />;
    case "text-list":
      return <LinesControl {...props} />;
    case "number":
      return <NumberControl {...props} />;
    case "bool":
      return <BoolControl {...props} />;
    case "select":
      return <PickOne {...props} />;
    case "multi-select":
      return <PickMany {...props} />;
    case "map-position":
      return <PositionControl {...props} />;
    default:
      return (
        <p className="field-unbuilt">
          Nothing here can collect a <code>{props.field.kind}</code> yet. It is
          safe; open the pack in <code>mace author</code> to change it.
        </p>
      );
  }
}

/** A draft that follows the value when the value changes underneath it. */
function useDraft<T>(value: T): [T, (next: T) => void] {
  const [draft, setDraft] = useState<T>(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);
  return [draft, setDraft];
}

function TextControl({ id, field, value, busy, onChange }: ControlProps) {
  const now = asText(value);
  const [draft, setDraft] = useDraft(now);
  return (
    <div className="field-row">
      <input
        id={id}
        className="field-input"
        type="text"
        value={draft}
        placeholder={field.placeholder ?? ""}
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          if (draft !== now) onChange(draft === "" ? null : draft);
        }}
      />
    </div>
  );
}

function NumberControl({ id, field, value, busy, onChange }: ControlProps) {
  const now = value === null || value === undefined ? "" : String(value);
  const [draft, setDraft] = useDraft(now);
  return (
    <div className="field-row">
      <input
        id={id}
        className="field-input field-number"
        type="number"
        value={draft}
        min={field.minimum ?? undefined}
        max={field.maximum ?? undefined}
        step={field.integer === false ? "any" : 1}
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          if (draft === now) return;
          if (draft === "") return onChange(null);
          const read = Number(draft);
          if (!Number.isNaN(read)) onChange(read);
        }}
      />
      {field.hint === "" ? null : <span className="dim">{field.hint}</span>}
    </div>
  );
}

function BoolControl({ id, value, busy, onChange }: ControlProps) {
  const now = value === true;
  return (
    <div className="field-row">
      <label className="field-check">
        <input
          id={id}
          type="checkbox"
          checked={now}
          disabled={busy}
          onChange={(event) => onChange(event.target.checked ? true : null)}
        />
        <span>{now ? "yes" : "no"}</span>
      </label>
    </div>
  );
}

function PickOne({ id, field, value, busy, onChange }: ControlProps) {
  const options = field.options ?? [];
  const now = typeof value === "string" ? value : "";
  const missing = now !== "" && !options.some((one) => one.value === now);
  return (
    <div className="field-row">
      <select
        id={id}
        className="field-input"
        value={now}
        disabled={busy || options.length === 0}
        onChange={(event) =>
          onChange(event.target.value === "" ? null : event.target.value)
        }
      >
        <option value="">— nothing —</option>
        {/* A reference to something that has gone is shown as itself rather
            than silently becoming "nothing", or opening this form would
            quietly delete the author's answer. */}
        {missing ? <option value={now}>{now} (not found)</option> : null}
        {options.map((one) => (
          <option key={one.value} value={one.value}>
            {one.label}
            {one.note === "" ? "" : ` · ${one.note}`}
          </option>
        ))}
      </select>
      {options.length === 0 ? (
        <span className="dim">nothing to pick yet</span>
      ) : null}
    </div>
  );
}

function PickMany({ id, field, value, busy, onChange }: ControlProps) {
  const options = field.options ?? [];
  const chosen = asList(value).filter(
    (one): one is string => typeof one === "string",
  );

  const toggle = (which: string) => {
    const next = chosen.includes(which)
      ? chosen.filter((one) => one !== which)
      : [...chosen, which];
    onChange(next.length === 0 ? null : next);
  };

  if (options.length === 0) return <p className="dim">Nothing to pick yet.</p>;
  return (
    <ul className="field-many" id={id}>
      {options.map((one) => (
        <li key={one.value}>
          <label className="field-check">
            <input
              type="checkbox"
              checked={chosen.includes(one.value)}
              disabled={busy}
              onChange={() => toggle(one.value)}
            />
            <span>{one.label}</span>
            {one.note === "" ? null : <span className="dim"> · {one.note}</span>}
          </label>
        </li>
      ))}
    </ul>
  );
}

/**
 * Several lines, in order.
 *
 * A textarea rather than a list of inputs: prose is what goes in here, and an
 * author writing three lines of description should be able to write them the
 * way they would anywhere else.
 */
function LinesControl({ id, field, value, busy, onChange }: ControlProps) {
  const lines = asList(value).map(lineText);
  const [draft, setDraft] = useDraft(lines.join("\n"));
  return (
    <div className="field-row">
      <textarea
        id={id}
        className="field-input field-lines"
        rows={Math.max(3, lines.length + 1)}
        value={draft}
        placeholder={field.placeholder ?? ""}
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = draft
            .split("\n")
            .map((one) => one.trim())
            .filter((one) => one !== "");
          if (next.join("\n") === lines.join("\n")) return;
          onChange(next.length === 0 ? null : next);
        }}
      />
    </div>
  );
}

function PositionControl({ id, value, busy, onChange }: ControlProps) {
  const at = value as { x?: number; y?: number } | null;
  const [x, setX] = useDraft(at?.x === undefined ? "" : String(at.x));
  const [y, setY] = useDraft(at?.y === undefined ? "" : String(at.y));

  const commit = (nextX: string, nextY: string) => {
    if (nextX === "" && nextY === "") return onChange(null);
    const [readX, readY] = [Number(nextX), Number(nextY)];
    if (Number.isNaN(readX) || Number.isNaN(readY)) return;
    onChange({ x: readX, y: readY });
  };

  return (
    <div className="field-row">
      <label className="dim" htmlFor={id}>
        x
      </label>
      <input
        id={id}
        className="field-input field-number"
        type="number"
        value={x}
        disabled={busy}
        onChange={(event) => setX(event.target.value)}
        onBlur={() => commit(x, y)}
      />
      <label className="dim" htmlFor={`${id}-y`}>
        y
      </label>
      <input
        id={`${id}-y`}
        className="field-input field-number"
        type="number"
        value={y}
        disabled={busy}
        onChange={(event) => setY(event.target.value)}
        onBlur={() => commit(x, y)}
      />
    </div>
  );
}

export function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function asList(value: unknown): unknown[] {
  if (value === null || value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

/** The text of a line, which the author may have written bare. */
function lineText(line: unknown): string {
  if (typeof line === "string") return line;
  if (typeof line === "object" && line !== null && "text" in line) {
    const text = (line as { text?: unknown }).text;
    return typeof text === "string" ? text : "";
  }
  return "";
}
