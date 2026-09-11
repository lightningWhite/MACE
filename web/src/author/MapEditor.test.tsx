/**
 * The map editor's drill-down.
 *
 * A place naming another via `submapOf` never gets a pin of its own on the
 * world canvas — it belongs on its hub's own small canvas instead. These
 * check the three things that make that true rather than a nice idea: the
 * world canvas actually excludes it, a hub actually offers a way in, and the
 * scoped canvas actually shows what it should.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { MapEditor } from "./MapEditor";
import type { Atlas } from "./protocol";

const ATLAS: Atlas = {
  places: [
    { id: "home", name: "Home", x: 0, y: 0, exits: ["castle"], region: null, submapOf: null },
    {
      id: "castle",
      name: "The Castle",
      x: 100,
      y: 0,
      exits: ["home"],
      region: null,
      submapOf: null,
    },
    {
      id: "dungeon",
      name: "The Dungeon",
      x: 0,
      y: 20,
      exits: [],
      region: null,
      submapOf: "castle",
    },
  ],
  roads: [
    { id: "road", name: "The Road", from: "home", to: "castle", ticks: 3, bidirectional: true },
  ],
  regions: [],
};

interface Call {
  path: string;
  method: string;
  body: unknown;
}

/** A fake wizard that only knows how to draw and edit `ATLAS`. */
function stubMap(): { calls: Call[] } {
  const calls: Call[] = [];
  const fetcher = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const path = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body === undefined ? null : JSON.parse(String(init.body));
    calls.push({ path, method, body });
    const reply = (payload: unknown, status = 200) =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { "content-type": "application/json" },
      });
    if (path.endsWith("/map")) return reply(ATLAS);
    if (path.endsWith("/answers")) return reply({});
    if (path.includes("/objects/")) return reply({}, 201);
    if (path.includes("/roads")) return reply({}, 201);
    return reply({ detail: `no route for ${path}` }, 404);
  };
  vi.stubGlobal("fetch", fetcher);
  return { calls };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("never draws an interior place on the world canvas", async () => {
  stubMap();
  render(<MapEditor onOpen={() => {}} onChanged={() => {}} busy={false} />);

  expect(await screen.findByText("The Castle")).toBeTruthy();
  expect(screen.queryByText("The Dungeon")).toBeNull();
});

it("offers a way into a hub's interior", async () => {
  stubMap();
  render(<MapEditor onOpen={() => {}} onChanged={() => {}} busy={false} />);

  await screen.findByText("The Castle");
  expect(
    screen.getByRole("button", { name: "Open the small map inside The Castle" }),
  ).toBeTruthy();
});

it("scopes the canvas to a hub's places once you open it", async () => {
  const user = userEvent.setup();
  stubMap();
  render(<MapEditor onOpen={() => {}} onChanged={() => {}} busy={false} />);

  await screen.findByText("The Castle");
  await user.click(
    screen.getByRole("button", { name: "Open the small map inside The Castle" }),
  );

  expect(await screen.findByText("The Dungeon")).toBeTruthy();
  expect(await screen.findByText("The Castle")).toBeTruthy();
  expect(screen.queryByText("Home")).toBeNull();
  expect(screen.getByRole("button", { name: "back to the world map" })).toBeTruthy();
});

it("links a new room to its hub in the same authoring intention", async () => {
  const user = userEvent.setup();
  const { calls } = stubMap();
  render(<MapEditor onOpen={() => {}} onChanged={() => {}} busy={false} />);

  await screen.findByText("The Castle");
  await user.click(
    screen.getByRole("button", { name: "Open the small map inside The Castle" }),
  );

  await user.type(
    screen.getByLabelText("Name a new place inside this hub"),
    "The Armory",
  );
  await user.click(screen.getByRole("button", { name: "add" }));

  const made = calls.find((call) => call.path.includes("/objects/locations"));
  expect(made?.body).toEqual({
    name: "The Armory",
    section: null,
    answers: { "location.submapOf": "castle" },
  });
});
