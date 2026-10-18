import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { breakPhone, dropPhone, freshPhone } from '$lib/testing/phone';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { deviceId, loadDeviceId, OLD_DEVICE_KEY, startDevice } from './device';
import { UNREADABLE } from './held';
import { getMeta, phoneDatabaseName, setMeta } from './phone';
import { CACHE_PREFIX } from './rules';
import { SIGN_OUT_PENDING_KEY } from './signOutPending';
import { addToQueue, readQueue } from './store';
import { KEPT_ON_WIPE, wipeDevice, wipeIfAnotherLogin } from './wipe';

const SHELL_CACHE = `${CACHE_PREFIX}test-wipe`;
const OTHER_CACHE = 'mealwright-recipes-test-wipe';

beforeEach(() => freshPhone());
afterEach(async () => {
  vi.restoreAllMocks();
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

const WREN = { login_id: 2, login_name: 'Wren', username: 'wren', role: 'member', protocol: 1 };
const DEVICE = '11111111-2222-4333-8444-555555555555';
const ARLO = { id: 3, name: 'Arlo', username: 'arlo', role: 'member' };
const tick = (id: string) => ({
  id,
  made_at: '2026-10-18T09:00:00Z',
  seen: 0,
  kind: 'tick' as const,
  item_id: 'i'
});

const databaseThere = async () =>
  (await indexedDB.databases()).some((d) => d.name === phoneDatabaseName());

describe('a phone database that can’t be read: nothing wiped, nothing written', () => {
  it('another login signing in: “couldn’t read”, and Wren’s phone stays as it was', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const mend = breakPhone();
    expect(await wipeIfAnotherLogin(ARLO)).toBe(UNREADABLE);
    // Even with "Carry on and lose them" chosen for what an earlier warning showed.
    const losing = { who: { ...ARLO, id: 2, name: 'Wren' }, count: 1, ids: ['a'] };
    expect(await wipeIfAnotherLogin(ARLO, losing)).toBe(UNREADABLE);
    mend();
    expect(await databaseThere()).toBe(true);
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await readQueue()).toHaveLength(1);
  });

  it('starting the app writes nothing over `meta` it couldn’t read', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    const mend = breakPhone();
    await startDevice(ARLO);
    mend();
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('username')).toBe('wren');
    expect(await getMeta('device_id')).toBe(DEVICE);
    // The device ID is this visit's only, not Wren's.
    expect(deviceId()).not.toBe(DEVICE);
  });

  it('nor over another login’s `meta` (another tab may have changed it since the check)', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await startDevice(ARLO);
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(deviceId()).not.toBe(DEVICE);
    // The same login, or a clean phone, is noted as before.
    await startDevice({ ...ARLO, id: 2, name: 'Wren', username: 'wren' });
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(deviceId()).toBe(DEVICE);
  });
});
