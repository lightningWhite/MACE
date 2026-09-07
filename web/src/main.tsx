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
const authoring = window.location.hash.replace(/^#\/?/, "") === "author";

createRoot(root).render(
  <StrictMode>{authoring ? <Studio /> : <App />}</StrictMode>,
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
