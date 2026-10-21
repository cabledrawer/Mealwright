// Starting the app on a weak signal (sync-protocol 11.4; cabledrawer 20 Oct, hand test).
//
// The start asks the server whether it needs setting up and who is signed in. Offline, or on
// a signal so weak that requests hang rather than fail, that answer can take until the 30 s
// timeout, and nothing showed meanwhile. So the start waits for it only briefly
// (START_WAIT_MS, and not at all when the browser says it is offline). If it hasn't come by
// then, the app opens at once as whoever was last signed in on this device, as it does
// offline, and the answer is acted on when it comes, with the same rules as at the start:
//
// - Still no connection: the app carries on as it opened, as it does offline.
// - The same login: carries on, now known to be signed in.
// - Anything else (not signed in, another login, the server needing setting up, a server
//   error): +layout.ts runs again with that answer, and decides exactly as if it had come
//   in time (sign in, the warning, the wipe). A different login that then starts clean
//   starts the app again, so nothing of the last one stays on the screen.
//
// Until the answer has been acted on, the server's lists are held back (confirmed.ts).

import { cantReach, getMe, getSetup, type Me, type SetupState } from '$lib/api';
import { session } from '$lib/session.svelte';
import { releaseServerLists } from './confirmed';

/** How long the start waits for the server before opening from this device. */
export const START_WAIT_MS = 500;

/** What the server said at the start: whether it needs setup and who is signed in. */
export type Answer = { setup: SetupState; me: Me | null } | { error: unknown };

/** Ask the server (never throws: a failure is part of the answer). */
export async function askServer(fetch: typeof globalThis.fetch): Promise<Answer> {
  try {
    const setup = await getSetup(fetch);
    if (setup.needs_setup) return { setup, me: null };
    return { setup, me: await getMe(fetch) };
  } catch (error) {
    return { error };
  }
}

/** The answer if it comes in time, or null. No wait when the browser says it's offline. */
export function inTime(asked: Promise<Answer>): Promise<Answer | null> {
  const wait = typeof navigator !== 'undefined' && navigator.onLine === false ? 0 : START_WAIT_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<null>((done) => (timer = setTimeout(() => done(null), wait)));
  return Promise.race([asked, late]).finally(() => clearTimeout(timer));
}

/** How a late answer is acted on: +layout.ts runs again, or the app starts again. (Loaded
 * when needed, so the tests, which put their own here, never load the app's navigation.) */
export const restart = {
  rerun: async (): Promise<void> => (await import('$app/navigation')).invalidateAll(),
  reload: (): void => location.reload()
};

let starts = 0;
let late: Answer | null = null;

/** A new start of +layout.ts: a late answer to an earlier one is then left alone. */
export function newStart(): number {
  return ++starts;
}

/** The late answer +layout.ts is running again for, if any (once). */
export function takeLateAnswer(): Answer | null {
  const answer = late;
  late = null;
  return answer;
}

/** The server answered after the app opened from this device (start number `start`). */
export async function answeredLate(asked: Promise<Answer>, start: number): Promise<void> {
  const answer = await asked;
  // Another start has asked again since (signed in, say): its answer decides.
  if (start !== starts) return;
  if ('error' in answer && cantReach(answer.error)) {
    // Still no connection: carry on as opened, as offline.
    releaseServerLists();
    return;
  }
  const before = session.me?.id;
  late = answer;
  try {
    await restart.rerun();
  } catch {
    // The page shows the error itself.
  } finally {
    late = null;
    releaseServerLists();
  }
  // A different login started clean (the wipe): start again as them.
  if (session.me && session.me.id !== before) restart.reload();
}
