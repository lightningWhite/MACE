/**
 * The keys, which have to be the terminal's keys.
 *
 * A player who learns the fight in one front-end and finishes it in the other
 * should not have to learn them twice, so these mirror `keys_for` in
 * `mace/cli/play.py` — including the awkward cases it handles.
 */

import { describe, expect, it } from "vitest";

import { keysFor } from "./keys";
import { fight, terminalKeys } from "../test/wire";
import { isKind, type ResponsesOffered } from "../protocol";

function offered(): ResponsesOffered {
  const found = fight
    .flatMap((step) => step.frame.events)
    .filter((event): event is ResponsesOffered => isKind(event, "combat.responses"))
    .at(-1);
  if (found === undefined) throw new Error("no responses were recorded");
  return found;
}

describe("keysFor", () => {
  it("takes the first letter when it is free", () => {
    const bound = keysFor([
      { response: "dodge", label: "dodge" },
      { response: "parry", label: "parry" },
    ]);
    expect(bound.map((one) => one.key)).toEqual(["d", "p"]);
  });

  it("moves along the word when the obvious letter is taken", () => {
    const bound = keysFor([
      { response: "block", label: "block" },
      { response: "use:bread", label: "Bread" },
    ]);
    expect(bound.map((one) => one.key)).toEqual(["b", "r"]);
  });

  it("falls back to a digit when every letter is spoken for", () => {
    const bound = keysFor([
      { response: "a", label: "ab" },
      { response: "b", label: "ba" },
      { response: "c", label: "ab" },
    ]);
    expect(bound[2]?.key).toBe("3");
  });

  it("gives every real response its own key", () => {
    const bound = keysFor(offered().options);
    expect(new Set(bound.map((one) => one.key)).size).toBe(bound.length);
  });

  it("binds exactly what the terminal binds", () => {
    // Recorded from `keys_for` in `mace/cli/play.py` by
    // `tests/test_web_wire.py`. If the two rules drift apart, this is where
    // it shows up — including the case nobody would guess, where `Bread`
    // walks past `b` and `r` to land on `e`.
    const bound = Object.fromEntries(
      keysFor(offered().options).map((one) => [one.response, one.key]),
    );
    expect(bound).toEqual(terminalKeys);
  });

  it("binds the answers a player reaches for to their own initials", () => {
    const bound = new Map(
      keysFor(offered().options).map((one) => [one.response, one.key]),
    );
    expect(bound.get("dodge")).toBe("d");
    expect(bound.get("block")).toBe("b");
    expect(bound.get("parry")).toBe("p");
    expect(bound.get("strike")).toBe("s");
  });
});
