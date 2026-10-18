// Signing out (docs/dev/sync-protocol.md section 12).
//
// Before signing out, changes still waiting are sent (for up to 5 seconds); the Settings
// page warns if any are left. Then this browser is wiped (wipe.ts) BEFORE the server
// sign-out. Offline, the wipe happens at once and a "sign-out pending" flag makes the app end
// the server session first thing when it's back (signOutPending.ts).

import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { endPendingSignOut, markSignOutPending } from './signOutPending';
import { wipeDevice } from './wipe';

/** How long Sign out (and "Try sending now") tries to send what's waiting. */
export const SEND_FOR_MS = 5000;

/** Send what's waiting, for up to `ms`. Gives back how many changes are still waiting. */
export async function trySending(ms = SEND_FOR_MS): Promise<number> {
  if (shoppingSync.waiting === 0) return 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  await Promise.race([
    shoppingSync.tryAgain().catch(() => undefined),
    new Promise((done) => (timer = setTimeout(done, ms)))
  ]);
  clearTimeout(timer);
  return shoppingSync.waiting;
}

/** Wipe this browser, then end the server session (now, or once it's back). */
export async function signOutHere(): Promise<void> {
  // Set first: it outlasts the wipe, so the server session is ended even if the page is
  // closed before the server answers.
  markSignOutPending();
  // Nobody signed in from here on: the list stops reading or writing the phone database, so
  // nothing makes it again after the wipe.
  session.me = null;
  await wipeDevice();
  if (!network.offline) await endPendingSignOut();
}
