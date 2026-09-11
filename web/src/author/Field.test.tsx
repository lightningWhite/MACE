/**
 * Repeat entries whose sub-steps bind into a nested sub-object.
 *
 * `mace.wizard.flow.plant` lets a repeat's sub-step bind past one segment —
 * `entries.combat.against` lands at `{combat: {against: [...]}}` inside the
 * entry, the same way `entities[{id}].combat.profile` nests on an ordinary
 * object. This checks the client's matching half: `assemble`/`plant` in
 * `Field.tsx` have to build that same nested shape before handing the entry
 * back, or an encounter entry's `combat.against` would land as a flat
 * `against` key the content model does not recognise.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Field } from "./Field";
import type { Step } from "./protocol";

const STEP: Step = {
  id: "table.entries",
  title: "What can happen?",
  help: "",
  binds: "encounterTables[{id}].entries",
  optional: true,
  field: {
    kind: "repeat",
    optional: true,
    interactive: true,
    hint: "",
    of: "entry",
    steps: [
      {
        id: "entry.id",
        title: "A short name for this entry",
        help: "",
        binds: "entries.id",
        optional: false,
        field: { kind: "text", optional: false, interactive: false, hint: "" },
      },
      {
        id: "entry.combatAgainst",
        title: "Who does the player fight?",
        help: "",
        binds: "entries.combat.against",
        optional: true,
        field: {
          kind: "multi-select",
          optional: false,
          interactive: false,
          hint: "",
          options: [{ value: "wolf", label: "Wolf", note: "", scope: "" }],
        },
      },
    ],
  },
  value: null,
  described: "—",
  answered: false,
  entries: [],
};

afterEach(cleanup);

describe("a repeat entry with a nested binding", () => {
  it("plants a multi-segment binding as a nested object", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(<Field step={STEP} onAnswer={onAnswer} busy={false} />);

    await user.click(screen.getByRole("button", { name: "Add an entry" }));
    await user.type(screen.getByLabelText("A short name for this entry"), "wolf-pack");
    await user.tab();

    const multi = screen.getByRole("checkbox") as HTMLInputElement;
    await user.click(multi);
    await user.click(screen.getByRole("button", { name: "Add it" }));

    expect(onAnswer).toHaveBeenCalledWith([
      { id: "wolf-pack", combat: { against: ["wolf"] } },
    ]);
  });
});

describe("editing an existing entry", () => {
  const withEntries: Step = {
    ...STEP,
    value: [{ id: "wolf-pack", combat: { against: ["wolf"] } }],
    entries: [
      {
        values: { id: "wolf-pack", combat: { against: ["wolf"] } },
        summary: "wolf-pack — fight: Wolf",
        pieces: {},
      },
    ],
  };

  it("opens seeded with what is already there, not a blank form", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(<Field step={withEntries} onAnswer={onAnswer} busy={false} />);

    await user.click(screen.getByRole("button", { name: "Edit entry 1" }));

    const name = screen.getByLabelText(
      "A short name for this entry",
    ) as HTMLInputElement;
    expect(name.value).toBe("wolf-pack");
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
  });

  it("replaces the entry in place rather than appending a new one", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(<Field step={withEntries} onAnswer={onAnswer} busy={false} />);

    await user.click(screen.getByRole("button", { name: "Edit entry 1" }));
    const name = screen.getByLabelText("A short name for this entry");
    await user.clear(name);
    await user.type(name, "bandit-camp");
    await user.click(screen.getByRole("button", { name: "Save it" }));

    expect(onAnswer).toHaveBeenCalledWith([
      { id: "bandit-camp", combat: { against: ["wolf"] } },
    ]);
  });
});

// ── A statblock's relative-value picker ─────────────────────────────────────

describe("a statblock with a value relative to the player", () => {
  const STAT_STEP: Step = {
    id: "entity.stats",
    title: "What is it made of?",
    help: "",
    binds: "entities[{id}].stats",
    optional: true,
    field: {
      kind: "stat-allocator",
      optional: true,
      interactive: true,
      hint: "",
      points: 0,
      stats: ["hitpoints"],
      core: {},
      playerStats: ["hitpoints", "strength"],
    },
    value: {
      hitpoints: {
        base: { relativeToPlayer: { stat: "hitpoints", factor: 3 } },
        max: 40,
      },
    },
    described: "hitpoints 3x player's hitpoints",
    answered: true,
    entries: [
      {
        stat: "hitpoints",
        base: null,
        max: 40,
        relativeBase: { stat: "hitpoints", factor: 3 },
        relativeMax: null,
      },
    ],
  };

  afterEach(cleanup);

  it("shows a factor and a stat picker instead of a plain number", () => {
    render(<Field step={STAT_STEP} onAnswer={vi.fn()} busy={false} />);

    expect(
      (screen.getByLabelText("hitpoints base factor") as HTMLInputElement).value,
    ).toBe("3");
    expect(
      (screen.getByLabelText("hitpoints base stat") as HTMLSelectElement).value,
    ).toBe("hitpoints");
    // The cap was authored as a plain number, so it keeps its own number box.
    expect(
      (screen.getByLabelText("hitpoints cap") as HTMLInputElement).value,
    ).toBe("40");
  });

  it("switches a relative base back to a fixed number", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(<Field step={STAT_STEP} onAnswer={onAnswer} busy={false} />);

    await user.click(screen.getByRole("button", { name: "fixed" }));

    expect(onAnswer).toHaveBeenCalledWith({
      hitpoints: { base: 0, max: 40 },
    });
  });

  it("switches a fixed cap to relative, offering the player's own stats", async () => {
    const user = userEvent.setup();
    const onAnswer = vi.fn();
    render(<Field step={STAT_STEP} onAnswer={onAnswer} busy={false} />);

    await user.click(screen.getByRole("button", { name: "relative" }));

    expect(onAnswer).toHaveBeenCalledWith({
      hitpoints: {
        base: { relativeToPlayer: { stat: "hitpoints", factor: 3 } },
        max: { relativeToPlayer: { stat: "hitpoints", factor: 1 } },
      },
    });
  });
});
