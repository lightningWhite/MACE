import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) throw new Error("no #root to mount on");

createRoot(root).render(
  <StrictMode>
    <App />
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
