// Wiping this browser's copy of the household (docs/dev/sync-protocol.md section 12): on
// signing out, and when a different login carries on over someone's unsent changes (11.5).
//
// What goes:
//   - the whole phone database (`mealwright`): queue, offline copy, ingredient names, cursor,
//     device ID, `meta`;
//   - every Cache Storage cache except the app shell (code only, nothing about the household);
//   - sessionStorage, and every localStorage key except the per-device display preferences
//     and the "sign-out pending" flag below (none says anything about the household). The
//     0.2 device ID key goes too.
// The next sign-in makes a new device ID. Other tabs of the app are told first, and clear
// themselves (otherTabs.ts).
//
// A different login signing in always starts clean, the same as signing out: a fresh copy
// and a new device ID (cabledrawer 18 Oct, sync-protocol 11.8). The same login signing back in
// after its session ran out keeps the copy, the waiting changes and the device ID (11.5).

import { shoppingSync } from '$lib/shopping/sync.svelte';
import { forgetDeviceId, storedLoginId } from './device';
import { heldChanges, UNREADABLE, type Held, type Unreadable } from './held';
import { tellOtherTabs } from './otherTabs';
import { deletePhone, withQueueLock } from './phone';
import { CACHE_PREFIX } from './rules';
import { SIGN_OUT_PENDING_KEY } from './signOutPending';

/**
 * localStorage keys a wipe keeps: display preferences of this device, and the "sign-out
 * pending" flag, which must outlast the wipe (signOutPending.ts). None says anything about
 * the household.
 */
export const KEPT_ON_WIPE: readonly string[] = [
  'mealwright.theme',
  'mealwright.sidebar',
  SIGN_OUT_PENDING_KEY
];

/**
 * Wipe everything this browser keeps about the household, taking turns with adding to the
 * queue (withQueueLock).
 */
export function wipeDevice(): Promise<void> {
  return withQueueLock(wipeNow);
}

/** The wipe itself. The caller holds the queue lock (withQueueLock). */
export async function wipeNow(): Promise<void> {
  // Every other tab of the app drops what it shows and goes to sign in (otherTabs.ts).
  tellOtherTabs();
  shoppingSync.forget();
  forgetDeviceId();
  await deletePhone().catch(() => undefined);
  try {
    for (const key of await caches.keys()) {
      if (!key.startsWith(CACHE_PREFIX)) await caches.delete(key);
    }
  } catch {
    // No Cache Storage here (plain http://): nothing is cached.
  }
  try {
    sessionStorage.clear();
  } catch {
    // Storage blocked: nothing kept there.
  }
  try {
    const gone: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key !== null && !KEPT_ON_WIPE.includes(key)) gone.push(key);
    }
    for (const key of gone) localStorage.removeItem(key);
  } catch {
    // Storage blocked: nothing kept there.
  }
}

/**
 * A sign-in has succeeded as `me`. If this device holds another login's copy, wipe it first,
 * exactly as at sign-out, so `me` starts clean with a new device ID (made on the next start).
 * The same login coming back keeps everything ('kept').
 *
 * Never over another login's waiting changes without the warning (section 16, decision 4):
 * they're read again from the phone database just now, since another tab may have queued
 * some since, and when there are any they come back instead and nothing is wiped. Only
 * `losing`, what the warning showed and "Carry on and lose them" chose to lose, lets the wipe
 * go ahead, and only while the queue holds no change outside it: the same changes, not just
 * as many (another tab may have sent one and queued a new one).
 *
 * UNREADABLE when the phone database couldn't be read: then nothing is wiped and nothing is
 * written, as whether anyone's changes are waiting isn't known.
 */
export async function wipeIfAnotherLogin(
  me: { id: number },
  losing: Held | null = null
): Promise<'kept' | 'wiped' | Unreadable | Held> {
  const stored = await storedLoginId();
  if (stored === UNREADABLE) return UNREADABLE;
  if (stored === null || stored === me.id) return 'kept';
  // The read and the wipe hold the queue lock together: a change another tab adds meanwhile
  // waits, and lands after the wipe, never unseen in between.
  return withQueueLock(async () => {
    const held = await heldChanges();
    if (held === UNREADABLE) return UNREADABLE;
    if (held && held.who.id !== me.id) {
      const shown = new Set(losing?.who.id === held.who.id ? losing.ids : []);
      if (!held.ids.every((id) => shown.has(id))) return held;
    }
    await wipeNow();
    return 'wiped' as const;
  });
}
