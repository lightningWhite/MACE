/**
 * The cascade's dependent asks.
 *
 * `mace.wizard.studio` resolves every ask's options against the whole
 * catalog before any question is answered, so a `stage` ask arrives holding
 * every quest's stages at once, each tagged with the quest it came from. This
 * checks the client's half of the deal: it narrows that list down to the
 * quest an author already picked, rather than showing every stage of every
 * quest until the author gets there.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Cascade } from "./Cascade";
import type { Vocabulary } from "./protocol";

const VOCABULARY: Vocabulary = {
  conditions: [
    {
      tag: "questStage",
      label: "A quest has reached a stage",
      group: "The story",
      help: "",
      bare: false,
      asks: [
        {
          key: "quest",
          title: "Which quest?",
          help: "",
          default: null,
          dependsOn: "",
          field: {
            kind: "select",
            optional: false,
            interactive: false,
            hint: "",
            options: [
              { value: "the-summons", label: "The Summons", note: "", scope: "" },
              { value: "the-heist", label: "The Heist", note: "", scope: "" },
            ],
          },
        },
        {
          key: "stage",
          title: "Which stage?",
          help: "",
          default: null,
          dependsOn: "quest",
          field: {
            kind: "select",
            optional: false,
            interactive: false,
            hint: "",
            options: [
              {
                value: "set-out",
                label: "set out",
                note: "The Summons",
                scope: "the-summons",
              },
              {
                value: "case-the-vault",
                label: "case the vault",
                note: "The Heist",
                scope: "the-heist",
              },
            ],
          },
        },
      ],
    },
  ],
  effects: [],
};

function stub() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/vocabulary")) {
        return new Response(JSON.stringify(VOCABULARY), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: `no route for ${path}` }), {
        status: 404,
      });
    }),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function opened(user: ReturnType<typeof userEvent.setup>) {
  render(<Cascade kind="conditions" onBuilt={() => {}} onCancel={() => {}} />);
  await user.click(
    await screen.findByRole("button", { name: /A quest has reached a stage/ }),
  );
  await screen.findByLabelText("Which stage?");
}

describe("a dependent ask", () => {
  it("offers nothing until the ask it depends on is answered", async () => {
    stub();
    const user = userEvent.setup();
    await opened(user);

    const stage = screen.getByLabelText("Which stage?") as HTMLSelectElement;
    expect(stage.options.length).toBe(1); // just "— nothing —"
  });

  it("narrows to the quest already chosen", async () => {
    stub();
    const user = userEvent.setup();
    await opened(user);

    await user.selectOptions(screen.getByLabelText("Which quest?"), "the-heist");

    const stage = screen.getByLabelText("Which stage?") as HTMLSelectElement;
    const labels = Array.from(stage.options).map((option) => option.textContent);
    expect(labels.some((one) => one?.startsWith("case the vault"))).toBe(true);
    expect(labels.some((one) => one?.startsWith("set out"))).toBe(false);
  });

  it("switches its offer when the quest answer changes", async () => {
    stub();
    const user = userEvent.setup();
    await opened(user);

    await user.selectOptions(screen.getByLabelText("Which quest?"), "the-heist");
    await user.selectOptions(screen.getByLabelText("Which quest?"), "the-summons");

    const stage = screen.getByLabelText("Which stage?") as HTMLSelectElement;
    const labels = Array.from(stage.options).map((option) => option.textContent);
    expect(labels.some((one) => one?.startsWith("set out"))).toBe(true);
    expect(labels.some((one) => one?.startsWith("case the vault"))).toBe(false);
  });
});
