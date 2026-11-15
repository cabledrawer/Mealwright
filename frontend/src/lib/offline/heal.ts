// How the service worker's cache looks after itself (BUILD-PLAN 0.9.5 "the service worker's
// cache heals itself"). Kept apart from the worker so it can be tested.
//
// The rule: a cache that is missing a file, holds a bad copy of one, or was left half-written
// by an install that failed never leaves the app blank or stuck. The worker notices, drops the
// bad copy, asks its own server for a fresh one (when there is a connection) and keeps that.
// With no connection a good cache still opens the app, as before. Only the app's own files and
// start page are ever put in the cache; nothing here reads or keeps an API answer.

/** The part of a cache the worker uses, so a test can stand one in. */
export interface CacheLike {
  match(key: string): Promise<Response | undefined>;
  put(key: string, response: Response): Promise<void>;
  delete(key: string): Promise<boolean>;
}

/** The part of `caches` the worker uses. */
export interface StorageLike {
  open(name: string): Promise<CacheLike>;
  delete(name: string): Promise<boolean>;
}

/**
 * A copy worth keeping or serving: a plain, whole 200 from our own server. Not an error page,
 * not a redirect that was followed (a sign-in page standing in for a file), not an opaque or
 * error type, not a partial (206) answer.
 */
export function usable(response: Response | undefined | null): response is Response {
  return (
    !!response &&
    response.ok &&
    response.status === 200 &&
    !response.redirected &&
    (response.type === 'basic' || response.type === 'default')
  );
}

/**
 * Answers for one of the app's own files: from the cache when the copy there is good,
 * otherwise from the network, and the fresh copy is kept for next time. A cache that can't
 * be opened or read counts as empty. With no connection and nothing good in the cache, the
 * network's own failure is passed on (there is nothing else to show).
 */
export async function answer(
  storage: StorageLike,
  name: string,
  key: string,
  fetchFresh: () => Promise<Response>
): Promise<Response> {
  let cache: CacheLike | null = null;
  let found: Response | undefined;
  try {
    cache = await storage.open(name);
    found = await cache.match(key);
  } catch {
    // An unreadable cache is treated as an empty one.
  }
  if (usable(found)) return found;
  if (found && cache) await cache.delete(key).catch(() => false); // drop the bad copy
  const fresh = await fetchFresh();
  if (cache && usable(fresh)) await cache.put(key, fresh.clone()).catch(() => undefined);
  return fresh;
}

/** How many of the app's files the first download asks for at once. */
export const INSTALL_AT_ONCE = 6;

/**
 * Fills this version's cache. Anything left under the same name (half-written by an install
 * that failed) is dropped first, and if filling fails the half-filled cache is dropped again
 * before the failure is passed on, so the next try starts clean.
 */
export async function install(
  storage: StorageLike,
  name: string,
  requests: Request[],
  fetchFresh: (request: Request) => Promise<Response> = (request) => fetch(request)
): Promise<void> {
  await storage.delete(name).catch(() => false);
  try {
    const cache = await storage.open(name);
    // Not `cache.addAll`: it keeps a redirected or partial answer too. Each file is checked
    // by the same rule as every later write (usable) before it is kept. INSTALL_AT_ONCE files
    // at a time (one at a time cost a round trip each on a slow link); a group is kept in order,
    // and a failure anywhere stops the rest and drops the cache (below).
    for (let at = 0; at < requests.length; at += INSTALL_AT_ONCE) {
      const group = requests.slice(at, at + INSTALL_AT_ONCE);
      const answers = await Promise.all(group.map((request) => fetchFresh(request)));
      answers.forEach((response, i) => {
        if (!usable(response)) throw new Error(`Could not fetch ${group[i].url}`);
      });
      for (let i = 0; i < group.length; i++) await cache.put(group[i].url, answers[i]);
    }
  } catch (error) {
    await storage.delete(name).catch(() => false);
    throw error;
  }
}
