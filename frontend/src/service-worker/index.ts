// The app's service worker (sync protocol 11.6). Written by hand, no library.
//
// What it does: keeps the app's own files (code, fonts, icons: `build` and `files`) and the
// start page in one cache named for this build, so the app opens with no connection.
// What it never does:
//   - touch anything under /api (so /api/v1/events and every API call go straight to the
//     network and nothing about the household is ever cached here);
//   - touch anything from another address (there is none; nothing is fetched elsewhere);
//   - call skipWaiting() or reload a page. A new version waits until every window of the app
//     is closed, so an update never takes over in the middle of shopping. The next start opens
//     the new version.
//   - call clients.claim() for an update. Only the very first worker on a device (no older
//     version's cache at activate AND no active worker at install) takes the page that installed it, once its files are on the device, so
//     that first page also works with no connection. Nothing reloads.
// PR 6's offline queue lives in IndexedDB, not here; the new version sends the old one's
// queue before showing the list (sync protocol 11.6).

import { self as worker } from '$app/service-worker';
import { version } from '$app/env';
import { assets, immutable } from '$app/manifest';
import { answer, install, markFirstInstall, takeFirstInstallMark } from '#lib/offline/heal.js';
import { SHELL, appFiles, cacheName, handling, mayClaim, oldCaches } from '#lib/offline/rules.js';
import { MAX_WAIT_MS, PAGE_IS_QUIET } from '#lib/offline/precacheMessage.js';

const CACHE = cacheName(version);
// `immutable` is what the old `build` was (the files Vite builds); `assets` is what the old
// `files` was (the files in static/).
const ASSETS = appFiles(immutable, assets);
const KNOWN = new Set(ASSETS);

// The page says when it has finished loading (precacheWait.ts). Made now, while the worker's
// script runs, so a message that comes before the install event is not missed.
const pageIsQuiet = new Promise<void>((done) => {
  worker.addEventListener('message', (event) => {
    if ((event.data as { type?: string } | null)?.type === PAGE_IS_QUIET) done();
  });
});

worker.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      // The very first install waits for the page to finish loading (or MAX_WAIT_MS), so
      // its 300-odd files don't slow the page down; an update (a worker is already active)
      // installs at once. If nothing comes, the files are downloaded all the same.
      const first = !worker.registration.active;
      if (first) {
        await Promise.race([pageIsQuiet, new Promise((done) => setTimeout(done, MAX_WAIT_MS))]);
      }
      // "reload": ask the server, not the browser's own copy, so a new worker never keeps
      // an old file. A half-written cache of this name is dropped first and after a failure
      // (lib/offline/heal.ts), so a failed install never leaves a bad cache behind.
      await install(
        caches,
        CACHE,
        [SHELL, ...ASSETS].map((path) => new Request(path, { cache: 'reload' }))
      );
      // Remembered for activate (the worker may be restarted in between): no worker was active.
      if (first) await markFirstInstall(caches, CACHE);
    })()
  );
});

worker.addEventListener('activate', (event) => {
  // Only now, when no window of the old version is left, are its files deleted.
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      const noWorkerBefore = await takeFirstInstallMark(caches, CACHE);
      const first = mayClaim(keys, CACHE, noWorkerBefore);
      for (const key of oldCaches(keys, CACHE)) await caches.delete(key);
      // The first worker takes the page that installed it (its files are on the device now): no
      // older cache AND no active worker at install. An update never does.
      if (first) await worker.clients.claim();
    })()
  );
});

worker.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  const kind = handling(request, url, worker.location.origin, KNOWN);
  if (kind === 'network') return; // no respondWith: the browser goes to the network as usual
  if (kind === 'version') {
    // SvelteKit's own "is there a new version?" check: this version, so it finds nothing new.
    // Nothing is fetched, kept or reloaded; a new version still arrives only as a new worker.
    event.respondWith(Response.json({ version }, { headers: { 'cache-control': 'no-store' } }));
    return;
  }

  // A missing or bad copy is dropped and fetched fresh from the app's own server, and the
  // fresh one is kept (heal.ts). A good copy still opens the app with no connection.
  event.respondWith(
    answer(caches, CACHE, kind === 'shell' ? SHELL : url.pathname, () =>
      fetch(kind === 'shell' ? SHELL : request)
    )
  );
});
