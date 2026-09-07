import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { Studio } from "./author/Studio";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) throw new Error("no #root to mount on");

// One build, two front-ends, and a fragment rather than a router: `#author`
// is the wizard and everything else is the game. A fragment because the other
// two ways cost something — a path needs the server to serve index.html for a
// URL it has no file for, which a static host on GitHub Pages will not do,
// and a router is a dependency for one decision. The wizard is only
// *answered* when somebody ran `mace author --web`, so a hosted game stays a
// game and nothing else.
const fragment = window.location.hash.replace(/^#\/?/, "");

// `#play/<id>` is a playthrough somebody else opened — in practice the
// wizard, handing over a playtest. It is still the game client and still an
// ordinary session; the only thing the fragment changes is that the client
// attaches to one instead of offering to start one.
const handed = /^play\/(.+)$/.exec(fragment)?.[1];

createRoot(root).render(
  <StrictMode>
    {fragment === "author" ? (
      <Studio />
    ) : handed === undefined ? (
      <App />
    ) : (
      <App playtest={decodeURIComponent(handed)} />
    )}
  </StrictMode>,
);

// The offline shell. Registered after the app is mounted and never awaited:
// a service worker that failed to register is a page without offline support,
// not a page that should refuse to load. Dev builds skip it, because a
// worker caching Vite's module graph makes every reload a lie.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js`)
      .catch(() => undefined);
  });
}
