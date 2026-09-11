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

import { useEffect, useState } from "react";

import { Cascade } from "./Cascade";
import { Control } from "./Control";
import type {
  Allocated,
  Built,
  Entry,
  Piece,
  RelativeStat,
  Step,
  StepSpec,
} from "./protocol";

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
 * Bound to a top-level step, which is answered as it changes — the ordinary
 * case, and the shape every other field on an object's own steps takes.
 */
function Pieces({ step, onAnswer, busy }: Props) {
  const kind = step.field.kind === "conditions" ? "conditions" : "effects";
  const single = step.field.single === true;
  const held = (step.entries ?? []) as Piece[];

  return (
    <PiecesEditor
      kind={kind}
      single={single}
      busy={busy}
      held={held}
      onChange={(next) =>
        onAnswer(
          single
            ? (next[0]?.authored ?? null)
            : next.length === 0
              ? null
              : next.map((one) => one.authored),
        )
      }
    />
  );
}

/**
 * The condition/effect list and its "add" button, held by whoever owns the
 * pieces — a step, directly, or one field of an entry still being composed
 * inside a `Repeat`'s own form, which has nothing to answer until the whole
 * entry is added.
 *
 * A `single` condition field holds one rather than a list — a description
 * line's `when` is one condition — so adding replaces rather than appends,
 * and the button says so.
 */
function PiecesEditor({
  kind,
  single,
  busy,
  held,
  onChange,
}: {
  kind: "conditions" | "effects";
  single: boolean;
  busy: boolean;
  held: Piece[];
  onChange: (next: Piece[]) => void;
}) {
  const [building, setBuilding] = useState(false);

  const add = (built: Built) => {
    setBuilding(false);
    const piece: Piece = { authored: built.authored, said: built.said };
    onChange(single ? [piece] : [...held, piece]);
  };

  const drop = (index: number) => {
    if (single) return onChange([]);
    onChange(held.filter((_one, at) => at !== index));
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
  const [composing, setComposing] = useState<"add" | number | null>(null);
  const held = (step.entries ?? []) as Entry[];
  const noun = step.field.of ?? "entry";
  const steps = step.field.steps ?? [];

  const add = (values: Record<string, unknown>) => {
    setComposing(null);
    onAnswer([...held.map((one) => one.values), values]);
  };

  const save = (index: number, values: Record<string, unknown>) => {
    setComposing(null);
    onAnswer(held.map((one, at) => (at === index ? values : one.values)));
  };

  const drop = (index: number) => {
    setComposing(null);
    const next = held.filter((_one, at) => at !== index).map((one) => one.values);
    onAnswer(next.length === 0 ? null : next);
  };

  const editing = typeof composing === "number" ? held[composing] : undefined;

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
                className="piece-edit"
                disabled={busy}
                onClick={() => setComposing(index)}
                aria-label={`Edit ${noun} ${index + 1}`}
              >
                edit
              </button>
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

      {composing !== null ? (
        <EntryForm
          noun={noun}
          steps={steps}
          busy={busy}
          initial={editing}
          onDone={
            typeof composing === "number" ? (values) => save(composing, values) : add
          }
          onCancel={() => setComposing(null)}
        />
      ) : (
        <button
          type="button"
          className="piece-add"
          disabled={busy || steps.length === 0}
          onClick={() => setComposing("add")}
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
 *
 * `initial` reopens this on an entry that already exists, rather than
 * building a fresh one — the same form either way, seeded from what is
 * already there instead of from nothing.
 */
function EntryForm({
  noun,
  steps,
  busy,
  initial,
  onDone,
  onCancel,
}: {
  noun: string;
  steps: StepSpec[];
  busy: boolean;
  initial?: Entry | undefined;
  onDone: (values: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    initial ? flatten(steps, initial.values) : {},
  );
  // Conditions and effects need their English kept alongside the raw answer
  // while an entry is still being composed — there is no server-held `Step`
  // for a sub-field to read `.entries` off, because the entry it belongs to
  // has not been added yet (or, reopened on an existing entry, the wizard
  // sent it already said, keyed the same way this state is).
  const [pieces, setPieces] = useState<Record<string, Piece[]>>(
    () => initial?.pieces ?? {},
  );
  const missing = steps.filter(
    (one) => !one.optional && !answered(values[keyOf(one.binds)]),
  );

  const setValue = (key: string, value: unknown) =>
    setValues((current) => ({ ...current, [key]: value }));

  return (
    <div className="cascade">
      <p className="cascade-question">{initial ? `This ${noun}` : `A new ${noun}`}</p>
      {steps.map((one) => {
        const key = keyOf(one.binds);
        const isPieces = one.field.kind === "conditions" || one.field.kind === "effects";
        return (
          <div className="field" key={one.id}>
            <label className="field-title" htmlFor={`entry-${one.id}`}>
              {one.title}
              {one.optional ? <span className="dim"> — optional</span> : null}
            </label>
            {one.help === "" ? null : <p className="field-help">{one.help}</p>}
            {isPieces ? (
              <PiecesEditor
                kind={one.field.kind === "conditions" ? "conditions" : "effects"}
                single={one.field.single === true}
                busy={busy}
                held={pieces[key] ?? []}
                onChange={(next) => {
                  setPieces((current) => ({ ...current, [key]: next }));
                  const single = one.field.single === true;
                  setValue(
                    key,
                    single
                      ? (next[0]?.authored ?? null)
                      : next.length === 0
                        ? null
                        : next.map((piece) => piece.authored),
                  );
                }}
              />
            ) : (
              <Control
                id={`entry-${one.id}`}
                field={one.field}
                value={values[key] ?? null}
                busy={busy}
                onChange={(value) => setValue(key, value)}
              />
            )}
          </div>
        );
      })}
      <div className="cascade-actions">
        <button
          type="button"
          disabled={busy || missing.length > 0}
          onClick={() => onDone(assemble(steps, values))}
        >
          {initial ? "Save it" : "Add it"}
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
 * `hull-integrity` beside them. `step.field.core` marks the ones the engine
 * reads by name in *this* project specifically — resolved server-side
 * against its own `game.rules.vitalPool`/`effortPool`, so a sci-fi pack that
 * renamed its vital pool sees that name marked, not a `hitpoints` it never
 * declared. Marked, not enforced: nothing stops renaming or removing one,
 * but the badge is there so nobody mistakes "the engine reads this by name"
 * for "this is flavor, waiting on a condition to give it meaning."
 */
function Statblock({ step, onAnswer, busy }: Props) {
  const held = (step.entries ?? []) as Allocated[];
  const [naming, setNaming] = useState("");
  const points = step.field.points ?? 0;
  const spent = held.reduce((total, one) => total + (one.base ?? 0), 0);
  const core = step.field.core ?? {};
  const playerStats = step.field.playerStats ?? [];
  const suggested = (step.field.stats ?? []).filter(
    (one) => !held.some((had) => had.stat === one),
  );

  const write = (next: Allocated[]) => {
    if (next.length === 0) return onAnswer(null);
    onAnswer(
      Object.fromEntries(
        next.map((one) => [
          one.stat,
          {
            base: one.relativeBase
              ? { relativeToPlayer: one.relativeBase }
              : (one.base ?? 0),
            ...(one.relativeMax
              ? { max: { relativeToPlayer: one.relativeMax } }
              : one.max !== null
                ? { max: one.max }
                : {}),
          },
        ]),
      ),
    );
  };

  const changeBase = (stat: string, next: number | RelativeStat | null) => {
    write(
      held.map((one) =>
        one.stat !== stat
          ? one
          : typeof next === "number" || next === null
            ? { ...one, base: next ?? 0, relativeBase: null }
            : { ...one, relativeBase: next },
      ),
    );
  };

  const changeMax = (stat: string, next: number | RelativeStat | null) => {
    write(
      held.map((one) =>
        one.stat !== stat
          ? one
          : typeof next === "number" || next === null
            ? { ...one, max: next, relativeMax: null }
            : { ...one, relativeMax: next },
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
          <StatRow
            key={one.stat}
            allocated={one}
            busy={busy}
            core={core[one.stat]}
            playerStats={playerStats}
            onChangeBase={(value) => changeBase(one.stat, value)}
            onChangeMax={(value) => changeMax(one.stat, value)}
            onRemove={() => write(held.filter((had) => had.stat !== one.stat))}
          />
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

/**
 * One stat's two values (base and cap), each independently either a fixed
 * number or a multiple of the player's own stat.
 */
function StatRow({
  allocated,
  busy,
  core,
  playerStats,
  onChangeBase,
  onChangeMax,
  onRemove,
}: {
  allocated: Allocated;
  busy: boolean;
  /** What this stat does, if the project marks it as one the engine reads
   * by name — undefined for an ordinary free-form stat. */
  core: string | undefined;
  /** The player's own declared stats, to reference in a relative value. */
  playerStats: string[];
  onChangeBase: (value: number | RelativeStat | null) => void;
  onChangeMax: (value: number | RelativeStat | null) => void;
  onRemove: () => void;
}) {
  return (
    <li>
      <span className="statblock-name">{allocated.stat}</span>
      {core !== undefined && (
        <span className="statblock-core" title={core}>
          core
        </span>
      )}
      <ValueControl
        label={`${allocated.stat} base`}
        busy={busy}
        value={allocated.base}
        relative={allocated.relativeBase ?? null}
        playerStats={playerStats}
        onChange={onChangeBase}
      />
      <span className="dim">/</span>
      <ValueControl
        label={`${allocated.stat} cap`}
        placeholder="cap"
        busy={busy}
        value={allocated.max}
        relative={allocated.relativeMax ?? null}
        playerStats={playerStats}
        onChange={onChangeMax}
        allowEmpty
      />
      <button
        type="button"
        className="piece-drop"
        disabled={busy}
        onClick={onRemove}
        aria-label={`Remove ${allocated.stat}`}
      >
        remove
      </button>
    </li>
  );
}

/**
 * A number, or a multiple of one of the player's own stats — switched with a
 * plain link so the common case (typing a number) stays a single click away.
 *
 * Buffered locally like every other control here: writing straight through
 * on every keystroke round-trips to the wizard on every digit, and the value
 * coming back on the next render fights whatever the input was about to show
 * next.
 */
function ValueControl({
  label,
  placeholder,
  busy,
  value,
  relative,
  playerStats,
  onChange,
  allowEmpty = false,
}: {
  label: string;
  placeholder?: string;
  busy: boolean;
  value: number | null;
  relative: RelativeStat | null;
  playerStats: string[];
  onChange: (next: number | RelativeStat | null) => void;
  allowEmpty?: boolean;
}) {
  const [typed, setTyped] = useState(value === null ? "" : String(value));
  const [factor, setFactor] = useState(String(relative?.factor ?? 1));

  useEffect(() => setTyped(value === null ? "" : String(value)), [value]);
  useEffect(() => setFactor(String(relative?.factor ?? 1)), [relative?.factor]);

  if (relative !== null) {
    return (
      <span className="statblock-relative">
        <input
          className="field-input field-number field-number-narrow"
          type="number"
          aria-label={`${label} factor`}
          value={factor}
          disabled={busy}
          onChange={(event) => setFactor(event.target.value)}
          onBlur={() => {
            const read = Number(factor);
            if (Number.isNaN(read)) setFactor(String(relative.factor));
            else onChange({ stat: relative.stat, factor: read });
          }}
        />
        <span className="dim">x player's</span>
        <select
          className="field-input"
          aria-label={`${label} stat`}
          value={relative.stat}
          disabled={busy}
          onChange={(event) => onChange({ stat: event.target.value, factor: relative.factor })}
        >
          {playerStats.includes(relative.stat) ? null : (
            <option value={relative.stat}>{relative.stat}</option>
          )}
          {playerStats.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="link-button"
          disabled={busy}
          onClick={() => onChange(allowEmpty ? null : 0)}
        >
          fixed
        </button>
      </span>
    );
  }

  return (
    <span className="statblock-fixed">
      <input
        className="field-input field-number"
        type="number"
        aria-label={label}
        placeholder={placeholder}
        value={typed}
        disabled={busy}
        onChange={(event) => setTyped(event.target.value)}
        onBlur={() => {
          if (typed === "" && allowEmpty) return onChange(null);
          const read = Number(typed);
          if (Number.isNaN(read)) setTyped(value === null ? "" : String(value));
          else onChange(read);
        }}
      />
      {playerStats.length > 0 && (
        <button
          type="button"
          className="link-button"
          disabled={busy}
          onClick={() => onChange({ stat: playerStats[0] ?? "", factor: 1 })}
        >
          relative
        </button>
      )}
    </span>
  );
}

/**
 * Where a sub-step's answer lives inside its entry — everything past the
 * repeat's own name in its binding, joined back into one key for the local
 * `values` state. `entries.combat.against` keys as `combat.against`;
 * `stages.journal` keys as `journal`, same as it always has.
 */
function keyOf(binds: string): string {
  return binds.split(".").slice(1).join(".");
}

function answered(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" || Array.isArray(value)) return value.length > 0;
  return true;
}

/**
 * Set a dotted path in a plain object, creating the way as it goes — the
 * same rule `mace.wizard.flow.plant` applies on the Python side, so
 * `entries.combat.against` lands at `{combat: {against: [...]}}` here too.
 */
function plant(holder: Record<string, unknown>, path: string[], value: unknown): void {
  let current = holder;
  for (const key of path.slice(0, -1)) {
    const nested = current[key];
    if (typeof nested !== "object" || nested === null || Array.isArray(nested)) {
      current[key] = {};
    }
    current = current[key] as Record<string, unknown>;
  }
  const leaf = path[path.length - 1];
  if (leaf !== undefined) current[leaf] = value;
}

/**
 * Drop the questions the author left blank, and nest each answer at the path
 * its own step binds to, so the entry reads the way an ordinary object's
 * bindings would.
 */
function assemble(
  steps: StepSpec[],
  values: Record<string, unknown>,
): Record<string, unknown> {
  const entry: Record<string, unknown> = {};
  for (const step of steps) {
    const key = keyOf(step.binds);
    const value = values[key];
    if (answered(value)) plant(entry, key.split("."), value);
  }
  return entry;
}

/** Follow a dotted path into a plain object — the read half of `plant`. */
function dig(holder: Record<string, unknown>, path: string[]): unknown {
  let current: unknown = holder;
  for (const key of path) {
    if (typeof current !== "object" || current === null || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

/**
 * The inverse of `assemble`: an existing entry, read back into the flat,
 * per-step `values` an `EntryForm` keeps while it is open — what reopening
 * one for editing seeds its local state from.
 */
function flatten(
  steps: StepSpec[],
  entryValues: Record<string, unknown>,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const step of steps) {
    const key = keyOf(step.binds);
    const value = dig(entryValues, key.split("."));
    if (value !== undefined) values[key] = value;
  }
  return values;
}
