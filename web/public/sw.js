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
 * What the shell can do without a network is therefore: load, say so, and
 * keep the save safe. That is the whole of it until the engine moves into the
 * tab (ADR-0005), at which point there is no server to be offline from.
 */

const CACHE = "mace-shell-v1";

self.addEventListener("install", (event) => {
  // The document itself, so a cold offline start has something to open.
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(["/", "/manifest.webmanifest"])),
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
  if (url.pathname.startsWith("/api/")) return;

  // A navigation offline gets the shell back, so the app opens and can say
  // what is wrong rather than showing the browser's error page.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put("/", copy));
          return response;
        })
        .catch(() => caches.match("/").then((hit) => hit ?? Response.error())),
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
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});
