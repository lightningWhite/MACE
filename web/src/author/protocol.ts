/**
 * The wire the authoring client is written against.
 *
 * Every shape here is projected by `mace.wizard.studio` and recorded into
 * `src/test/author.json` by `tests/test_web_author_wire.py`, so a change to
 * the wizard's screens fails a Python test before it reaches a browser. The
 * client never invents a question, a field type, or an option list.
 */

/** How far along one section of the task list is. */
export type State = "empty" | "started" | "done";

/** How much a problem matters. */
export type Severity = "error" | "warning" | "note";

/** One line of the task list. */
export interface Task {
  section: string;
  title: string;
  help: string;
  state: State;
  summary: string;
  /** The one problem worth showing on a crowded row. */
  note: string;
  errors: number;
  /** The flow that authors it, where one does. */
  flow: string | null;
  collections: string[];
}

/** The task list, as a header and a set of rows. */
export interface Desk {
  name: string;
  percent: number;
  problems: number;
  errors: number;
  tasks: Task[];
}

/** One thing the validator found. */
export interface Problem {
  severity: Severity;
  message: string;
  pack: string;
  path: string | null;
  collection: string | null;
  object: string | null;
  field: string | null;
}

/** One thing an author can pick. */
export interface Option {
  value: string;
  label: string;
  /** Where it came from: `this pack`, or a library's id. */
  note: string;
}

/**
 * A field type, with its options already resolved.
 *
 * The union is deliberately flat: `kind` is what the renderer switches on,
 * and every other key is optional because a field type only carries what it
 * needs. Adding one in `mace.wizard.fields` shows up here as a `kind` the
 * renderer does not know, which it draws as read-only rather than as nothing.
 */
export interface FieldSpec {
  kind: string;
  optional: boolean;
  /** Whether a builder drives this rather than a control. */
  interactive: boolean;
  hint: string;
  placeholder?: string;
  minItems?: number;
  minimum?: number | null;
  maximum?: number | null;
  integer?: boolean;
  options?: Option[];
  /** A collection to offer "+ make a new one" for. */
  allowCreate?: string | null;
  points?: number;
  stats?: string[];
  single?: boolean;
  of?: string;
  steps?: StepSpec[];
}

/** One question inside a repeat, which has no answer of its own. */
export interface StepSpec {
  id: string;
  title: string;
  help: string;
  binds: string;
  optional: boolean;
  field: FieldSpec;
}

/** One condition or effect already on a step, and the English of it. */
export interface Piece {
  authored: Record<string, unknown>;
  said: string;
}

/** One entry of a repeat: what it holds, and a line summarising it. */
export interface Entry {
  values: Record<string, unknown>;
  summary: string;
}

/** One stat of a statblock. */
export interface Allocated {
  stat: string;
  base: number;
  max: number | null;
}

/** One question, its answer, and everything a form needs to draw it. */
export interface Step extends StepSpec {
  value: unknown;
  /** What the answer is, in English. */
  described: string;
  answered: boolean;
  /**
   * The pieces of an answer that holds several of something, so a list can be
   * shown and taken apart. `null` for a field that holds one answer.
   */
  entries: Piece[] | Entry[] | Allocated[] | null;
}

/** A section's contents, and what may be made in it. */
export interface SectionScreen {
  section: string;
  title: string;
  help: string;
  /** Whether it is one object rather than a list — game setup. */
  manifest: boolean;
  creates: string[];
  objects: Array<{
    collection: string;
    id: string;
    label: string;
    unfinished: boolean;
  }>;
  problems: Problem[];
}

/** One object's steps. */
export interface ObjectScreen {
  collection: string;
  id: string | null;
  title: string;
  noun: string;
  label: string;
  steps: Step[];
}

/** What `POST /save` puts on the screen. */
export interface SavedScreen {
  saved: string[];
}

export type Screen =
  | SectionScreen
  | ObjectScreen
  | Step
  | SavedScreen
  | null;

/** One shape for every reply. */
export interface Frame {
  pack: { id: string; name: string; kind: string; version: string };
  /** Files changed since the last save. */
  dirty: string[];
  /** Files the wizard could not read, which it leaves exactly as they are. */
  unreadable: string[];
  desk: Desk;
  screen: Screen;
}

/** One place on the author's map, as they have drawn it. */
export interface Drawn {
  id: string;
  name: string;
  /** `null` where the author has not put it anywhere yet. */
  x: number | null;
  y: number | null;
  /** Local ids of the places you can walk to from here. */
  exits: string[];
}

/** One road on the author's map. */
export interface Road {
  id: string;
  name: unknown;
  from: unknown;
  to: unknown;
  ticks: unknown;
  bidirectional: boolean;
}

/**
 * The world map as the author has drawn it.
 *
 * Not the player's atlas: no fog of war, no weather, and no opinion about
 * where anybody has been. It is the shape of the pack.
 */
export interface Atlas {
  places: Drawn[];
  roads: Road[];
}

/** One way of building a condition or an effect. */
export interface Recipe {
  tag: string;
  label: string;
  group: string;
  help: string;
  /** Whether it is written bare — `{chance: 0.15}` rather than a mapping. */
  bare: boolean;
  asks: Array<{
    key: string;
    title: string;
    help: string;
    default: unknown;
    field: FieldSpec;
  }>;
}

export interface Vocabulary {
  conditions: Recipe[];
  effects: Recipe[];
}

/** What `POST /build` returns: content, and the English of it. */
export interface Built {
  authored: Record<string, unknown>;
  said: string;
}

export function isSection(screen: Screen): screen is SectionScreen {
  return screen !== null && "objects" in screen;
}

export function isObject(screen: Screen): screen is ObjectScreen {
  return screen !== null && "steps" in screen && "noun" in screen;
}

export function isStep(screen: Screen): screen is Step {
  return screen !== null && "described" in screen;
}

export function isSaved(screen: Screen): screen is SavedScreen {
  return screen !== null && "saved" in screen;
}
