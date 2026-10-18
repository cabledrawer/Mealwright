// For tests only: a fresh, empty phone database and queue for each test. Every test file
// shares one origin (so one IndexedDB), so each test gets a database of its own name.

import { vi } from 'vitest';
import { forgetDeviceId } from '$lib/offline/device';
import { closePhone, deletePhone, usePhoneDatabase } from '$lib/offline/phone';
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

/**
 * Make the phone database fail to open, as a broken or locked-up IndexedDB does: every read
 * of it rejects from now on (it still shows in the list of databases). Returns a function
 * that mends it. Closes the open connection first, so the next read has to open it.
 */
export function breakPhone(): () => void {
  closePhone();
  const open = vi.spyOn(indexedDB, 'open').mockImplementation(() => {
    throw new DOMException('The phone database is broken (a test).', 'UnknownError');
  });
  return () => open.mockRestore();
}
