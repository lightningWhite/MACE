/**
 * Turning events into something to read.
 *
 * The same job `Renderer` does in `mace/cli/play.py`, and deliberately the
 * same *shape* of job: a lookup from event kind to a line, with no rules in
 * it. Where the terminal writes a line, this appends one to a transcript that
 * scrolls, because a browser can keep what a terminal has scrolled away.
 *
 * Events the player has no use for are dropped rather than rendered as
 * debris. The engine emits some for tests and debuggers; a reader is not one
 * of those.
 */

import type { CombatResolved, GameEvent } from "./protocol";
import { isKind } from "./protocol";

/** How a line reads, which is all a stylesheet needs to know about it. */
export type Tone =
  | "prose"
  | "journey"
  | "weather"
  | "aside"
  | "exchange"
  | "warning"
  | "ending";

export interface Line {
  id: number;
  tone: Tone;
  text: string;
}

/** A running number, so React has a key that never repeats. */
let counter = 0;

function line(tone: Tone, text: string): Line {
  counter += 1;
  return { id: counter, tone, text };
}

/** The local half of a qualified content id — `bread`, not `core:bread`. */
function local(id: string): string {
  const at = id.indexOf(":");
  return at < 0 ? id : id.slice(at + 1);
}

/** A number the way a player reads one: 8, not 8.0; 2.5 when it matters. */
function amount(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${amount(value)}`;
}

/**
 * What each outcome of an exchange is called.
 *
 * The same words the terminal uses, from `mace/cli/play.py`, because two
 * front-ends that describe the same exchange differently are two games.
 */
const RESULTS: Record<string, string> = {
  counter: "Clean counter",
  absorbed: "Taken on the guard",
  glancing: "Glancing",
  clean: "Caught square",
};

/** How the timing half of an exchange is described, by precision. */
const TIMING: Array<[number, string]> = [
  [0.9, "perfectly timed"],
  [0.6, "well timed"],
  [0.3, "a shade early"],
  [0.0, "mistimed"],
];

function timing(precision: number): string {
  for (const [floor, said] of TIMING) if (precision >= floor) return said;
  return "mistimed";
}

/**
 * Say how one exchange went, and why.
 *
 * Attribution is what turns an outcome into learning: "Clean counter — you
 * read the overhead" tells a player what to do again, and "-8 hp" does not.
 */
function exchange(event: CombatResolved): string {
  const result = RESULTS[event.result] ?? event.result;
  const read = event.read === "correct" ? "read" : "misread";
  const parts = [`${result} — you ${read} it, ${timing(event.precision)}.`];
  if (event.damageTaken) parts.push(`You take ${amount(event.damageTaken)}.`);
  if (event.damageDealt) {
    const hit = event.critical ? "Critical opening" : "Your opening lands";
    parts.push(`${hit} for ${amount(event.damageDealt)}.`);
  }
  if (event.feint && event.read !== "correct") parts.push("It was a feint.");
  return parts.join(" ");
}

/** How a fight ended, in the terminal's own words. */
const FINISHED: Record<string, string> = {
  won: "You are still standing.",
  lost: "You are not.",
  fled: "You are away, and it is behind you.",
};

/**
 * Render one event, or decline to.
 *
 * Returns null for everything a player has no use for, which is most of the
 * stream: `choices` is a menu rather than prose, `world.status` is the
 * standing line, and the rest exist for the engine's own sake.
 */
function describe(event: GameEvent): Line | null {
  if (isKind(event, "narrate")) {
    return line("prose", event.text);
  }
  if (isKind(event, "travel.leg")) {
    return event.text === null ? null : line("journey", event.text);
  }
  if (isKind(event, "travel.interrupted")) {
    return line("journey", `The journey stops: ${event.reason}.`);
  }
  if (isKind(event, "weather.changed")) {
    return event.text === null ? null : line("weather", event.text);
  }
  if (isKind(event, "stat.changed")) {
    const reason = event.reason === null ? "" : ` (${event.reason})`;
    return line("aside", `${signed(event.delta)} ${event.stat}${reason}`);
  }
  if (isKind(event, "inventory.changed")) {
    return line("aside", `${signed(event.delta)} ${local(event.item)}`);
  }
  if (isKind(event, "quest.updated")) {
    return event.journal === null
      ? line("aside", `Quest ${event.status}: ${local(event.quest)}`)
      : line("aside", `Journal: ${event.journal}`);
  }
  if (isKind(event, "world.news")) {
    const days = event.daysOld === 1 ? "a day" : `${event.daysOld} days`;
    return line("aside", `Word reaches you, ${days} old.`);
  }
  if (isKind(event, "combat.begin")) {
    const against = event.combatants
      .filter((one) => one.side === "enemy")
      .map((one) => one.name)
      .join(", ");
    return line("exchange", `Fighting: ${against}`);
  }
  if (isKind(event, "combat.resolve")) {
    return line("exchange", exchange(event));
  }
  if (isKind(event, "combat.end")) {
    return line("exchange", FINISHED[event.outcome] ?? event.outcome);
  }
  if (isKind(event, "engine.rule-failed")) {
    return line("warning", event.message);
  }
  if (isKind(event, "game.over")) {
    return line("ending", event.outcome === "won" ? "You won." : "You lost.");
  }
  return null;
}

/**
 * Whether a fight is on, carried across frames the same way `play.py`'s
 * `Renderer.fighting` is: one flag, flipped by `combat.begin`/`combat.end`,
 * that the caller holds onto between calls.
 */
export interface Fighting {
  current: boolean;
}

/**
 * Everything in a frame worth reading, in order.
 *
 * `stat.changed` and `world.status` are swallowed while a fight is on, the
 * same as the terminal's `Renderer`: `combat.resolve` already says what an
 * exchange cost and why, with the attacker named, so the bare pool number
 * underneath it is not a second fact, it's the same fact twice with the
 * attacker's name missing. `fighting` is mutated in place — a frame can both
 * start and end a fight, or resolve an exchange mid-fight, so the flag has to
 * flip event-by-event rather than once per frame.
 *
 * @param events - the frame's events.
 * @param fighting - whether a fight is already on, updated as events turn it
 *   on or off. Pass the same object across frames to carry the fight forward;
 *   omit it to always suppress nothing but a fight's own frames of prose.
 * @returns lines to append to the transcript.
 */
export function transcribe(events: GameEvent[], fighting: Fighting = { current: false }): Line[] {
  const written: Line[] = [];
  for (const event of events) {
    if (isKind(event, "combat.begin")) fighting.current = true;
    else if (isKind(event, "combat.end")) fighting.current = false;

    if (fighting.current && (event.kind === "stat.changed" || event.kind === "world.status")) {
      continue;
    }

    const rendered = describe(event);
    if (rendered !== null) written.push(rendered);
  }
  return written;
}

/** The last standing line in a frame, if it carried one. */
export function statusOf(events: GameEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event !== undefined && isKind(event, "world.status")) return event;
  }
  return null;
}

/** The tell a frame ended on, if a fight is waiting on an answer. */
export function tellOf(events: GameEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event !== undefined && isKind(event, "combat.tell")) return event;
  }
  return null;
}

/** The responses a frame ended on, if it offered any. */
export function responsesOf(events: GameEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event !== undefined && isKind(event, "combat.responses")) return event;
  }
  return null;
}

/** The fight a frame started, if it started one. */
export function fightOf(events: GameEvent[]) {
  for (const event of events) {
    if (isKind(event, "combat.begin")) return event;
  }
  return null;
}

/** Whether a frame ended a fight. */
export function fightEnded(events: GameEvent[]): boolean {
  return events.some((event) => event.kind === "combat.end");
}

/** The menu a frame ended on, if it offered one. */
export function menuOf(events: GameEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event !== undefined && isKind(event, "choices")) return event.options;
  }
  return null;
}
