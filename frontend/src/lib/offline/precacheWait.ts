// The service worker's first download of the app's files waits for the page to finish
// loading (0.9.5 speed work; proposed, for cabledrawer). Its 329 files, fetched while the first page
// is still loading, slowed that page by 10 to 12 seconds on a small server. The page tells the
// worker when it has been quiet (nothing new asked for) for a moment; the worker also gives up
// waiting after `MOST_WAIT_MS` and goes on, so the files are always downloaded.
//
// Only the very first install waits. An update installs at once, as before: a page is already
// open and the old files are already there to use offline.

import { MOST_WAIT_MS, PAGE_IS_QUIET } from './precacheMessage';

export { MOST_WAIT_MS, PAGE_IS_QUIET };
/** How long the page must ask for nothing new before it says so. */
export const QUIET_MS = 1500;
/** The page stops waiting for quiet after this and says so anyway. */
export const PAGE_GIVES_UP_MS = 20_000;

type Timer = ReturnType<typeof setTimeout>;

/**
 * Resolves once `note` (called for every request the page makes) has not been called for
 * `quietMs`, or after `mostMs`, whichever comes first. The clock is injected for tests.
 */
export function afterQuiet(
  watch: (note: () => void) => () => void,
  quietMs: number,
  mostMs: number,
  clock: {
    set: (run: () => void, ms: number) => Timer;
    clear: (timer: Timer) => void;
  } = { set: (run, ms) => setTimeout(run, ms), clear: (timer) => clearTimeout(timer) }
): Promise<void> {
  return new Promise((done) => {
    let quiet: Timer | undefined;
    let stop = () => {};
    const finish = () => {
      if (quiet !== undefined) clock.clear(quiet);
      clock.clear(limit);
      stop();
      done();
    };
    const restart = () => {
      if (quiet !== undefined) clock.clear(quiet);
      quiet = clock.set(finish, quietMs);
    };
    const limit = clock.set(finish, mostMs);
    stop = watch(restart);
    restart();
  });
}

/** Watch the requests this page makes (code, styles, pictures and calls to the server). */
export function watchRequests(note: () => void): () => void {
  if (typeof PerformanceObserver === 'undefined') return () => {};
  const observer = new PerformanceObserver(() => note());
  try {
    observer.observe({ type: 'resource' });
  } catch {
    return () => {};
  }
  return () => observer.disconnect();
}

/**
 * Once the page has loaded and been quiet, tell the worker that is installing (the first visit)
 * that its files may now be downloaded. Nothing to do where there is no worker, or when one is
 * already running (an update, or a later visit).
 */
export async function tellWorkerPageIsQuiet(
  container: ServiceWorkerContainer | null = typeof navigator === 'undefined'
    ? null
    : (navigator.serviceWorker ?? null),
  watch: (note: () => void) => () => void = watchRequests
): Promise<void> {
  if (!container) return;
  if (document.readyState !== 'complete') {
    await new Promise<void>((loaded) => addEventListener('load', () => loaded(), { once: true }));
  }
  await afterQuiet(watch, QUIET_MS, PAGE_GIVES_UP_MS);
  const registration = await container.getRegistration().catch(() => undefined);
  if (!registration || registration.active) return;
  (registration.installing ?? registration.waiting)?.postMessage({ type: PAGE_IS_QUIET });
}
