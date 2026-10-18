import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { dropPhone, freshPhone } from '$lib/testing/phone';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { deviceId, loadDeviceId, OLD_DEVICE_KEY } from './device';
import { phoneDatabaseName, setMeta } from './phone';
import { CACHE_PREFIX } from './rules';
import { SIGN_OUT_PENDING_KEY } from './signOutPending';
import { addToQueue } from './store';
import { KEPT_ON_WIPE, wipeDevice } from './wipe';

const SHELL_CACHE = `${CACHE_PREFIX}test-wipe`;
const OTHER_CACHE = 'mealwright-recipes-test-wipe';

beforeEach(() => freshPhone());
afterEach(async () => {
  await dropPhone();
  await caches.delete(SHELL_CACHE);
  await caches.delete(OTHER_CACHE);
  localStorage.clear();
  sessionStorage.clear();
});

describe('wiping this browser (sync-protocol section 12)', () => {
  it('takes the whole phone database, other caches and storage; keeps the app and display', async () => {
    const before = await loadDeviceId();
    await setMeta({ login_id: 2, login_name: 'Wren', username: 'wren', cursor: 40 });
    await addToQueue(
      { id: 'a', made_at: '2026-10-18T09:00:00Z', seen: 0, kind: 'tick', item_id: 'i' },
      2,
      before
    );
    await (await caches.open(SHELL_CACHE)).put('/index.html', new Response('app'));
    await (await caches.open(OTHER_CACHE)).put('/photo.jpg', new Response('photo'));
    localStorage.setItem('mealwright.theme', 'dark');
    localStorage.setItem('mealwright.sidebar', 'collapsed');
    localStorage.setItem(SIGN_OUT_PENDING_KEY, '1');
    localStorage.setItem('mealwright.household-from-browser', 'sent');
    localStorage.setItem(OLD_DEVICE_KEY, before);
    sessionStorage.setItem('anything', 'x');

    await wipeDevice();

    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
    expect(await caches.has(SHELL_CACHE)).toBe(true);
    expect(await caches.has(OTHER_CACHE)).toBe(false);
    expect(sessionStorage.length).toBe(0);
    const kept = Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i));
    expect(kept.sort()).toEqual([...KEPT_ON_WIPE].sort());
    expect([...KEPT_ON_WIPE].sort()).toEqual([
      'mealwright.sidebar',
      'mealwright.sign-out-pending',
      'mealwright.theme'
    ]);
    // The old place of the device ID is empty too (cabledrawer 18 Oct).
    expect(localStorage.getItem(OLD_DEVICE_KEY)).toBeNull();
    expect(shoppingSync.queue).toEqual([]);
    expect(shoppingSync.copy).toBeNull();
    // The next sign-in makes a new device ID.
    expect(await loadDeviceId()).not.toBe(before);
    expect(deviceId()).not.toBe(before);
  });
});
