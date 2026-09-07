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

import type { GameEvent } from "./protocol";
import { isKind } from "./protocol";

/** How a line reads, which is all a stylesheet needs to know about it. */
export type Tone =
  | "prose"
  | "journey"
  | "weather"
  | "aside"
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
  if (isKind(event, "engine.rule-failed")) {
    return line("warning", event.message);
  }
  if (isKind(event, "game.over")) {
    return line("ending", event.outcome === "won" ? "You won." : "You lost.");
  }
  return null;
}

/**
 * Everything in a frame worth reading, in order.
 *
 * @param events - the frame's events.
 * @returns lines to append to the transcript.
 */
export function transcribe(events: GameEvent[]): Line[] {
  const written: Line[] = [];
  for (const event of events) {
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

/** The menu a frame ended on, if it offered one. */
export function menuOf(events: GameEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event !== undefined && isKind(event, "choices")) return event.options;
  }
  return null;
}
