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
  /**
   * What a dependent ask's answer must equal for this option to apply — the
   * quest a stage belongs to, say. Empty for an option offered regardless.
   */
  scope: string;
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
  /** Whether typing something not on `options` is itself an answer. */
  freeText?: boolean;
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
  /**
   * Said in English, per condition/effect sub-field — keyed the same way
   * `EntryForm` keys its own local state, so reopening an entry to edit it
   * can seed `PiecesEditor` without losing whichever condition or effect
   * is already there.
   */
  pieces: Record<string, Piece[]>;
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
  /** The region it belongs to, id as authored — `null` for none. */
  region: string | null;
  /**
   * Another place this one is inside of, id as authored — `null` for none.
   * A place with this set gets no pin of its own on the world canvas; it
   * belongs on its named hub's own small canvas instead.
   */
  submapOf: string | null;
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
/** One region on the author's map — a name, nothing more; membership lives on
 * each place's own `region`. */
export interface MapRegion {
  id: string;
  name: string;
}

export interface Atlas {
  places: Drawn[];
  roads: Road[];
  regions: MapRegion[];
}

/** One line of an object's description, and when the player reads it. */
export interface Told {
  text: string;
  /** The condition, in English. "always" for the fallback. */
  when: string;
}

/** One short answer about an object, and whether the author wrote it. */
export interface Fact {
  label: string;
  value: string;
  /** False when it came from whatever this object `extends`. */
  own: boolean;
}

/** One object as the engine will see it, inheritance resolved. */
export interface Preview {
  collection: string;
  id: string;
  name: string;
  /** False when the models will not accept it yet; `why` says what is wrong. */
  built: boolean;
  inherits: string | null;
  why: string[];
  lines: Told[];
  facts: Fact[];
  stats: Array<{
    stat: string;
    base: number;
    max: number | null;
    customizable: boolean;
  }>;
  carries: Array<{ item: string; name: string; qty: number }>;
}

/** One node of the scene graph. */
export interface Node {
  id: string;
  prompt: string | null;
  /** Local ids of the scenes this one can lead to. */
  leadsTo: string[];
  /** Whether something outside the scene graph points at it. */
  entrance: boolean;
  /** Whether there is any way in at all. */
  reachable: boolean;
  /** Whether it hands control back rather than leading anywhere. */
  ends: boolean;
}

/** Every scene, what leads to it, and what it leads to. */
export interface Graph {
  entrances: string[];
  scenes: Node[];
  /** Files the wizard could not read. */
  unreadable: string[];
  /** Scenes that will not compile, so they are not on the graph at all. */
  dropped: string[];
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
    /** Another ask's key in this recipe, when this one's options should be
     * narrowed to whatever was answered there. Empty for a question that
     * stands on its own. */
    dependsOn: string;
    field: FieldSpec;
  }>;
}

export interface Vocabulary {
  conditions: Recipe[];
  effects: Recipe[];
}

/**
 * Where and how to open a playtest.
 *
 * Every field is a session-opening parameter, the way the seed is, so a
 * playtest is an ordinary replayable session rather than a special mode.
 */
export interface Setup {
  seed: string;
  startLocation: string | null;
  startTick: number | null;
  weather: string | null;
  items: Record<string, number>;
  background: string | null;
  spend: Record<string, number>;
  combatMode: string | null;
}

/** The playtest form: what was used last, and the pickers to change it. */
export interface Rehearsal {
  setup: Setup;
  locations: Option[];
  weather: Option[];
  items: Option[];
}

/** What `POST /export` returns: the file, and how big it is. */
export interface Exported {
  path: string;
  bytes: number;
}

/** What `POST /build` returns: content, and the English of it. */
export interface Built {
  authored: Record<string, unknown>;
  said: string;
}

/** One authorable game pack, as `GET /api/author/games` lists it. */
export interface AuthorableGame {
  id: string;
  name: string;
  path: string;
}

/** Every game a `Desk` can open or switch to, and which one (if any) is. */
export interface AuthorableGames {
  games: AuthorableGame[];
  open: string | null;
}

/** Every library pack a new game could depend on. */
export interface AuthorableLibraries {
  libraries: AuthorableGame[];
}

/** What `GET /api/author` says when nothing is open yet. */
export interface NothingOpen {
  open: false;
}

/** Whether a reply from `GET /api/author` is a real frame. */
export function isOpen(reply: Frame | NothingOpen): reply is Frame {
  return "pack" in reply;
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
