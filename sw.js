const VERSION = "mrd-v2";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return; // let article images etc. pass through

  const isFeed = url.pathname.endsWith("/data/feed.json");
  const isShellDoc = url.pathname.endsWith("/") || url.pathname.endsWith("/index.html");

  if (isFeed || isShellDoc) {
    // Network-first: always try for fresh, fall back to cache offline.
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
  } else {
    // Cache-first for static assets.
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request))
    );
  }
});
