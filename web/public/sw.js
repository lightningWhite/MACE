/**
 * The offline shell.
 *
 * Hand-written rather than generated, because what it has to do is small and
 * a build-time precache manifest would be a dependency and a moving part to
 * keep a page loading. It caches what the page asks for as the page asks for
 * it: the first online visit fills the cache, and a later visit with no
 * network gets the shell back out of it.
 *
 * The API is deliberately never cached. A stale frame is a stale world — it
 * would show a player a menu that the session has already moved past, and
 * they would click it and be told no. Better to fail honestly and let the
 * client say it is offline.
 *
 * Everything else same-origin *is* cached, and in a static build that
 * includes the Pyodide runtime and the engine bundle. So the second visit to
 * a static deployment plays with no network at all: there is no server to be
 * offline from, which is what ADR-0005 was for.
 */

const CACHE = "mace-shell-v1";

/**
 * Where the app lives.
 *
 * The worker's own scope, not `/`: a project site on GitHub Pages is served
 * from `/<repo>/`, and a service worker that precached `/` there would cache
 * somebody else's page.
 */
const BASE = new URL("./", self.registration.scope);

self.addEventListener("install", (event) => {
  // The document itself, so a cold offline start has something to open.
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) =>
        cache.addAll([BASE.pathname, new URL("manifest.webmanifest", BASE).pathname]),
      )
      .catch(() => undefined),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith(new URL("api/", BASE).pathname)) return;

  // A navigation offline gets the shell back, so the app opens and can say
  // what is wrong rather than showing the browser's error page.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          void caches
            .open(CACHE)
            .then((cache) => cache.put(BASE.pathname, copy))
            .catch(() => undefined);
          return response;
        })
        .catch(() =>
          caches.match(BASE.pathname).then((hit) => hit ?? Response.error()),
        ),
    );
    return;
  }

  // Everything else the build serves: from the cache when it is there, and
  // filled in behind the player the first time they are online.
  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ??
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            // Not awaited, and allowed to fail: the runtime is fourteen
            // megabytes and a device that will not store it should still be
            // able to play, just not offline.
            void caches
              .open(CACHE)
              .then((cache) => cache.put(request, copy))
              .catch(() => undefined);
          }
          return response;
        }),
    ),
  );
});
