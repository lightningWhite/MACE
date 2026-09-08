/**
 * The fight, on and off the clock.
 *
 * The frames here are a real reflex playthrough of the troll on the bridge,
 * so the windows, the tells and the counter matrix are the engine's own. What
 * these check is that the browser's window is neither kinder nor crueller
 * than the terminal's, because that is the one thing a second front-end must
 * never get wrong.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Action, CombatBegan, CombatTell, ResponsesOffered } from "../protocol";
import { isKind } from "../protocol";
import { Combat, type Fight } from "./Combat";
import { IDEAL, OPENS } from "./TimingBar";
import { fight } from "../test/wire";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/**
 * Pull the fight out of the recorded frames.
 *
 * `combat.begin` arrives once, on the frame that starts the fight; the tell
 * and the answers to it come with every exchange. So this takes the first of
 * the one and the last of the others, which is exactly what the client does.
 */
function recorded(): Fight {
  const events = fight.flatMap((step) => step.frame.events);

  const began = events.find((event): event is CombatBegan =>
    isKind(event, "combat.begin"),
  );
  const tell = events
    .filter((event): event is CombatTell => isKind(event, "combat.tell"))
    .at(-1);
  const responses = events
    .filter((event): event is ResponsesOffered => isKind(event, "combat.responses"))
    .at(-1);

  if (began === undefined || tell === undefined || responses === undefined) {
    throw new Error("the recorded fight is missing its events");
  }
  const vitals = Object.fromEntries(began.combatants.map((one) => [one.actor, one.vital]));
  return { began, tell, responses, vitals, openedAt: 0 };
}

function show(fight: Fight, busy = false) {
  const onAnswer = vi.fn<(action: Action) => void>();
  render(
    <Combat fight={fight} onAnswer={onAnswer} busy={busy} staminaOf={40} />,
  );
  return onAnswer;
}

function tactical(fight: Fight): Fight {
  return { ...fight, began: { ...fight.began, mode: "tactical" } };
}

// ── The tell ──────────────────────────────────────────────────────────────────

describe("the tell", () => {
  it("is prose, and it is the loudest thing on the screen", () => {
    const fight = recorded();
    show(fight);
    const said = screen.getByText(fight.tell.text);
    expect(said.className).toBe("tell");
    expect(said.getAttribute("aria-live")).toBe("assertive");
  });

  it("names the move when the player has learned to read it", () => {
    const fight = recorded();
    show({ ...fight, tell: { ...fight.tell, type: "overhead" } });
    expect(screen.getByText("(overhead)")).toBeTruthy();
  });

  it("says nothing about a tell that was not legible", () => {
    const fight = recorded();
    show({ ...fight, tell: { ...fight.tell, type: "" } });
    expect(screen.queryByText(/^\(/)).toBeNull();
  });

  it("names who is swinging", () => {
    show(recorded());
    expect(screen.getByRole("heading", { name: /Gorm/ })).toBeTruthy();
  });
});

describe("a combatant's vital pool", () => {
  it("draws a bar for the foe, seeded from combat.begin", () => {
    const fight = recorded();
    show(fight);
    const foe = fight.began.combatants.find((one) => one.side === "enemy");
    if (foe === undefined) throw new Error("the recorded fight has no foe");
    const meter = screen.getByRole("meter", { name: new RegExp(foe.name) });
    expect(meter.getAttribute("aria-valuenow")).toBe(String(Math.round(foe.vital.value)));
  });

  it("reads from the running vitals, not the opening one, once it changes", () => {
    const fight = recorded();
    const foe = fight.began.combatants.find((one) => one.side === "enemy");
    if (foe === undefined) throw new Error("the recorded fight has no foe");
    const wounded = { ...fight, vitals: { ...fight.vitals, [foe.actor]: { ...foe.vital, value: 1 } } };
    show(wounded);
    const meter = screen.getByRole("meter", { name: new RegExp(foe.name) });
    expect(meter.getAttribute("aria-valuenow")).toBe("1");
  });
});

// ── The window ────────────────────────────────────────────────────────────────

describe("the window", () => {
  it("marks the spot the engine actually rewards", () => {
    // `precision_of` puts the sweet spot three quarters of the way through,
    // falling off half a window either side. A bar that marked a different
    // spot would be worse than no bar.
    expect(IDEAL).toBeCloseTo(0.75, 5);
    expect(OPENS).toBeCloseTo(0.25, 5);

    const { container } = render(
      <Combat fight={recorded()} onAnswer={() => {}} busy={false} staminaOf={40} />,
    );
    const ideal = container.querySelector<HTMLElement>(".timing-ideal");
    expect(ideal?.style.insetInlineStart).toBe("75%");
    const sweet = container.querySelector<HTMLElement>(".timing-sweet");
    expect(sweet?.style.insetInlineStart).toBe("25%");
  });

  it("is absent in tactical mode, and nothing else changes", () => {
    const fight = recorded();
    const { container } = render(
      <Combat
        fight={tactical(fight)}
        onAnswer={() => {}}
        busy={false}
        staminaOf={40}
      />,
    );
    expect(container.querySelector(".timing")).toBeNull();
    expect(screen.getByText(fight.tell.text)).toBeTruthy();
    expect(screen.getByRole("button", { name: /dodge/ })).toBeTruthy();
  });

  it("counts down in numbers for a reader who asked for less motion", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const { container } = render(
      <Combat fight={recorded()} onAnswer={() => {}} busy={false} staminaOf={40} />,
    );
    expect(container.querySelector(".timing")).toBeNull();
    expect(screen.getByRole("timer").textContent).toMatch(/^\d+\.\ds$/);
  });
});

// ── Answering ─────────────────────────────────────────────────────────────────

describe("answering", () => {
  it("sends how long the player took", async () => {
    const user = userEvent.setup();
    const fight = recorded();
    const onAnswer = show({ ...fight, openedAt: performance.now() });

    await user.click(screen.getByRole("button", { name: /dodge/ }));
    const sent = onAnswer.mock.calls[0]?.[0];
    expect(sent?.kind).toBe("combat.input");
    expect(sent).toHaveProperty("response", "dodge");
    expect(sent).toHaveProperty("elapsedMs");
  });

  it("sends no time at all in tactical mode", async () => {
    const user = userEvent.setup();
    const onAnswer = show(tactical(recorded()));

    await user.click(screen.getByRole("button", { name: /parry/ }));
    expect(onAnswer).toHaveBeenCalledWith({
      kind: "combat.input",
      response: "parry",
    });
  });

  it("takes the answer from the keyboard, the way the terminal does", async () => {
    const user = userEvent.setup();
    const onAnswer = show(tactical(recorded()));

    await user.keyboard("b");
    expect(onAnswer).toHaveBeenCalledWith({
      kind: "combat.input",
      response: "block",
    });
  });

  it("does nothing while an answer is already in flight", async () => {
    const user = userEvent.setup();
    const onAnswer = show(tactical(recorded()), true);
    await user.click(screen.getByRole("button", { name: /dodge/ }));
    expect(onAnswer).not.toHaveBeenCalled();
  });
});

describe("a window that runs out", () => {
  it("spends the whole of it, and takes the blow on purpose", () => {
    // The terminal spends the window on a wrong key as readily as a right
    // one. A browser that quietly gave the time back would be a kinder window
    // than the terminal's, and the two have to be the same fight.
    vi.useFakeTimers();
    const fight = recorded();
    const onAnswer = show({ ...fight, openedAt: performance.now() });

    vi.advanceTimersByTime(fight.tell.windowMs + 50);

    expect(onAnswer).toHaveBeenCalledWith({
      kind: "combat.input",
      response: "recover",
      elapsedMs: fight.tell.windowMs,
    });
  });

  it("only gives up once", () => {
    vi.useFakeTimers();
    const fight = recorded();
    const onAnswer = show({ ...fight, openedAt: performance.now() });

    vi.advanceTimersByTime(fight.tell.windowMs * 3);
    expect(onAnswer).toHaveBeenCalledTimes(1);
  });
});

// ── What is being spent ───────────────────────────────────────────────────────

describe("the resources", () => {
  it("shows stamina against the cap the character sheet gave", () => {
    const fight = recorded();
    show(fight);
    const meter = screen.getByRole("meter", { name: "stamina" });
    expect(meter.getAttribute("aria-valuemax")).toBe("40");
    expect(meter.getAttribute("aria-valuenow")).toBe(
      String(Math.round(fight.responses.stamina)),
    );
  });

  it("shows momentum as the multiplier the wire carries, not as a bar", () => {
    // `combat.responses` sends 1.0 through 1.5. A bar would need a ceiling
    // the wire does not state.
    const fight = recorded();
    show({ ...fight, responses: { ...fight.responses, momentum: 1.15 } });
    expect(screen.getByText(/momentum ×1.15/)).toBeTruthy();
  });
});

describe("the training wheels", () => {
  it("show what beats what, until the player turns them off", async () => {
    const user = userEvent.setup();
    const fight = recorded();
    show(fight);

    const row = fight.began.matrix[0];
    expect(row).toBeDefined();
    expect(screen.getByText(row!.type)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /Hide what beats what/ }));
    expect(screen.queryByText(row!.type)).toBeNull();
  });
});
