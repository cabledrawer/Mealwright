// What the page and the service worker say to each other about the worker's first download of
// the app's files (see precacheWait.ts for why). Kept apart so the worker, which has no page
// to look at, can use it.

/** What the page posts to the installing worker. */
export const PAGE_IS_QUIET = 'page-is-quiet';
/** The longest the worker waits for it. */
export const MOST_WAIT_MS = 25_000;
