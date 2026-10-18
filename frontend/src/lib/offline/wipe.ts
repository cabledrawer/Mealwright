// Wiping this browser's copy of the household (docs/dev/sync-protocol.md section 12): on
// signing out, and when a different login carries on over someone's unsent changes (11.5).
//
// What goes:
//   - the whole phone database (`mealwright`): queue, offline copy, ingredient names, cursor,
//     device ID, `meta`;
//   - every Cache Storage cache except the app shell (code only, nothing about the household);
//   - sessionStorage, and every localStorage key except the per-device display preferences
//     below (which say nothing about the household). The 0.2 device ID key goes too.
// The next sign-in makes a new device ID.

import { shoppingSync } from '$lib/shopping/sync.svelte';
import { forgetDeviceId } from './device';
import { deletePhone } from './phone';
import { CACHE_PREFIX } from './rules';

/** localStorage keys a wipe keeps: display preferences of this device only. */
export const KEPT_ON_WIPE: readonly string[] = ['mealwright.theme', 'mealwright.sidebar'];

/** Wipe everything this browser keeps about the household. */
export async function wipeDevice(): Promise<void> {
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
