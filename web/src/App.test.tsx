/**
 * The client, rendered.
 *
 * Every frame these tests feed it came out of the real engine, so what is
 * being checked is that the client draws what MACE actually sends — not what
 * a hand-written fixture wishes it sent.
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import {
  DeadSocket,
  LiveSocket,
  afterStep,
  fakeService,
  opening,
} from "./test/wire";

function stub(service: ReturnType<typeof fakeService>) {
  vi.stubGlobal("fetch", service.fetcher);
  vi.stubGlobal("WebSocket", DeadSocket);
}

/** Get past the opening screen and into the game. */
async function play(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /Farmhand/ }));
  await user.click(screen.getByRole("button", { name: "Begin" }));
  await screen.findByText(/You are a peasant/);
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// ── Before the first tick ─────────────────────────────────────────────────────

describe("the opening", () => {
  it("offers the worlds and the people you could be", async () => {
    stub(fakeService());
    render(<App />);

    expect(await screen.findByRole("button", { name: /Farmhand/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Poacher/ })).toBeTruthy();
  });

  it("shows what a background grants, in the engine's own words", async () => {
    stub(fakeService());
    render(<App />);

    const farmhand = await screen.findByRole("button", { name: /Farmhand/ });
    expect(farmhand.textContent).toContain("strength +8");
    expect(farmhand.textContent).toContain("2 × bread");
  });

  it("will not begin until the question is answered", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);

    await screen.findByRole("button", { name: /Farmhand/ });
    expect(screen.getByRole("button", { name: "Begin" })).toHaveProperty(
      "disabled",
      true,
    );

    await user.click(screen.getByRole("button", { name: /Poacher/ }));
    expect(screen.getByRole("button", { name: "Begin" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("spends creation points without going past what is left", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);

    await user.click(await screen.findByRole("button", { name: /Farmhand/ }));
    const more = await screen.findByRole("button", { name: "more strength" });
    for (let click = 0; click < 16; click += 1) await user.click(more);

    // Fifteen points exist; the sixteenth click has nothing to spend.
    expect(screen.getByText("0 left")).toBeTruthy();
    expect(more).toHaveProperty("disabled", true);
  });

  it("says so when the service will not open a session", async () => {
    const user = userEvent.setup();
    stub(fakeService({ failOpen: "no game packs found" }));
    render(<App />);

    await user.click(await screen.findByRole("button", { name: /Farmhand/ }));
    await user.click(screen.getByRole("button", { name: "Begin" }));
    expect(await screen.findByText("no game packs found")).toBeTruthy();
  });
});

// ── Playing ───────────────────────────────────────────────────────────────────

describe("the game", () => {
  it("reads the opening prose and offers what may be done", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    expect(screen.getByRole("button", { name: /Take the north road/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Say goodbye to Hallam/ })).toBeTruthy();
  });

  it("appends what happens next rather than replacing it", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    await user.click(screen.getByRole("button", { name: /Take the north road/ }));
    await screen.findByText(/The journey stops:/);

    // The opening is still there: a transcript, not a teleprompter.
    expect(screen.getByText(/You are a peasant/)).toBeTruthy();
  });

  it("sends the choice the player clicked, by index", async () => {
    const user = userEvent.setup();
    const service = fakeService();
    stub(service);
    render(<App />);
    await play(user);

    await user.click(screen.getByRole("button", { name: /Take the north road/ }));
    await waitFor(() => expect(service.taken()).toBe(1));

    const acted = service.calls.filter((call) => call.path.endsWith("/actions"));
    expect(acted[0]?.body).toEqual({ kind: "choose", option: 2 });
  });

  it("shows an unavailable option, and why", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    await user.click(screen.getByRole("button", { name: /Take the north road/ }));
    await user.click(await screen.findByRole("button", { name: /Speak to the troll/ }));

    const toll = await screen.findByRole("button", { name: /Pay the toll/ });
    expect(toll).toHaveProperty("disabled", true);
    expect(toll.textContent).toContain("gold");
  });
});

// ── The panels ────────────────────────────────────────────────────────────────

describe("the panels", () => {
  it("draws the pools the game's rules named", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    const vital = opening.view.sheet.stats.find((gauge) => gauge.role === "vital");
    expect(vital).toBeDefined();
    const meter = screen.getByRole("meter", { name: vital!.stat });
    expect(meter.getAttribute("aria-valuenow")).toBe(String(Math.round(vital!.value)));
  });

  it("names what is in the pack", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    const pack = screen.getByRole("region", { name: "Pack" });
    for (const stack of opening.view.carried) {
      expect(within(pack).getByText(stack.name)).toBeTruthy();
    }
  });

  it("reads the journal's current stage", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    const journal = screen.getByRole("region", { name: "Journal" });
    const quest = opening.view.journal[0];
    expect(quest).toBeDefined();
    expect(within(journal).getByText(quest!.name)).toBeTruthy();
  });

  it("keeps a standing line, because the world runs whether you act or not", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    expect(screen.getByRole("contentinfo").textContent).toContain(
      "Day 1 · day · Fenmoor",
    );

    // It follows the player down the road rather than going stale.
    await user.click(screen.getByRole("button", { name: /Take the north road/ }));
    await waitFor(() =>
      expect(screen.getByRole("contentinfo").textContent).toContain(
        "The Old Bridge",
      ),
    );
  });
});

// ── The socket ────────────────────────────────────────────────────────────────

describe("a connection that holds", () => {
  it("sends actions down the socket rather than by request", async () => {
    const user = userEvent.setup();
    const service = fakeService();
    vi.stubGlobal("fetch", service.fetcher);
    vi.stubGlobal("WebSocket", LiveSocket);
    render(<App />);
    await play(user);

    expect(await screen.findByText("connected")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /Take the north road/ }));
    expect(await screen.findByText(/The journey stops:/)).toBeTruthy();

    expect(LiveSocket.last?.sent).toEqual([{ kind: "choose", option: 2 }]);
    expect(service.calls.some((call) => call.path.endsWith("/actions"))).toBe(false);
  });

  it("does not read the opening twice when the socket greets it", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", fakeService().fetcher);
    vi.stubGlobal("WebSocket", LiveSocket);
    render(<App />);
    await play(user);

    await screen.findByText("connected");
    // The greeting frame carries the opening prose the POST already rendered.
    expect(screen.getAllByText(/You are a peasant/)).toHaveLength(1);
  });
});

// ── When the socket dies ──────────────────────────────────────────────────────

describe("a connection that will not hold", () => {
  it("keeps playing over HTTP, and says that is what it is doing", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    expect(await screen.findByText(/playing over HTTP/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /Take the north road/ }));
    expect(await screen.findByText(/The journey stops:/)).toBeTruthy();
  });
});

// ── The save is the durability ────────────────────────────────────────────────

describe("the save", () => {
  it("is kept where a reload finds it", async () => {
    const user = userEvent.setup();
    stub(fakeService());
    render(<App />);
    await play(user);

    await waitFor(() =>
      expect(window.localStorage.getItem("mace.save")).not.toBeNull(),
    );
    const kept = JSON.parse(window.localStorage.getItem("mace.save")!) as {
      pack: string;
    };
    expect(kept.pack).toBe("peasants-quest");
  });

  it("is offered back on the next visit", async () => {
    window.localStorage.setItem(
      "mace.save",
      JSON.stringify({
        format: 1,
        pack: "peasants-quest",
        seed: "mace",
        packs: {},
        actions: [{ kind: "choose", prompt: "Take the north road" }],
      }),
    );
    stub(fakeService());
    render(<App />);

    expect(await screen.findByRole("button", { name: "Carry on" })).toBeTruthy();
    expect(screen.getByText(/after 1 action/)).toBeTruthy();
  });

  it("carries a playthrough on without re-reading the whole thing", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      "mace.save",
      JSON.stringify({
        format: 1,
        pack: "peasants-quest",
        seed: "mace",
        packs: {},
        actions: [],
      }),
    );
    stub(fakeService());
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Carry on" }));
    expect(await screen.findByText(/You are a peasant/)).toBeTruthy();
  });
});

// The recording has to reach a fight for the combat view's tests to have
// anything to stand on. Guarded here so the fixture cannot quietly stop.
it("the recording reaches a fight", () => {
  const kinds = afterStep(2).events.map((event) => event.kind);
  expect(kinds).toContain("combat.tell");
});
