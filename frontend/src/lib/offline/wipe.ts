// Wiping this browser's copy of the household (docs/dev/sync-protocol.md section 12): on
// signing out, and when a different login carries on over someone's unsent changes (11.5).
//
// What goes:
//   - the whole phone database (`mealwright`): queue, offline copy, ingredient names, cursor,
//     device ID, `meta`;
//   - every Cache Storage cache except the app shell (code only, nothing about the household);
//   - what's held in memory: the list's copy and queue, and the household's shops and places
//     (placesAndShops.svelte.ts);
//   - sessionStorage, and every localStorage key except the per-device display preferences
//     and the "sign-out pending" flag below (none says anything about the household). The
//     0.2 device ID key goes too.
// The next sign-in makes a new device ID. Other tabs of the app are told first, and clear
// themselves (otherTabs.ts).
//
// A different login signing in always starts clean, the same as signing out: a fresh copy
// and a new device ID (cabledrawer 18 Oct, sync-protocol 11.8). The same login signing back in
// after its session ran out keeps the copy, the waiting changes and the device ID (11.5).

import { placesAndShops } from '$lib/placesAndShops.svelte';
import { privacy } from '$lib/privacy.svelte';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { forgetDeviceId, rememberedLogin, storedLoginId } from './device';
import { heldChanges, UNREADABLE, type Held, type Unreadable } from './held';
import { tellOtherTabs } from './otherTabs';
import { deletePhone, withQueueLock } from './phone';
import { CACHE_PREFIX } from './rules';
import { SIGN_OUT_PENDING_KEY } from './signOutPending';
import { markWipePending, WIPE_PENDING_KEY, wipeFinished, wipePending } from './wipePending.svelte';

/**
 * localStorage keys a wipe keeps: display preferences of this device, and the "sign-out
 * pending" and "wipe pending" flags, which must outlast the wipe (signOutPending.ts,
 * wipePending.svelte.ts). None says anything about the household.
 */
export const KEPT_ON_WIPE: readonly string[] = [
  'mealwright.theme',
  'mealwright.sidebar',
  SIGN_OUT_PENDING_KEY,
  WIPE_PENDING_KEY
];

/**
 * How long deleting the phone database may take. It waits while another tab keeps it open
 * (they're told to close it, otherTabs.ts); a tab that never does mustn't hold this up for
 * ever. Past this, the wipe counts as failed, and "Try again" deletes it again.
 */
export const DELETE_FOR_MS = 10_000;

/**
 * Wipe everything this browser keeps about the household, taking turns with adding to the
 * queue (withQueueLock). False when the phone database couldn't be deleted (see wipeNow).
 */
export function wipeDevice(): Promise<boolean> {
  return withQueueLock(wipeNow);
}

/**
 * The wipe itself. The caller holds the queue lock (withQueueLock).
 *
 * False when the phone database couldn't be deleted. Everything else is still wiped, and
 * the "wipe pending" flag, set before anything was deleted, stays: until a later wipe has
 * deleted it, the old login's data is never opened, shown or used, and nobody can sign in
 * here (wipePending.svelte.ts; the sign-in page says so, with "Try again").
 */
export async function wipeNow(): Promise<boolean> {
  markWipePending();
  // Every other tab of the app drops what it shows and goes to sign in (otherTabs.ts).
  tellOtherTabs();
  shoppingSync.forget();
  placesAndShops.forget();
  privacy.forget();
  forgetDeviceId();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deleted = await Promise.race([
    deletePhone().then(
      () => true,
      () => false
    ),
    new Promise<boolean>((done) => (timer = setTimeout(() => done(false), DELETE_FOR_MS)))
  ]);
  clearTimeout(timer);
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
  wipeFinished(deleted);
  return deleted;
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
 * written, as whether anyone's changes are waiting isn't known. Except: the login it was last
 * written for (rememberedLogin) carries on ('kept', nothing written), and `losing` 'anyway'
 * (the warning's "Carry on anyway — anything waiting on this phone may be lost") wipes. 'wipe-failed' when the wipe
 * couldn't delete the phone database: then nobody may be let in (wipePending.svelte.ts).
 */
export async function wipeIfAnotherLogin(
  me: { id: number },
  losing: Held | 'anyway' | null = null
): Promise<'kept' | 'wiped' | 'wipe-failed' | Unreadable | Held> {
  // An earlier wipe couldn't delete the phone database: it was chosen already, so it's
  // finished first, whoever signs in. 'wipe-failed' while it still can't be.
  if (wipePending()) return (await wipeDevice()) ? 'wiped' : 'wipe-failed';
  const stored = await storedLoginId();
  if (stored === UNREADABLE) {
    // The same login carries on: it never wipes anything, so nothing is at risk (cabledrawer
    // 18 Oct). Nothing is written either (startDevice).
    if (rememberedLogin()?.id === me.id) return 'kept';
    // Anyone else only through the warning's "Carry on anyway" ('anyway').
    if (losing !== 'anyway') return UNREADABLE;
  } else if (stored === null || stored === me.id) return 'kept';
  // The read and the wipe hold the queue lock together: a change another tab adds meanwhile
  // waits, and lands after the wipe, never unseen in between.
  return withQueueLock(async () => {
    const now = await storedLoginId();
    if (now !== UNREADABLE && (now === null || now === me.id)) return 'kept' as const;
    const held = await heldChanges();
    // "Carry on anyway" covers only a phone database that still can't be read. Readable
    // again, it's the usual warning, with whose changes and how many.
    if (held === UNREADABLE && losing !== 'anyway') return UNREADABLE;
    if (held && held !== UNREADABLE && held.who.id !== me.id) {
      const shown = new Set(
        losing && losing !== 'anyway' && losing.who.id === held.who.id ? losing.ids : []
      );
      if (!held.ids.every((id) => shown.has(id))) return held;
    }
    return (await wipeNow()) ? ('wiped' as const) : ('wipe-failed' as const);
  });
}
