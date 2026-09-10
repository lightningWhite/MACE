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
import { afterStep, fight, opening } from "./test/wire";

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

  it("collapses a run of identical leg text into one line and a count", () => {
    const leg = (n: number): GameEvent => ({
      kind: "travel.leg",
      route: "north-road",
      leg: n,
      of: 6,
      waypoint: null,
      text: "The barley gives out and the wood starts.",
    });
    const events: GameEvent[] = [leg(1), leg(2), leg(3), leg(4)];

    const lines = transcribe(events);

    expect(lines).toHaveLength(1);
    expect(lines[0]?.text).toBe("The barley gives out and the wood starts. (×4)");
    expect(lines[0]?.tone).toBe("journey");
  });

  it("does not collapse leg lines that actually differ", () => {
    const events: GameEvent[] = [
      { kind: "travel.leg", route: "r", leg: 1, of: 3, waypoint: null, text: "One." },
      { kind: "travel.leg", route: "r", leg: 2, of: 3, waypoint: null, text: "Two." },
      { kind: "travel.leg", route: "r", leg: 3, of: 3, waypoint: null, text: "One." },
    ];

    const text = transcribe(events).map((line) => line.text);
    expect(text).toEqual(["One.", "Two.", "One."]);
  });

  it("does not let a repeated line elsewhere in the stream count toward a run", () => {
    const events: GameEvent[] = [
      { kind: "travel.leg", route: "r", leg: 1, of: 2, waypoint: null, text: "Same." },
      { kind: "narrate", text: "Something happens.", pause: false },
      { kind: "travel.leg", route: "r", leg: 2, of: 2, waypoint: null, text: "Same." },
    ];

    const text = transcribe(events).map((line) => line.text);
    expect(text).toEqual(["Same.", "Something happens.", "Same."]);
  });

  it("never collapses repetition outside a journey — that is still two things said", () => {
    const events: GameEvent[] = [
      { kind: "narrate", text: "The elder nods.", pause: false },
      { kind: "narrate", text: "The elder nods.", pause: false },
    ];

    const text = transcribe(events).map((line) => line.text);
    expect(text).toEqual(["The elder nods.", "The elder nods."]);
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

describe("an exchange", () => {
  /**
   * Every exchange the recorded reflex fight resolved, as lines.
   *
   * One `fighting` flag shared across every frame, the way the client's own
   * ref is: the recording's fight spans several frames, and whether a frame
   * is mid-fight is state carried forward, not something one frame says on
   * its own.
   */
  function lines() {
    const fighting = { current: false };
    return fight
      .flatMap((step) => transcribe(step.frame.events, fighting))
      .map((one) => one.text);
  }

  it("names the result and the read, not the arithmetic", () => {
    // The recording reads the first tell right and the second one wrong.
    const said = lines();
    expect(said).toContain(
      "Clean counter — you read it, perfectly timed. Your opening lands for 3.7.",
    );
    expect(
      said.some((one) => one.startsWith("Caught square — you misread it,")),
    ).toBe(true);
  });

  it("says what a blow cost", () => {
    expect(lines().some((one) => one.includes("You take 13.7."))).toBe(true);
  });

  it("names who the fight is with", () => {
    expect(lines()).toContain("Fighting: Gorm");
  });

  it("does not also print the bare pool number combat.resolve already named", () => {
    // The recording's mid-fight frames carry a `stat.changed` for both
    // fighters' vital pool alongside `combat.resolve` — the terminal drops
    // the former on purpose, and so should this.
    expect(lines().some((one) => /^[-+]\d/.test(one))).toBe(false);
  });

  it("stops swallowing pool changes once the fight is over", () => {
    const fighting = { current: false };
    transcribe(
      [{ kind: "combat.begin", combat: "c", mode: "reflex", combatants: [], canFlee: true, matrix: [] }],
      fighting,
    );
    transcribe(
      [{ kind: "combat.end", combat: "c", outcome: "won", exchanges: 1, spoils: [] }],
      fighting,
    );
    const after = transcribe(
      [{ kind: "stat.changed", actor: "hero", stat: "stamina", delta: 4, value: 20, reason: null }],
      fighting,
    );
    expect(after.map((one) => one.text)).toEqual(["+4 stamina"]);
  });

  it("uses the words the terminal uses", () => {
    const events: GameEvent[] = [
      {
        kind: "combat.resolve",
        combat: "c",
        exchange: 1,
        attacker: "a",
        defender: "d",
        move: "m",
        response: "parry",
        read: "correct",
        result: "absorbed",
        precision: 0.7,
        damageTaken: 0,
        damageDealt: 0,
        critical: false,
        momentum: 1,
        stamina: 20,
        feint: false,
      },
    ];
    expect(transcribe(events)[0]?.text).toBe(
      "Taken on the guard — you read it, well timed.",
    );
  });

  it("owns up to a feint the player fell for", () => {
    const events: GameEvent[] = [
      {
        kind: "combat.resolve",
        combat: "c",
        exchange: 1,
        attacker: "a",
        defender: "d",
        move: "m",
        response: "block",
        read: "wrong",
        result: "clean",
        precision: 0.1,
        damageTaken: 4,
        damageDealt: 0,
        critical: false,
        momentum: 1,
        stamina: 20,
        feint: true,
      },
    ];
    expect(transcribe(events)[0]?.text).toContain("It was a feint.");
  });

  it("says how a fight ended, in the terminal's words", () => {
    const events: GameEvent[] = [
      { kind: "combat.end", combat: "c", outcome: "fled", exchanges: 3, spoils: [] },
    ];
    expect(transcribe(events)[0]?.text).toBe(
      "You are away, and it is behind you.",
    );
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
