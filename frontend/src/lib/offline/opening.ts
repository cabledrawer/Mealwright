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
//
// When that late answer is "still no connection", or the app opened offline, the server
// hasn't said who is signed in yet. So once it can be reached again (live updates connect,
// or the connection comes back: (app)/+layout.svelte), it is asked again (askAgain), with the
// lists held back meanwhile, and its answer is acted on exactly as a late answer is above.

import { ApiError, cantReach, getMe, getSetup, type Me, type SetupState } from '#lib/api.js';
import { holdServerLists, releaseServerLists } from './confirmed';

/** How long the start waits for the server before opening from this device. */
export const START_WAIT_MS = 500;

/** What the server said at the start: whether it needs setup and who is signed in. */
export type Answer = { setup: SetupState; me: Me | null } | { error: unknown };

/** Ask the server (never throws: a failure is part of the answer). */
export async function askServer(fetch: typeof globalThis.fetch): Promise<Answer> {
  try {
    // Both asked at once (0.9.5 speed work; proposed, for cabledrawer): on a slow connection the
    // second question waited a whole round trip for the first. On a fresh install nobody is
    // signed in and whatever the server says to "who am I?" is not asked about, as before.
    const [setup, me] = await Promise.allSettled([getSetup(fetch), getMe(fetch)]);
    if (setup.status === 'rejected') throw setup.reason;
    if (setup.value.needs_setup) return { setup: setup.value, me: null };
    if (me.status === 'rejected') throw me.reason;
    return { setup: setup.value, me: me.value };
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
  rerun: async (): Promise<void> => (await import('$app/navigation')).refreshAll()
};

/** A late answer, the login the app had opened as from this device, and how many theme picks
 * there had been when that start asked (a theme picked since is newer than the answer). */
export type LateAnswer = { answer: Answer; openedAs: number; picks: number };

let starts = 0;
let late: LateAnswer | null = null;
/** The login the app opened as from this device, while the server hasn't said who is signed
 * in (the late answer was "still no connection", or it opened offline); else null. */
let unconfirmed: number | null = null;
/** Theme picks when the start that opened as `unconfirmed` asked. */
let unconfirmedPicks = 0;
let asking = false;

/** A new start of +layout.ts: a late answer to an earlier one is then left alone. */
export function newStart(): number {
  unconfirmed = null;
  return ++starts;
}

/** The app opened offline as `openedAs` (`picks` theme picks when it asked): the server is
 * asked who is signed in once it can be reached (askAgain). */
export function openedOffline(openedAs: number, picks: number): void {
  unconfirmed = openedAs;
  unconfirmedPicks = picks;
}

/**
 * The server can be reached again (live updates connected, or the connection is back). If
 * the app opened from this device without the server saying who is signed in, ask it now,
 * holding the server's lists back until the answer has been acted on. Still no connection,
 * or a server error (a 5xx): asked again next time. Otherwise +layout.ts decides, as for a late answer: the same login
 * carries on; nobody, or a different login, goes to the sign-in page.
 */
export async function askAgain(fetch: typeof globalThis.fetch = globalThis.fetch): Promise<void> {
  const openedAs = unconfirmed;
  const picks = unconfirmedPicks;
  if (openedAs === null || asking) return;
  asking = true;
  const start = starts;
  holdServerLists();
  let answer: Answer;
  try {
    answer = await askServer(fetch);
  } finally {
    asking = false;
  }
  // Another start has asked since (signed in, say): its answer decides.
  if (start !== starts || unconfirmed !== openedAs) {
    releaseServerLists();
    return;
  }
  if ('error' in answer && notYet(answer.error)) {
    releaseServerLists();
    return;
  }
  unconfirmed = null;
  await decideLate({ answer, openedAs, picks });
}

/** Asking again got no real answer: no connection, or the server had a problem (a 5xx).
 * The app carries on as it opened, and asks again next time, never showing an error page. */
function notYet(error: unknown): boolean {
  return cantReach(error) || (error instanceof ApiError && error.status >= 500);
}

async function decideLate(answer: LateAnswer): Promise<void> {
  late = answer;
  try {
    await restart.rerun();
  } catch {
    // The page shows the error itself.
  } finally {
    late = null;
  }
}

/** The late answer +layout.ts is running again for, if any (once). */
export function takeLateAnswer(): LateAnswer | null {
  const answer = late;
  late = null;
  return answer;
}

/** The server answered after the app opened from this device as `openedAs` (start number
 * `start`, asked with `picks` theme picks so far). +layout.ts decides on it, and lets the
 * server's lists through once it has. */
export async function answeredLate(
  asked: Promise<Answer>,
  start: number,
  openedAs: number,
  picks: number
): Promise<void> {
  const answer = await asked;
  // Another start has asked again since (signed in, say): its answer decides.
  if (start !== starts) return;
  if ('error' in answer && cantReach(answer.error)) {
    // Still no connection: carry on as opened, as offline, and ask again once it's back.
    openedOffline(openedAs, picks);
    releaseServerLists();
    return;
  }
  await decideLate({ answer, openedAs, picks });
}
