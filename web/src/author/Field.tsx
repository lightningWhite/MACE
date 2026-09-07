/**
 * One question, drawn as whatever kind of answer it wants.
 *
 * The whole file is a switch on `field.kind`, and that is the design rather
 * than a shortcut: the wizard says what kind of answer a step takes and every
 * front-end decides how to collect one. The terminal reads a line; this reads
 * a control. Neither knows what a location is.
 *
 * Two rules it keeps.
 *
 * **Nothing is typed that could be picked.** A `select` is a list the wizard
 * resolved, never a text box, because a reference typed by hand is the
 * dangling reference `Query` exists to make impossible.
 *
 * **A kind this file does not know is shown, not hidden.** A field type added
 * in `mace.wizard.fields` before it is drawn here reads as its English
 * description and says so, which is a form an author can still work around.
 * Rendering nothing would lose their content silently.
 */

import { useEffect, useState } from "react";

import type { FieldSpec, Step } from "./protocol";

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
      <Control step={step} onAnswer={onAnswer} busy={busy} />
      <p className="field-reading">
        <span className="dim">now: </span>
        {step.described}
      </p>
    </div>
  );
}

function Control({ step, onAnswer, busy }: Props) {
  const id = `field-${step.id}`;
  const field = step.field;

  switch (field.kind) {
    case "text":
      return <TextControl id={id} step={step} onAnswer={onAnswer} busy={busy} />;
    case "text-list":
      return <LinesControl id={id} step={step} onAnswer={onAnswer} busy={busy} />;
    case "number":
      return <NumberControl id={id} step={step} onAnswer={onAnswer} busy={busy} />;
    case "bool":
      return <BoolControl id={id} step={step} onAnswer={onAnswer} busy={busy} />;
    case "select":
      return <PickOne id={id} step={step} onAnswer={onAnswer} busy={busy} />;
    case "multi-select":
      return <PickMany id={id} step={step} onAnswer={onAnswer} busy={busy} />;
    case "map-position":
      return <PositionControl id={id} step={step} onAnswer={onAnswer} busy={busy} />;
    default:
      return <NotYet field={field} />;
  }
}

/** A field this client cannot collect yet, shown rather than hidden. */
function NotYet({ field }: { field: FieldSpec }) {
  return (
    <p className="field-unbuilt">
      This one is built one answer at a time, and the browser cannot do that
      yet — <code>{field.kind}</code>. It is safe here; open the pack in{" "}
      <code>mace author</code> to change it.
    </p>
  );
}

interface ControlProps extends Props {
  id: string;
}

/** A value that follows the step when the step changes underneath it. */
function useDraft<T>(value: T): [T, (next: T) => void] {
  const [draft, setDraft] = useState<T>(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);
  return [draft, setDraft];
}

function TextControl({ id, step, onAnswer, busy }: ControlProps) {
  const [draft, setDraft] = useDraft(asText(step.value));
  const placeholder = step.field.placeholder ?? "";
  return (
    <div className="field-row">
      <input
        id={id}
        className="field-input"
        type="text"
        value={draft}
        placeholder={placeholder}
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          if (draft !== asText(step.value)) onAnswer(draft === "" ? null : draft);
        }}
      />
    </div>
  );
}

function NumberControl({ id, step, onAnswer, busy }: ControlProps) {
  const [draft, setDraft] = useDraft(
    step.value === null || step.value === undefined ? "" : String(step.value),
  );
  const field = step.field;
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
          if (draft === "") return onAnswer(null);
          const read = Number(draft);
          if (!Number.isNaN(read)) onAnswer(read);
        }}
      />
      {field.hint === "" ? null : <span className="dim">{field.hint}</span>}
    </div>
  );
}

function BoolControl({ id, step, onAnswer, busy }: ControlProps) {
  const now = step.value === true;
  return (
    <div className="field-row">
      <label className="field-check">
        <input
          id={id}
          type="checkbox"
          checked={now}
          disabled={busy}
          onChange={(event) => onAnswer(event.target.checked ? true : null)}
        />
        <span>{now ? "yes" : "no"}</span>
      </label>
    </div>
  );
}

function PickOne({ id, step, onAnswer, busy }: ControlProps) {
  const options = step.field.options ?? [];
  const now = typeof step.value === "string" ? step.value : "";
  const missing = now !== "" && !options.some((one) => one.value === now);
  return (
    <div className="field-row">
      <select
        id={id}
        className="field-input"
        value={now}
        disabled={busy || options.length === 0}
        onChange={(event) =>
          onAnswer(event.target.value === "" ? null : event.target.value)
        }
      >
        <option value="">— nothing —</option>
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

function PickMany({ id, step, onAnswer, busy }: ControlProps) {
  const options = step.field.options ?? [];
  const chosen = asList(step.value).filter(
    (one): one is string => typeof one === "string",
  );

  const toggle = (value: string) => {
    const next = chosen.includes(value)
      ? chosen.filter((one) => one !== value)
      : [...chosen, value];
    onAnswer(next.length === 0 ? null : next);
  };

  if (options.length === 0) {
    return <p className="dim">Nothing to pick yet.</p>;
  }
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
 * way they would anywhere else. One blank line separates them, which is also
 * where the beats fall.
 */
function LinesControl({ id, step, onAnswer, busy }: ControlProps) {
  const lines = asList(step.value).map(lineText);
  const [draft, setDraft] = useDraft(lines.join("\n"));
  return (
    <div className="field-row">
      <textarea
        id={id}
        className="field-input field-lines"
        rows={Math.max(3, lines.length + 1)}
        value={draft}
        placeholder={step.field.placeholder ?? ""}
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = draft
            .split("\n")
            .map((one) => one.trim())
            .filter((one) => one !== "");
          if (next.join("\n") === lines.join("\n")) return;
          onAnswer(next.length === 0 ? null : next);
        }}
      />
    </div>
  );
}

function PositionControl({ id, step, onAnswer, busy }: ControlProps) {
  const at = step.value as { x?: number; y?: number } | null;
  const [x, setX] = useDraft(at?.x === undefined ? "" : String(at.x));
  const [y, setY] = useDraft(at?.y === undefined ? "" : String(at.y));

  const commit = (nextX: string, nextY: string) => {
    if (nextX === "" && nextY === "") return onAnswer(null);
    const [readX, readY] = [Number(nextX), Number(nextY)];
    if (Number.isNaN(readX) || Number.isNaN(readY)) return;
    onAnswer({ x: readX, y: readY });
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
      <span className="dim">a map editor is the next thing to build</span>
    </div>
  );
}

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asList(value: unknown): unknown[] {
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
