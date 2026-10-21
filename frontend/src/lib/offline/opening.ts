// Starting the app on a weak signal (sync-protocol 11.4).
//
// cabledrawer's decision (20 Oct, hand test): offline or on a weak signal, the saved copy shows
// at once and the network is tried in the background; when it answers, the list updates in
// place. How long the start waits before opening from this device (START_WAIT_MS) is the
// builder's choice, proposed, for cabledrawer.
//
// The start asks the server whether it needs setting up and who is signed in. Offline, or on
// a signal so weak that requests hang rather than fail, that answer can take until the 30 s
// timeout, and nothing showed meanwhile. So the start waits for it only briefly (not at all
// when the browser says it is offline). If it hasn't come by then, the app opens at once as
// whoever was last signed in on this device, as it does offline, and the answer is acted on
// when it comes, with the same rules as at the start:
//
// - Still no connection: the app carries on as it opened, as it does offline.
// - The same login: carries on, now known to be signed in.
// - Not signed in, or the server needing setting up: +layout.ts runs again with that answer
//   and decides exactly as if it had come in time.
// - A different login: never wiped while the screen is up, and the app never reloads itself
//   (11.6). That login is signed out again and goes to the sign-in page with its username
//   filled in, as the start does for a login it turns away; the sign-in page then warns, or
//   wipes, by its usual rules. Until then the app stays the device login's, so a change made
//   meanwhile is queued as theirs and kept.
//
// Until the answer has been acted on, the server's lists are held back (confirmed.ts).

import { cantReach, getMe, getSetup, type Me, type SetupState } from '$lib/api';
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

/** How a late answer is acted on: +layout.ts runs again. (Loaded when needed, so the tests,
 * which put their own here, never load the app's navigation.) */
export const restart = {
  rerun: async (): Promise<void> => (await import('$app/navigation')).invalidateAll()
};

/** A late answer, and the login the app had opened as from this device. */
export type LateAnswer = { answer: Answer; openedAs: number };

let starts = 0;
let late: LateAnswer | null = null;

/** A new start of +layout.ts: a late answer to an earlier one is then left alone. */
export function newStart(): number {
  return ++starts;
}

/** The late answer +layout.ts is running again for, if any (once). */
export function takeLateAnswer(): LateAnswer | null {
  const answer = late;
  late = null;
  return answer;
}

/** The server answered after the app opened from this device as `openedAs` (start number
 * `start`). +layout.ts decides on it, and lets the server's lists through once it has. */
export async function answeredLate(
  asked: Promise<Answer>,
  start: number,
  openedAs: number
): Promise<void> {
  const answer = await asked;
  // Another start has asked again since (signed in, say): its answer decides.
  if (start !== starts) return;
  if ('error' in answer && cantReach(answer.error)) {
    // Still no connection: carry on as opened, as offline.
    releaseServerLists();
    return;
  }
  late = { answer, openedAs };
  try {
    await restart.rerun();
  } catch {
    // The page shows the error itself.
  } finally {
    late = null;
  }
}
