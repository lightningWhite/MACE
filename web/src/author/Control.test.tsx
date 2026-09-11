/**
 * The "+ create a new one" affordance on a picker.
 *
 * `allow_create` was already on the wire — the terminal wizard has driven it
 * from the start — but nothing here rendered it, so an author using the
 * browser had no way to make the thing a picker was missing without leaving
 * the field to go create it in its own section first. This checks the web
 * half now does what `mace.cli.author`'s `_create_inline` already does: ask
 * for a name, make the bare object, and hand the new id straight back to the
 * field that needed it.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Field } from "./Field";
import { fakeStudio, made } from "../test/authorWire";
import { isObject, type Step } from "./protocol";

if (!isObject(made.screen)) throw new Error("fixture `made` is not an object screen");
const madeId = made.screen.id;

const STEP: Step = {
  id: "location.region",
  title: "Which region is it in?",
  help: "",
  binds: "locations[{id}].region",
  optional: true,
  field: {
    kind: "select",
    optional: true,
    interactive: false,
    hint: "",
    options: [{ value: "fenmoor", label: "Fenmoor", note: "this pack", scope: "" }],
    allowCreate: "regions",
  },
  value: null,
  described: "—",
  answered: false,
  visible: true,
  entries: [],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a picker that can create what it is missing", () => {
  it("offers a way to make a new one", async () => {
    vi.stubGlobal("fetch", fakeStudio().fetcher);
    render(<Field step={STEP} onAnswer={vi.fn()} busy={false} />);

    expect(
      screen.getByRole("option", { name: "+ create a new one…" }),
    ).toBeTruthy();
  });

  it("asks for a name, makes it, and answers with the new id", async () => {
    const user = userEvent.setup();
    const { fetcher, calls } = fakeStudio();
    vi.stubGlobal("fetch", fetcher);
    const onAnswer = vi.fn();
    render(<Field step={STEP} onAnswer={onAnswer} busy={false} />);

    await user.selectOptions(
      screen.getByRole("combobox"),
      "+ create a new one…",
    );
    await user.type(screen.getByLabelText("The new one's name"), "Fenmoor");
    await user.click(screen.getByRole("button", { name: "Create" }));

    const post = calls.find(
      (call) => call.method === "POST" && call.path.includes("/objects/regions"),
    );
    expect(post?.body).toMatchObject({ name: "Fenmoor" });
    expect(onAnswer).toHaveBeenCalledWith(madeId);
  });

  it("does not offer creating anything when the field has no allowCreate", () => {
    vi.stubGlobal("fetch", fakeStudio().fetcher);
    const step: Step = { ...STEP, field: { ...STEP.field, allowCreate: null } };
    render(<Field step={step} onAnswer={vi.fn()} busy={false} />);

    expect(
      screen.queryByRole("option", { name: "+ create a new one…" }),
    ).toBeNull();
  });

  it("shows the wizard's own refusal rather than swallowing it", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      fakeStudio({ refuse: "`fenmoor` is already there" }).fetcher,
    );
    render(<Field step={STEP} onAnswer={vi.fn()} busy={false} />);

    await user.selectOptions(
      screen.getByRole("combobox"),
      "+ create a new one…",
    );
    await user.type(screen.getByLabelText("The new one's name"), "Fenmoor");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("`fenmoor` is already there")).toBeTruthy();
  });
});

const MIXED_STEP: Step = {
  ...STEP,
  field: {
    ...STEP.field,
    options: [
      { value: "fenmoor", label: "Fenmoor", note: "this pack", scope: "" },
      { value: "fantasy.core:the-lowlands", label: "The Lowlands", note: "fantasy.core", scope: "" },
    ],
  },
};

describe("a picker mixing the pack's own things with a library's", () => {
  it("shows only this pack's by default", () => {
    vi.stubGlobal("fetch", fakeStudio().fetcher);
    render(<Field step={MIXED_STEP} onAnswer={vi.fn()} busy={false} />);

    const select = screen.getByRole("combobox");
    expect(within(select).getByRole("option", { name: /Fenmoor/ })).toBeTruthy();
    expect(within(select).queryByRole("option", { name: /The Lowlands/ })).toBeNull();
    expect(screen.getByRole("button", { name: /1 more from elsewhere/ })).toBeTruthy();
  });

  it("reveals the rest on request", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", fakeStudio().fetcher);
    render(<Field step={MIXED_STEP} onAnswer={vi.fn()} busy={false} />);

    await user.click(screen.getByRole("button", { name: /more from elsewhere/ }));

    expect(
      within(screen.getByRole("combobox")).getByRole("option", { name: /The Lowlands/ }),
    ).toBeTruthy();
  });

  it("keeps an already-chosen library thing visible even while collapsed", () => {
    vi.stubGlobal("fetch", fakeStudio().fetcher);
    const step: Step = { ...MIXED_STEP, value: "fantasy.core:the-lowlands" };
    render(<Field step={step} onAnswer={vi.fn()} busy={false} />);

    expect(
      within(screen.getByRole("combobox")).getByRole("option", { name: /The Lowlands/ }),
    ).toBeTruthy();
  });

  it("does not collapse when the pack has none of its own to reduce to", () => {
    vi.stubGlobal("fetch", fakeStudio().fetcher);
    const step: Step = {
      ...MIXED_STEP,
      field: {
        ...MIXED_STEP.field,
        options: [MIXED_STEP.field.options![1]!],
      },
    };
    render(<Field step={step} onAnswer={vi.fn()} busy={false} />);

    expect(
      within(screen.getByRole("combobox")).getByRole("option", { name: /The Lowlands/ }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /more from elsewhere/ })).toBeNull();
  });
});
