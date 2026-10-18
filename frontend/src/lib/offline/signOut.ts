// Signing out (docs/dev/sync-protocol.md section 12).
//
// Before signing out, changes still waiting are sent (for up to 5 seconds); the Settings
// page warns if any are left. Then this browser is wiped (wipe.ts) BEFORE the server
// sign-out. Offline, the wipe happens at once and a "sign-out pending" flag makes the app end
// the server session first thing when it's back (signOutPending.ts).

import { ApiError, signOut } from '$lib/api';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { storedWaiting, UNREADABLE, type Unreadable } from './held';
import { endPendingSignOut, markSignOutPending, signOutPending } from './signOutPending';
import { signOutState } from './unfinished.svelte';
import { wipeDevice } from './wipe';

/** How long Sign out (and "Try sending now") tries to send what's waiting. */
export const SEND_FOR_MS = 5000;

/**
 * Send what's waiting, for up to `ms`. Gives back how many changes are still waiting, read
 * again from the phone database (the list may not have read them all), or UNREADABLE when it
 * couldn't be read: then whether any are waiting isn't known, and signing out waits.
 */
export async function trySending(ms = SEND_FOR_MS): Promise<number | Unreadable> {
  if (shoppingSync.waiting > 0) {
    let timer: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([
      shoppingSync.tryAgain().catch(() => undefined),
      new Promise((done) => (timer = setTimeout(done, ms)))
    ]);
    clearTimeout(timer);
  }
  return stillWaiting();
}

/** The signed-in login's changes still waiting here: stored, and any kept in memory only. */
async function stillWaiting(): Promise<number | Unreadable> {
  const me = session.me?.id;
  if (me === undefined) return 0;
  const stored = await storedWaiting(me);
  if (stored === UNREADABLE) return UNREADABLE;
  // Kept in memory only (no IndexedDB here): numbered below zero, and never stored.
  const inMemory = shoppingSync.queue.filter((e) => e.login_id === me && (e.seq ?? 0) < 0);
  return stored + inMemory.length;
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

/**
 * End this browser's session on the server, without wiping anything (the app turning a login
 * away over someone's waiting changes, 11.5). True once it's ended, or there was none. False
 * when it couldn't be: then the sign-in page says "Couldn't finish signing out" and doesn't
 * send this browser back into the app, which would only sign it out again.
 */
export async function endSession(): Promise<boolean> {
  if (signOutPending()) return endPendingSignOut();
  try {
    await signOut();
  } catch (error) {
    // 401: there was no session left to end.
    if (!(error instanceof ApiError && error.status === 401)) {
      signOutState.unfinished = true;
      return false;
    }
  }
  signOutState.unfinished = false;
  return true;
}
