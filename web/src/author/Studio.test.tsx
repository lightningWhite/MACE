/**
 * The wizard, rendered.
 *
 * Every screen these tests feed it came out of the real wizard, so what is
 * being checked is that the client draws what `mace.wizard.studio` actually
 * sends — including that a picker arrives with `Bridge Troll` on it rather
 * than a text box the author has to type `fantasy.core:bridge-troll` into.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Studio } from "./Studio";
import { fakeStudio } from "../test/authorWire";

function stub(studio: ReturnType<typeof fakeStudio>) {
  vi.stubGlobal("fetch", studio.fetcher);
}

/** Open the task list and wait for it. */
async function opened() {
  render(<Studio />);
  await screen.findByText("A Peasant's Quest");
}

/** Walk into the world map's section, then into Fenmoor. */
async function intoFenmoor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /World map/ }));
  await user.click(await screen.findByRole("button", { name: "Open Fenmoor" }));
  await screen.findByLabelText(/What is this place called/);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ── The task list ─────────────────────────────────────────────────────────────

describe("the task list", () => {
  it("says where the pack stands before anything is opened", async () => {
    stub(fakeStudio());
    await opened();

    expect(screen.getByText(/% complete/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /World map/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Game setup/ })).toBeTruthy();
  });

  it("marks a section's state in a word as well as a glyph", async () => {
    stub(fakeStudio());
    await opened();

    // The accessible name carries the state; the ✓ is decorative beside it.
    expect(screen.getByRole("button", { name: /World map — done/ })).toBeTruthy();
  });

  it("says nothing about a wizard that is not answering", async () => {
    stub(fakeStudio({ absent: true }));
    render(<Studio />);
    expect(await screen.findByText(/not found/)).toBeTruthy();
  });
});

// ── A section ─────────────────────────────────────────────────────────────────

describe("a section", () => {
  it("lists what it holds", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();

    await user.click(screen.getByRole("button", { name: /World map/ }));
    expect(await screen.findByRole("button", { name: "Open Fenmoor" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open The North Road" })).toBeTruthy();
  });

  it("makes a new one from as little as its name", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();

    await user.click(screen.getByRole("button", { name: /World map/ }));
    await user.type(
      await screen.findByLabelText(/What is the new one called/),
      "The Long Moor",
    );
    await user.click(screen.getByRole("button", { name: "Make it" }));

    const made = studio.calls.find((call) => call.method === "POST");
    expect(made?.body).toEqual({
      name: "The Long Moor",
      section: "world",
      answers: {},
    });
    // And it opens what it made, rather than dropping the author back on a list.
    expect(
      await screen.findByRole("heading", { name: "The Long Moor" }),
    ).toBeTruthy();
  });

  it("keeps the form when the wizard refuses a name", async () => {
    const user = userEvent.setup();
    stub(fakeStudio({ refuse: "`fenmoor` is already there" }));
    await opened();

    await user.click(screen.getByRole("button", { name: /World map/ }));
    await user.type(
      await screen.findByLabelText(/What is the new one called/),
      "Fenmoor",
    );
    await user.click(screen.getByRole("button", { name: "Make it" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(
      /already there/,
    );
    expect(screen.getByRole("button", { name: "Make it" })).toBeTruthy();
  });

  it("can go back to the task list", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();

    await user.click(screen.getByRole("button", { name: /World map/ }));
    await user.click(await screen.findByRole("button", { name: /back/ }));
    expect(await screen.findByRole("button", { name: /Characters/ })).toBeTruthy();
  });
});

// ── One object ────────────────────────────────────────────────────────────────

describe("one object", () => {
  it("draws every step of the flow, with its answer", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoFenmoor(user);

    const name = screen.getByLabelText(/What is this place called/);
    expect((name as HTMLInputElement).value).toBe("Fenmoor");
    expect(screen.getByLabelText(/Which region/)).toBeTruthy();
  });

  it("offers a reference as a list, never as a text box", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoFenmoor(user);

    const region = screen.getByLabelText(/Which region/);
    expect(region.tagName).toBe("SELECT");
    expect(
      within(region as HTMLSelectElement).getByRole("option", {
        name: /The Lowlands/,
      }),
    ).toBeTruthy();
  });

  it("writes a picked reference rather than a typed one", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoFenmoor(user);

    await user.selectOptions(
      screen.getByLabelText(/Which region/),
      "the-marches",
    );

    const answered = studio.calls.find((call) => call.path.endsWith("/answers"));
    expect(answered?.body).toEqual({
      collection: "locations",
      object: "fenmoor",
      step: "location.region",
      value: "the-marches",
    });
  });

  it("sends a cleared field as nothing, not as an empty string", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoFenmoor(user);

    await user.selectOptions(screen.getByLabelText(/Which region/), "");

    const answered = studio.calls.find((call) => call.path.endsWith("/answers"));
    expect((answered?.body as { value: unknown }).value).toBeNull();
  });

  it("does not send an answer the author did not change", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoFenmoor(user);

    await user.click(screen.getByLabelText(/What is this place called/));
    await user.tab();

    expect(studio.calls.some((call) => call.path.endsWith("/answers"))).toBe(
      false,
    );
  });

  it("shows a field it cannot collect rather than hiding it", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoFenmoor(user);

    // `exits` is a repeat, which is built one entry at a time.
    expect(screen.getByText(/cannot do that yet/)).toBeTruthy();
    expect(screen.getByText("repeat")).toBeTruthy();
  });
});

// ── Saving ────────────────────────────────────────────────────────────────────

describe("saving", () => {
  it("says which files it wrote", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();

    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Saved locations\.yml/)).toBeTruthy();
  });
});
