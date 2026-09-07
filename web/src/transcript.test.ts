/**
 * Turning the engine's events into something to read.
 *
 * Every event here came out of the real engine — see `test/wire.ts` — so a
 * test that passes is a test against the protocol as it is, not as this file
 * imagines it.
 */

import { describe, expect, it } from "vitest";

import type { GameEvent } from "./protocol";
import { menuOf, statusOf, transcribe } from "./transcript";
import { afterStep, opening } from "./test/wire";

describe("transcribe", () => {
  it("reads the opening prose in the order it was narrated", () => {
    const lines = transcribe(opening.events);
    expect(lines[0]?.text).toContain("You are a peasant");
    expect(lines.every((line) => line.text.length > 0)).toBe(true);
  });

  it("drops the events a reader has no use for", () => {
    // `scene.entered` and `character.created` are in the stream and are not
    // prose; rendering them would be debris.
    const text = transcribe(opening.events).map((line) => line.text);
    expect(text.some((one) => one.includes("scene.entered"))).toBe(false);
    expect(text.some((one) => one.includes("fenmoor-arrival"))).toBe(false);
  });

  it("gives a journey its own tone", () => {
    const tones = transcribe(afterStep(0).events).map((line) => line.tone);
    expect(tones).toContain("journey");
  });

  it("says why a journey stopped", () => {
    const text = transcribe(afterStep(0).events).map((line) => line.text);
    expect(text.some((one) => one.startsWith("The journey stops:"))).toBe(true);
  });

  it("phrases a stat change the way a player reads one", () => {
    const events: GameEvent[] = [
      {
        kind: "stat.changed",
        actor: "hero",
        stat: "stamina",
        delta: -6,
        value: 34,
        reason: "the road",
      },
      {
        kind: "inventory.changed",
        actor: "hero",
        item: "fantasy.core:bread",
        delta: -1,
        quantity: 1,
      },
    ];
    expect(transcribe(events).map((line) => line.text)).toEqual([
      "-6 stamina (the road)",
      "-1 bread",
    ]);
  });

  it("does not render a whole number as a decimal", () => {
    const events: GameEvent[] = [
      { kind: "stat.changed", actor: "h", stat: "hp", delta: 8, value: 8, reason: null },
    ];
    expect(transcribe(events)[0]?.text).toBe("+8 hp");
  });
});

describe("statusOf", () => {
  it("finds the standing line the frame ended on", () => {
    const status = statusOf(opening.events);
    expect(status?.place).toBe("Fenmoor");
    expect(status?.day).toBe(1);
  });

  it("is null for a frame that carried none", () => {
    expect(statusOf([{ kind: "narrate", text: "x", pause: false }])).toBeNull();
  });
});

describe("menuOf", () => {
  it("finds the options on offer", () => {
    const options = menuOf(opening.events);
    expect(options?.map((option) => option.prompt)).toContain("Take the north road");
  });

  it("is null when the frame offered none, so the last menu stands", () => {
    expect(menuOf(afterStep(2).events)).toBeNull();
  });
});
