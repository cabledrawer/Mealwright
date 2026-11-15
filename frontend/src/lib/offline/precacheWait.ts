// The service worker's first download of the app's files waits for the page to finish loading
// (0.9.5 speed work; proposed, for cabledrawer). Its 329 files, fetched while the first page is
// still loading, slowed that page by 10 to 12 seconds on a small server. The page tells the
// worker when it has asked for nothing new for a moment; the worker gives up waiting after
// MOST_WAIT_MS and goes on, so the files are always downloaded. Only the very first install
// waits: an update installs at once, as before.
import { MOST_WAIT_MS, PAGE_IS_QUIET } from './precacheMessage';

export { MOST_WAIT_MS, PAGE_IS_QUIET };
/** How long the page must ask for nothing new before it says so, and when it says so anyway. */
export const QUIET_MS = 1500;
export const PAGE_GIVES_UP_MS = 20_000;

/**
 * Resolves once `watch`'s callback (called for every request the page makes) has not been
 * called for `quietMs`, or after `mostMs`, whichever comes first.
 */
export function afterQuiet(
  watch: (note: () => void) => () => void,
  quietMs: number,
  mostMs: number
): Promise<void> {
  return new Promise((done) => {
    let quiet = setTimeout(finish, quietMs);
    const limit = setTimeout(finish, mostMs);
    const stop = watch(() => {
      clearTimeout(quiet);
      quiet = setTimeout(finish, quietMs);
    });
    function finish() {
      clearTimeout(quiet);
      clearTimeout(limit);
      stop();
      done();
    }
  });
}

/** The requests this page makes (code, styles, pictures and calls to the server). */
const watchRequests = (note: () => void) => {
  const seen = new PerformanceObserver(note);
  seen.observe({ type: 'resource' });
  return () => seen.disconnect();
};

/**
 * Once the page has loaded and been quiet, tell the worker that is installing (the first visit)
 * that its files may now be downloaded. Nothing when there is no worker or one is already
 * running (an update, or a later visit).
 */
export async function tellWorkerPageIsQuiet(
  container: ServiceWorkerContainer | null = navigator.serviceWorker ?? null,
  watch = watchRequests
): Promise<void> {
  if (!container) return;
  if (document.readyState !== 'complete') {
    await new Promise((loaded) => addEventListener('load', loaded, { once: true }));
  }
  await afterQuiet(watch, QUIET_MS, PAGE_GIVES_UP_MS);
  const registration = await container.getRegistration().catch(() => undefined);
  if (registration && !registration.active) {
    (registration.installing ?? registration.waiting)?.postMessage({ type: PAGE_IS_QUIET });
  }
}
