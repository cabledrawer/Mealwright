/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

// The app's service worker (sync protocol 11.6). Written by hand, no library.
//
// What it does: keeps the app's own files (code, fonts, icons: `build` and `files`) and the
// start page in one cache named for this build, so the app opens with no connection.
// What it never does:
//   - touch anything under /api (so /api/v1/events and every API call go straight to the
//     network and nothing about the household is ever cached here);
//   - touch anything from another address (there is none; nothing is fetched elsewhere);
//   - call skipWaiting() or claim() or reload a page. A new version waits until every
//     window of the app is closed, so an update never takes over in the middle of shopping.
//     The next start opens the new version.
// PR 6's offline queue lives in IndexedDB, not here; the new version sends the old one's
// queue before showing the list (sync protocol 11.6).

import { build, files, version } from '$service-worker';
import { CACHE_PREFIX, SHELL, cacheName, handling } from '$lib/offline/rules';

const worker = self as unknown as ServiceWorkerGlobalScope;

const CACHE = cacheName(version);
const ASSETS = [...build, ...files];
const KNOWN = new Set(ASSETS);

worker.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      // "reload": ask the server, not the browser's own copy, so a new worker never keeps
      // an old file.
      await cache.addAll([SHELL, ...ASSETS].map((path) => new Request(path, { cache: 'reload' })));
    })()
  );
});

worker.addEventListener('activate', (event) => {
  // Only now, when no window of the old version is left, are its files deleted.
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) {
        if (key.startsWith(CACHE_PREFIX) && key !== CACHE) await caches.delete(key);
      }
    })()
  );
});

worker.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  const kind = handling(request, url, worker.location.origin, KNOWN);
  if (kind === 'network') return; // no respondWith: the browser goes to the network as usual

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const found = await cache.match(kind === 'shell' ? SHELL : url.pathname);
      return found ?? fetch(request);
    })()
  );
});
