/**
 * The wire, as TypeScript sees it.
 *
 * Every one of these shapes is produced by Python — `Event.record()`,
 * `View.record()`, `Save.record()` — and this file is the only place that
 * knows it. Nothing below it re-derives a fact the engine already stated, and
 * nothing above it reads a field this file has not declared.
 *
 * The engine is the authority on all of it. If a panel wants something that
 * is not here, the fix is a field on the projection in `mace/session/view.py`,
 * never a computation in a component.
 */

/** What the service says about one playable pack. */
export interface GameSummary {
  id: string;
  name: string;
  version: string;
  description: string | null;
}

/** One background on offer at character creation, already phrased. */
export interface BackgroundOffer {
  id: string;
  name: string;
  description: string;
  /** What picking it does, in English. The engine phrases these, not us. */
  grants: string[];
}

/** One stat creation points may be spent on. */
export interface StatOffer {
  stat: string;
  base: number;
  minimum: number;
  maximum: number;
  /** How many points this stat can still take. */
  room: number;
}

/** The character-creation question, or the news that there isn't one. */
export interface CreationOffer {
  asksAnything: boolean;
  points: number;
  backgrounds: BackgroundOffer[];
  stats: StatOffer[];
}

/**
 * How hard the clock presses in `reflex` combat.
 *
 * 1.0 is the fight as written; 0.5 gives twice the window. An accessibility
 * setting, and a session one — a recorded `elapsedMs` only means anything
 * against the window it was answered inside, so it cannot move mid-game.
 */
export const PRESSURES: Array<{ value: number; label: string }> = [
  { value: 0.5, label: "Twice the time" },
  { value: 0.75, label: "A little longer" },
  { value: 1, label: "As written" },
  { value: 1.5, label: "Harder" },
];

/** What the player answered at creation. */
export interface Made {
  background: string | null;
  spend: Record<string, number>;
}

// ── Events: things that happened ─────────────────────────────────────────────

/** One option on a menu. */
export interface Option {
  prompt: string;
  available: boolean;
  /** Why it is unavailable, when the author wrote a reason. */
  hint: string | null;
}

export interface Narrated {
  kind: "narrate";
  text: string;
  pause: boolean;
}

export interface ChoicesOffered {
  kind: "choices";
  scene: string;
  options: Option[];
}

export interface WorldStatus {
  kind: "world.status";
  tick: number;
  day: number;
  dayPart: string;
  season: string;
  time: string;
  location: string | null;
  place: string;
  region: string | null;
  weather: string | null;
  sky: string;
  temperature: number | null;
  light: number;
  indoors: boolean;
  /** 0 to 1. A number on purpose: how to say it is ours to decide. */
  exposure: number;
}

export interface TravelLeg {
  kind: "travel.leg";
  route: string;
  leg: number;
  of: number;
  waypoint: string | null;
  text: string | null;
}

export interface TravelInterrupted {
  kind: "travel.interrupted";
  route: string;
  at: string | null;
  destination: string;
  remaining: number;
  reason: string;
}

export interface WeatherChanged {
  kind: "weather.changed";
  region: string;
  condition: string;
  name: string;
  intensity: number;
  tags: string[];
  visibility: number;
  temperature: number | null;
  text: string | null;
}

export interface Moved {
  kind: "moved";
  from: string | null;
  to: string;
  route: string | null;
  ticks: number;
}

export interface StatChanged {
  kind: "stat.changed";
  actor: string;
  stat: string;
  delta: number;
  value: number;
  reason: string | null;
}

export interface InventoryChanged {
  kind: "inventory.changed";
  actor: string;
  item: string;
  delta: number;
  quantity: number;
}

export interface QuestUpdated {
  kind: "quest.updated";
  quest: string;
  status: string;
  stage: string | null;
  journal: string | null;
}

export interface NewsHeard {
  kind: "world.news";
  event: string;
  daysOld: number;
  region: string | null;
}

// ── Combat ───────────────────────────────────────────────────────────────────

export interface Combatant {
  actor: string;
  name: string;
  side: "player" | "enemy";
  profile: string | null;
  /**
   * The pool `game.rules.vitalPool` names, as it stood when the fight began.
   * `stat.changed` events update it exchange by exchange — this is only the
   * opening value, kept so a client that never learns the running total
   * still has something to draw.
   */
  vital: Gauge;
}

/** One row of the counter matrix: what beats a move of this type. */
export interface Counter {
  type: string;
  beatenBy: string[];
}

export interface CombatBegan {
  kind: "combat.begin";
  combat: string;
  mode: "reflex" | "tactical" | "auto";
  combatants: Combatant[];
  canFlee: boolean;
  /** The training wheels. Shown until the player turns them off. */
  matrix: Counter[];
}

export interface CombatTell {
  kind: "combat.tell";
  combat: string;
  attacker: string;
  defender: string;
  move: string;
  /** The move's type, or empty when the tell was not legible. */
  type: string;
  text: string;
  /** How long the window is open. The bar drains over this. */
  windowMs: number;
  /** Whether the tell gave the move away. */
  clear: boolean;
}

export interface CombatResponse {
  response: string;
  label: string;
}

export interface ResponsesOffered {
  kind: "combat.responses";
  combat: string;
  options: CombatResponse[];
  stamina: number;
  momentum: number;
  streak: number;
}

export interface CombatResolved {
  kind: "combat.resolve";
  combat: string;
  exchange: number;
  attacker: string;
  defender: string;
  move: string;
  response: string;
  read: "correct" | "wrong" | string;
  result: string;
  /** 0 to 1. How close to the sweet spot the answer landed. */
  precision: number;
  damageTaken: number;
  damageDealt: number;
  critical: boolean;
  momentum: number;
  stamina: number;
  feint: boolean;
}

export interface Spoil {
  item: string;
  qty: number;
}

export interface CombatEnded {
  kind: "combat.end";
  combat: string;
  outcome: "won" | "lost" | "fled" | string;
  exchanges: number;
  spoils: Spoil[];
}

export interface GameOver {
  kind: "game.over";
  outcome: string;
  reason: string | null;
}

export interface RuleFailed {
  kind: "engine.rule-failed";
  message: string;
  where: string | null;
}

/** Anything this client does not render. Kept, never guessed at. */
export interface OtherEvent {
  kind: string;
  [field: string]: unknown;
}

export type GameEvent =
  | Narrated
  | ChoicesOffered
  | WorldStatus
  | TravelLeg
  | TravelInterrupted
  | WeatherChanged
  | Moved
  | StatChanged
  | InventoryChanged
  | QuestUpdated
  | NewsHeard
  | CombatBegan
  | CombatTell
  | ResponsesOffered
  | CombatResolved
  | CombatEnded
  | GameOver
  | RuleFailed
  | OtherEvent;

/**
 * Narrow an event by its kind.
 *
 * TypeScript cannot do it from a union with an open member in it, so this is
 * the one cast in the client, made once and in the open.
 */
export function isKind<K extends GameEvent["kind"]>(
  event: GameEvent,
  kind: K,
): event is Extract<GameEvent, { kind: K }> {
  return event.kind === kind;
}

// ── The view-model: things that stand ────────────────────────────────────────

export interface Gauge {
  stat: string;
  value: number;
  maximum: number | null;
  role: "vital" | "effort" | "ability";
}

export interface Carried {
  item: string;
  name: string;
  qty: number;
  value: number | null;
}

export interface Entry {
  quest: string;
  name: string;
  summary: string | null;
  status: "active" | "complete" | "failed";
  stage: string | null;
  journal: string | null;
  startedAtTick: number | null;
}

export type Standing = "here" | "visited" | "known";

export interface Place {
  location: string;
  name: string;
  standing: Standing;
  region: string | null;
  weather: string | null;
  sky: string | null;
  indoors: boolean;
  /**
   * The option on offer that goes here, if one is.
   *
   * What makes the map something you can travel by rather than a picture of
   * one. Only the engine knows that "Take the north road" is the option that
   * walks to Hagan's Castle; a client that matched prompts to places by their
   * wording would be guessing at content.
   */
  choice: number | null;
  /**
   * Good id to the last unit price the player was quoted here.
   *
   * Only prices they have personally seen. An overlay drawn from what the
   * engine knows would be a map that told the player where to go.
   */
  prices: Record<string, number>;
  x: number | null;
  y: number | null;
}

export interface Road {
  route: string;
  name: string | null;
  from: string;
  to: string;
  bidirectional: boolean;
  ticks: number;
  closed: boolean;
  reason: string | null;
}

export interface Underway {
  route: string;
  from: string;
  to: string;
  walked: number;
  ticks: number;
  blockedAt: string | null;
}

export interface Atlas {
  here: string | null;
  places: Place[];
  roads: Road[];
  journey: Underway | null;
}

export interface Sheet {
  entity: string;
  name: string;
  background: string | null;
  stats: Gauge[];
  exposure: number;
}

/** One good on a merchant's counter, priced for right now. */
export interface Priced {
  good: string;
  item: string;
  name: string;
  /** What one costs the player, or null when it is not for sale. */
  buy: number | null;
  /** What the merchant pays for one, or null when it will not take it. */
  sell: number | null;
  available: number;
  carried: number;
}

/** What the merchant in front of the player is offering. */
export interface Stall {
  merchant: string;
  name: string;
  /** Empty for a caravan, which deals for nowhere. */
  market: string;
  /** Whether this is a caravan carrying its own prices. */
  mobile: boolean;
  currency: string;
  /** What the player has. */
  coin: number;
  /** What the merchant can pay out. `null` is bottomless — a whole town. */
  purse: number | null;
  /** How far an argument has moved the bill. Negative once they have soured. */
  swing: number;
  /** Whether this merchant will argue about a price at all. */
  haggles: boolean;
  /** Whether they have heard enough for now. */
  soured: boolean;
  goods: Priced[];
}

export interface View {
  pack: string;
  tick: number;
  outcome: "playing" | "won" | "lost";
  endedBecause: string | null;
  sheet: Sheet;
  carried: Carried[];
  journal: Entry[];
  atlas: Atlas;
  /** Prices, while the player is standing at a counter. */
  stall: Stall | null;
}

// ── One frame for every reply ────────────────────────────────────────────────

export interface Frame {
  session: string;
  playing: boolean;
  events: GameEvent[];
  choices: string[];
  view: View;
  /** Only on the frame that opened a session from a save. */
  warnings?: string[];
}

/** What the socket sends instead of a frame when it refuses one. */
export interface Refusal {
  error: string;
}

export function isRefusal(message: Frame | Refusal): message is Refusal {
  return "error" in message;
}

/** An action, in the record form the engine decodes. */
export type Action =
  | { kind: "choose"; option: number }
  | { kind: "choose"; prompt: string }
  | { kind: "combat.input"; response: string; elapsedMs?: number }
  | { kind: "wait"; ticks: number }
  | { kind: "trade"; good: string; qty: number; sell: boolean }
  | { kind: "haggle" }
  | { kind: "look" };

/** A save file: packs, seed, character, and everything the player did. */
export interface SaveRecord {
  format: number;
  pack: string;
  seed: string;
  packs: Record<string, string>;
  combatMode?: string;
  timePressure?: number;
  character?: Made;
  startAt?: string;
  startTick?: number;
  actions: Array<Record<string, unknown>>;
}
