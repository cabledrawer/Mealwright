// What the service worker (src/service-worker/index.ts) may touch. Kept apart from the worker
// itself so it can be tested.
//
// The rule in one line: the worker keeps only the app's own files (the code, fonts, icons),
// never anything from /api and never anything from another address. Live updates
// (/api/v1/events) and every API call go straight to the network, uncached.

/** The page every address inside the app falls back to (a single-page app). */
export const SHELL = '/index.html';

/** The start of every cache this app makes. Old ones with this start are deleted. */
export const CACHE_PREFIX = 'mealwright-app-';

export const cacheName = (version: string) => `${CACHE_PREFIX}${version}`;

/**
 * The file SvelteKit 3 asks for when a tab comes back into view (it cannot be switched off).
 * Updates here come only through this worker, so the worker answers it itself with the
 * version it was built with: SvelteKit sees "nothing new", the server is not asked, and with
 * no connection nothing fails (no console error, no offline bar).
 */
export const VERSION_FILE = '/_app/version.json';

/**
 * The addresses of the app's own files, from SvelteKit's manifest (`immutable`: the files
 * Vite builds; `assets`: the files in `static/`). Each becomes an absolute address (a
 * leading `/`; the app has no base path), de-duplicated, in the order given.
 */
export function appFiles(
  immutable: readonly { path: string }[],
  assets: readonly { path: string }[]
): string[] {
  const all = [...immutable, ...assets].map((file) =>
    file.path.startsWith('/') ? file.path : `/${file.path}`
  );
  return [...new Set(all)];
}

/** True for any address under /api (the API, including /api/v1/events). */
export function isApi(pathname: string): boolean {
  return pathname === '/api' || pathname.startsWith('/api/');
}

export type Handling = 'shell' | 'asset' | 'version' | 'network';

/**
 * What the worker does with a request. Only `shell` (a page opened in the browser) and
 * `asset` (one of the app's own files, known at build time) are answered from the cache, and
 * `version` (SvelteKit's own version check) is answered by the worker itself; everything else,
 * notably /api, is left alone and goes to the network.
 */
export function handling(
  request: { method: string; mode: string },
  url: { origin: string; pathname: string },
  ownOrigin: string,
  assets: ReadonlySet<string>
): Handling {
  if (request.method !== 'GET') return 'network';
  if (url.origin !== ownOrigin) return 'network';
  if (isApi(url.pathname)) return 'network';
  if (url.pathname === VERSION_FILE) return 'version';
  if (request.mode === 'navigate') return 'shell';
  return assets.has(url.pathname) ? 'asset' : 'network';
}
