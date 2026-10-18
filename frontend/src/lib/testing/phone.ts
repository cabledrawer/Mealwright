// For tests only: a fresh, empty phone database and queue for each test. Every test file
// shares one origin (so one IndexedDB), so each test gets a database of its own name.

import { forgetDeviceId } from '$lib/offline/device';
import { deletePhone, usePhoneDatabase } from '$lib/offline/phone';
import { shoppingSync, TIMING } from '$lib/shopping/sync.svelte';

export function freshPhone(): void {
  shoppingSync.forget();
  shoppingSync.timing = { ...TIMING, gatherMs: 0 };
  forgetDeviceId();
  usePhoneDatabase(`test-${crypto.randomUUID()}`);
}

/** Delete this test's database. */
export async function dropPhone(): Promise<void> {
  shoppingSync.forget();
  await deletePhone();
}
