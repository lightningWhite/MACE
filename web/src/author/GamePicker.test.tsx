/**
 * Choosing which game to author, before there is a task list.
 *
 * `mace dev` opens with nothing picked, so this is the first screen an
 * author with a fresh process sees — a plain fetch stub is enough here
 * (rather than the recorded `authorWire` fixture), since none of this
 * exists in that recording yet.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GamePicker } from "./GamePicker";

const OPENED_FRAME = {
  pack: { id: "castle-quest", name: "Castle Quest", kind: "game", version: "0.1.0" },
  dirty: [],
  unreadable: [],
  desk: { name: "Castle Quest", percent: 0, problems: 0, errors: 0, tasks: [] },
  screen: null,
};

/** Thrown from a handler to make the stub answer with a refusal. */
class Refused {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {}
}

function stub(handlers: Record<string, (body: unknown) => unknown>) {
  vi.stubGlobal(
    "fetch",
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const path = String(input).replace(/^https?:\/\/[^/]+/, "");
      const key = `${init?.method ?? "GET"} ${path}`;
      const handler = handlers[key];
      if (handler === undefined) {
        return new Response(JSON.stringify({ detail: `no route for ${key}` }), {
          status: 404,
        });
      }
      const body = init?.body === undefined ? undefined : JSON.parse(String(init.body));
      try {
        return new Response(JSON.stringify(handler(body)), { status: 200 });
      } catch (error) {
        if (error instanceof Refused) {
          return new Response(JSON.stringify({ detail: error.detail }), {
            status: error.status,
          });
        }
        throw error;
      }
    },
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the game picker", () => {
  it("lists authorable games and opens one on click", async () => {
    const user = userEvent.setup();
    const onOpened = vi.fn();
    stub({
      "GET /api/author/games": () => ({
        games: [{ id: "castle-quest", name: "Castle Quest", path: "/x" }],
        open: null,
      }),
      "GET /api/author/libraries": () => ({ libraries: [] }),
      "POST /api/author/open": () => OPENED_FRAME,
    });

    render(<GamePicker onOpened={onOpened} />);
    await user.click(await screen.findByRole("button", { name: "Castle Quest" }));

    expect(onOpened).toHaveBeenCalledWith(OPENED_FRAME);
  });

  it("creates a new game with the libraries picked", async () => {
    const user = userEvent.setup();
    const onOpened = vi.fn();
    let posted: unknown = null;
    stub({
      "GET /api/author/games": () => ({ games: [], open: null }),
      "GET /api/author/libraries": () => ({
        libraries: [{ id: "fantasy.core", name: "Fantasy Core", path: "/y" }],
      }),
      "POST /api/author/games": (body) => {
        posted = body;
        return OPENED_FRAME;
      },
    });

    render(<GamePicker onOpened={onOpened} />);
    expect(await screen.findByText(/Nothing here yet/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "+ start a new game" }));
    await user.type(screen.getByLabelText("Its name"), "A New Quest");
    await user.click(screen.getByRole("checkbox", { name: "Fantasy Core" }));
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(posted).toEqual({ name: "A New Quest", requires: { "fantasy.core": "^0.1" } });
    expect(onOpened).toHaveBeenCalledWith(OPENED_FRAME);
  });

  it("shows the wizard's own refusal rather than swallowing it", async () => {
    const user = userEvent.setup();
    stub({
      "GET /api/author/games": () => ({
        games: [{ id: "castle-quest", name: "Castle Quest", path: "/x" }],
        open: null,
      }),
      "GET /api/author/libraries": () => ({ libraries: [] }),
      "POST /api/author/open": () => {
        throw new Refused(400, "this pack has unsaved changes");
      },
    });

    render(<GamePicker onOpened={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "Castle Quest" }));

    expect(await screen.findByText("this pack has unsaved changes")).toBeTruthy();
  });

  it("offers a way back only once there is somewhere to go back to", async () => {
    stub({
      "GET /api/author/games": () => ({ games: [], open: null }),
      "GET /api/author/libraries": () => ({ libraries: [] }),
    });

    render(<GamePicker onOpened={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Never mind" })).toBeNull();

    cleanup();
    render(<GamePicker onOpened={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Never mind" })).toBeTruthy();
  });
});
