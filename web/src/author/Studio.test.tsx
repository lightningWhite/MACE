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

  it("lists a repeat's entries and lets one be taken out", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoFenmoor(user);

    expect(screen.getByText(/to: traders-post/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Remove exit 1" }));

    const answered = studio.calls.find((call) => call.path.endsWith("/answers"));
    const body = answered?.body as { step: string; value: unknown[] };
    expect(body.step).toBe("location.exits");
    expect(body.value).toHaveLength(1);
  });

  it("builds a repeat entry from the flow the wizard sent for one", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoFenmoor(user);

    await user.click(screen.getByRole("button", { name: "Add a exit" }));
    await user.selectOptions(
      await screen.findByLabelText(/Where does it lead/),
      "troll-bridge",
    );
    await user.click(screen.getByRole("button", { name: "Add it" }));

    const answered = studio.calls.find((call) => call.path.endsWith("/answers"));
    const body = answered?.body as { value: Array<Record<string, unknown>> };
    expect(body.value[body.value.length - 1]).toEqual({ to: "troll-bridge" });
  });
});

// ── The cascade ───────────────────────────────────────────────────────────────

describe("the cascade", () => {
  /** Open the troll's scene, where the conditions and effects live. */
  async function intoTheScene(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: /Scenes/ }));
    await user.click(await screen.findByRole("button", { name: "Open talk to gorm" }));
    await screen.findByText(/Add a condition/);
  }

  it("says what a condition means, in English, before anything is built", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoTheScene(user);

    // Once in the list of conditions, once in the "now:" reading under it.
    expect(screen.getAllByText(/Gorm is not flagged/)).toHaveLength(2);
  });

  it("offers the vocabulary grouped, and never as a syntax lesson", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoTheScene(user);

    await user.click(screen.getByRole("button", { name: "Add a condition" }));
    expect(await screen.findByText(/What should this depend on/)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Something somebody is carrying/ }),
    ).toBeTruthy();
    expect(screen.getByText("The player")).toBeTruthy();
  });

  it("asks the recipe's own questions, with the pack's things on them", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoTheScene(user);

    await user.click(screen.getByRole("button", { name: "Add a condition" }));
    await user.click(
      await screen.findByRole("button", { name: /Something somebody is carrying/ }),
    );

    const which = await screen.findByLabelText(/Which item/);
    expect(which.tagName).toBe("SELECT");
    expect(
      within(which as HTMLSelectElement).getByRole("option", { name: /Gold/ }),
    ).toBeTruthy();
  });

  it("lets the wizard build the content, and appends what came back", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoTheScene(user);

    await user.click(screen.getByRole("button", { name: "Add a condition" }));
    await user.click(
      await screen.findByRole("button", { name: /Something somebody is carrying/ }),
    );
    await user.selectOptions(
      await screen.findByLabelText(/Which item/),
      "fantasy.core:gold",
    );
    await user.click(screen.getByRole("button", { name: "Add it" }));

    // The client never assembles content itself: it posts the answers and
    // takes what `/build` gives back.
    const built = studio.calls.find((call) => call.path.endsWith("/build"));
    expect(built?.body).toMatchObject({
      kind: "conditions",
      tag: "hasItem",
      answers: { item: "fantasy.core:gold" },
    });

    const answered = studio.calls.find((call) => call.path.endsWith("/answers"));
    const body = answered?.body as { value: unknown[] };
    expect(body.value[body.value.length - 1]).toEqual({
      hasItem: { item: "fantasy.core:gold", qty: 10 },
    });
  });

  it("takes a condition back off", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoTheScene(user);

    await user.click(screen.getByRole("button", { name: /Remove Gorm is not/ }));
    const answered = studio.calls.find((call) => call.path.endsWith("/answers"));
    expect((answered?.body as { value: unknown }).value).toBeNull();
  });
});

// ── Statblocks ────────────────────────────────────────────────────────────────

describe("a statblock", () => {
  async function intoGorm(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: /Characters/ }));
    await user.click(await screen.findByRole("button", { name: "Open Gorm" }));
    await screen.findByLabelText("strength base");
  }

  it("shows named numbers, with their caps", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoGorm(user);

    expect((screen.getByLabelText("strength base") as HTMLInputElement).value).toBe(
      "85",
    );
    // Gorm names no cap of his own — he inherits one — so the box is empty
    // rather than inventing a number the author did not write.
    expect((screen.getByLabelText("strength cap") as HTMLInputElement).value).toBe(
      "",
    );
  });

  it("adds a stat nobody has invented yet", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoGorm(user);

    await user.type(screen.getByLabelText(/Which stat/), "hull-integrity");
    await user.click(screen.getByRole("button", { name: "Add a stat" }));

    const answered = studio.calls.find((call) => call.path.endsWith("/answers"));
    const body = answered?.body as { value: Record<string, unknown> };
    expect(body.value["hull-integrity"]).toEqual({ base: 0 });
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

// ── The map editor ────────────────────────────────────────────────────────────

describe("the map", () => {
  async function intoTheMap(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: /World map/ }));
    await screen.findByRole("img", { name: /A map of/ });
  }

  it("draws the places and roads the author has drawn", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoTheMap(user);

    const map = screen.getByRole("img", { name: /A map of/ });
    expect(within(map).getByText("Fenmoor")).toBeTruthy();
    // The road's length is on it, which is the thing an author is setting.
    expect(within(map).getByText("6")).toBeTruthy();
  });

  it("says which places nobody has put anywhere", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoTheMap(user);

    // The recording makes a place and never positions it. Saying so is the
    // point: a guess that looked like a choice would be the editor writing
    // content nobody asked for.
    expect(screen.getAllByText("not placed")).toHaveLength(1);
  });

  it("draws a road between two places in one call", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoTheMap(user);

    const map = screen.getByRole("img", { name: /A map of/ });
    await user.click(within(map).getByText("Fenmoor"));
    await user.click(within(map).getByText("The Old Bridge"));

    const drawn = studio.calls.find((call) => call.path.endsWith("/roads"));
    expect(drawn?.method).toBe("POST");
    expect(drawn?.body).toEqual({
      origin: "fenmoor",
      destination: "troll-bridge",
      ticks: 4,
      name: null,
    });
  });

  it("rubs a road out, ways onto it and all", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await intoTheMap(user);

    const map = screen.getByRole("img", { name: /A map of/ });
    await user.click(within(map).getByText("6"));
    await user.click(
      await screen.findByRole("button", { name: /Rub out The North Road/ }),
    );

    const gone = studio.calls.find((call) => call.method === "DELETE");
    expect(gone?.path).toContain("/roads/north-road");
  });

  it("still lists the places, because dragging is not the whole of authoring", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await intoTheMap(user);

    expect(screen.getByRole("button", { name: "Open Fenmoor" })).toBeTruthy();
  });
});

// ── The scene graph ───────────────────────────────────────────────────────────

describe("the scene graph", () => {
  it("says how many ways in there are, and whether anything is orphaned", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await user.click(await screen.findByRole("button", { name: /Scenes/ }));

    expect(await screen.findByText(/ways in, left to right/)).toBeTruthy();
    expect(screen.getByText(/Every scene can be reached/)).toBeTruthy();
  });

  it("names the orphans in the graph's own description", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await user.click(await screen.findByRole("button", { name: /Scenes/ }));

    // Not a colour: the label a screen reader gets is the same information.
    const graph = await screen.findByRole("img", { name: /scenes\./ });
    expect(graph.getAttribute("aria-label")).toMatch(/All of them can be reached/);
  });

  it("opens a scene when one is clicked", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    await opened();
    await user.click(await screen.findByRole("button", { name: /Scenes/ }));

    const graph = await screen.findByRole("img", { name: /scenes\./ });
    await user.click(within(graph).getByText("talk-to-gorm"));
    expect(
      studio.calls.some((call) => call.path.endsWith("/scenes/talk-to-gorm")),
    ).toBe(true);
  });
});

// ── The live preview ──────────────────────────────────────────────────────────

describe("the live preview", () => {
  it("shows what extends hid, and says it was inherited", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await user.click(await screen.findByRole("button", { name: /Characters/ }));
    await user.click(await screen.findByRole("button", { name: "Open Gorm" }));

    const card = await screen.findByLabelText(/as the engine sees it/);
    expect(within(card).getByText(/fantasy.core:bridge-troll/)).toBeTruthy();
    // Gorm writes only `strength`; hitpoints come from the troll.
    expect(within(card).getByText("hitpoints")).toBeTruthy();
    expect(within(card).getAllByText(/\(inherited\)/).length).toBeGreaterThan(0);
  });

  it("is not shown for the game manifest, which inherits nothing", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();
    await user.click(await screen.findByRole("button", { name: /Game setup/ }));
    await screen.findByLabelText(/What is this game called/);

    expect(screen.queryByLabelText(/as the engine sees it/)).toBeNull();
  });
});

// ── Playtest, and handing the pack on ─────────────────────────────────────────

describe("the playtest", () => {
  it("offers where to start, with the pickers already resolved", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();

    await user.click(screen.getByRole("button", { name: "Playtest" }));
    const where = await screen.findByLabelText(/Start where/);

    // The bridge is on the list because the wizard resolved it, not because
    // the client went looking for locations.
    expect(within(where).getByText("The Old Bridge")).toBeTruthy();
    expect(
      within(await screen.findByLabelText(/In what weather/)).getByRole("option", {
        name: /blizzard/,
      }),
    ).toBeTruthy();
  });

  it("hands the session to the game client rather than playing it here", async () => {
    const user = userEvent.setup();
    const studio = fakeStudio();
    stub(studio);
    const opening = vi.fn();
    vi.stubGlobal("open", opening);
    await opened();

    await user.click(screen.getByRole("button", { name: "Playtest" }));
    await screen.findByLabelText(/Start where/);
    await user.selectOptions(screen.getByLabelText(/Start where/), "troll-bridge");
    await user.click(screen.getByRole("button", { name: "Play it" }));

    const asked = studio.calls.find((call) => call.method === "POST" && call.path.endsWith("/playtest"));
    expect(asked?.body).toMatchObject({ startLocation: "troll-bridge" });
    expect(String(opening.mock.calls[0]?.[0])).toContain("#play/played");
  });

  it("says why it would not start, and stays on the form", async () => {
    const user = userEvent.setup();
    stub(fakeStudio({ refuse: "no such location `atlantis`" }));
    await opened();

    await user.click(screen.getByRole("button", { name: "Playtest" }));
    await screen.findByLabelText(/Start where/);
    await user.click(screen.getByRole("button", { name: "Play it" }));

    expect(await screen.findByText(/no such location/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Play it" })).toBeTruthy();
  });
});

describe("handing the pack on", () => {
  it("writes a file and says where it went", async () => {
    const user = userEvent.setup();
    stub(fakeStudio());
    await opened();

    await user.click(screen.getByRole("button", { name: "Export" }));
    expect(await screen.findByText(/peasants-quest-0.4.0.zip/)).toBeTruthy();
  });

  it("is the one thing errors stop, and saving is not", async () => {
    stub(fakeStudio());
    render(<Studio />);
    await screen.findByText("A Peasant's Quest");

    // The recorded pack has no errors, so the button is live. What matters is
    // that it is the *only* button tied to them: saving never is.
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(
      false,
    );
    const exporting = screen.getByRole("button", { name: "Export" });
    expect(exporting.getAttribute("title")).toContain("somebody else can open");
  });
});
