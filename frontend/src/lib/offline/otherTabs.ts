// Other tabs of the app, when one of them wipes this browser (signing out, section 12, or a
// different login starting clean, 11.8). cabledrawer 18 Oct: "Other tabs clear themselves and go
// to the sign-in page as soon as you sign out in any tab."
//
// The tab that wipes says so on a BroadcastChannel, and also by setting and at once removing
// a localStorage key (the `storage` event, for browsers without BroadcastChannel). Deleting
// the database tells every tab that has it open as well (IndexedDB's `versionchange`,
// phone.ts). All three stay inside this browser: nothing leaves it. Each says only which
// database was wiped.
//
// A tab that hears it drops what's on screen and in memory, stops the live stream and
// sending, never opens (and so never makes) the database again until someone signs in, and
// goes to the sign-in page. That is (app)/+layout.svelte, through onWipedElsewhere().

import { forgetDeviceId } from './device';
import { onPhoneDeletedElsewhere, phoneDatabaseName, sealPhone } from './phone';

/** The channel and the localStorage key. Neither says anything about the household. */
export const WIPED = 'mealwright.wiped';

let channel: BroadcastChannel | null | undefined;

function theChannel(): BroadcastChannel | null {
  if (channel === undefined) {
    try {
      channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel(WIPED) : null;
    } catch {
      channel = null;
    }
  }
  return channel;
}

/** This tab is about to wipe the browser: tell the others. */
export function tellOtherTabs(): void {
  const db = phoneDatabaseName();
  try {
    theChannel()?.postMessage({ db });
  } catch {
    // No channel: the storage event and the database's own notice still go.
  }
  try {
    localStorage.setItem(WIPED, db);
    localStorage.removeItem(WIPED);
  } catch {
    // Storage blocked: the channel and the database's notice still go.
  }
}

/**
 * Run `handler` once another tab wipes this browser, after this tab has sealed its database
 * and forgotten the device ID. Returns a function that stops listening.
 */
export function onWipedElsewhere(handler: () => void): () => void {
  let heard = false;
  const wiped = (db: unknown) => {
    // Tests give each file a database of its own; only ours counts.
    if (heard || db !== phoneDatabaseName()) return;
    heard = true;
    sealPhone();
    forgetDeviceId();
    handler();
  };
  const onMessage = (event: MessageEvent) => wiped((event.data as { db?: unknown } | null)?.db);
  const onStorage = (event: StorageEvent) => {
    if (event.key === WIPED && event.newValue !== null) wiped(event.newValue);
  };
  const ours = theChannel();
  ours?.addEventListener('message', onMessage);
  window.addEventListener('storage', onStorage);
  const stopDeleted = onPhoneDeletedElsewhere(() => wiped(phoneDatabaseName()));
  return () => {
    ours?.removeEventListener('message', onMessage);
    window.removeEventListener('storage', onStorage);
    stopDeleted();
  };
}
