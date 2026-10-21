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
import { withQueueLock } from './phone';
import { wipeNow } from './wipe';

/** How long Sign out (and "Try sending now") tries to send what's waiting. */
export const SEND_FOR_MS = 5000;

/** The signed-in login's changes still waiting here: how many, and which. */
export interface Waiting {
  count: number;
  /** Their action IDs: a warning remembers which changes it showed, not just how many. */
  ids: string[];
}

/**
 * Send what's waiting, for up to `ms`. Gives back what's still waiting, read again from the
 * phone database (the list may not have read it all), or UNREADABLE when it couldn't be
 * read: then whether any are waiting isn't known, and signing out waits.
 */
export async function trySending(ms = SEND_FOR_MS): Promise<Waiting | Unreadable> {
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
async function stillWaiting(): Promise<Waiting | Unreadable> {
  const me = session.me?.id;
  if (me === undefined) return { count: 0, ids: [] };
  const stored = await storedWaiting(me);
  if (stored === UNREADABLE) return UNREADABLE;
  // Kept in memory only (no IndexedDB here): numbered below zero, and never stored.
  const inMemory = shoppingSync.queue
    .filter((e) => e.login_id === me && (e.seq ?? 0) < 0)
    .map((e) => e.action.id);
  const ids = [...stored, ...inMemory];
  return { count: ids.length, ids };
}

/**
 * Wipe this browser, then end the server session (now, or once it's back).
 *
 * `shown`: the changes the warning showed, and so chose to lose (none when there was no
 * warning). They're read again just before the wipe, holding the queue lock (another tab may
 * have queued more since): if any other change is waiting by then, nothing is wiped, and
 * they come back, to warn again. UNREADABLE when the phone database couldn't be read.
 *
 * Or 'anyway': "Sign out anyway. Anything waiting on this phone may be lost", chosen when
 * the phone database couldn't be read (cabledrawer 18 Oct: not being able to sign out of a shared
 * or lost phone is worse). It wipes as usual while it still can't be read; readable again,
 * any change waiting comes back, to warn as usual.
 */
export async function signOutHere(
  shown: readonly string[] | 'anyway' = []
): Promise<'signed-out' | Waiting | Unreadable> {
  const stopped = await withQueueLock(async () => {
    const now = await stillWaiting();
    if (now === UNREADABLE) {
      if (shown !== 'anyway') return UNREADABLE;
    } else if (now.ids.some((id) => shown === 'anyway' || !shown.includes(id))) return now;
    // Set first: it outlasts the wipe, so the server session is ended even if the page is
    // closed before the server answers.
    markSignOutPending();
    // Nobody signed in from here on: the list stops reading or writing the phone database,
    // so nothing makes it again after the wipe.
    session.me = null;
    // If the phone database couldn't be deleted, the session is still ended: the sign-in
    // page then says so, and lets nobody in until it has been (wipePending.svelte.ts).
    await wipeNow();
    return null;
  });
  if (stopped) return stopped;
  if (!network.offline) await endPendingSignOut();
  return 'signed-out';
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
