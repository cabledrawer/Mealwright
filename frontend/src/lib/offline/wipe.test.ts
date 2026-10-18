import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { breakPhone, dropPhone, failPhoneDelete, freshPhone } from '$lib/testing/phone';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import {
  deviceId,
  lastSignedIn,
  loadDeviceId,
  LOGIN_KEY,
  OLD_DEVICE_KEY,
  rememberedLogin,
  startDevice
} from './device';
import { heldChanges, UNREADABLE, type Held } from './held';
import { getMeta, openPhone, phoneDatabaseName, setMeta } from './phone';
import { CACHE_PREFIX } from './rules';
import { SIGN_OUT_PENDING_KEY } from './signOutPending';
import { addToQueue, dropFromQueue, readQueue } from './store';
import { KEPT_ON_WIPE, wipeDevice, wipeIfAnotherLogin } from './wipe';
import { WIPE_PENDING_KEY, wipeFailed, wipePending, wipeState } from './wipePending.svelte';

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
    localStorage.setItem(LOGIN_KEY, JSON.stringify({ id: 2, username: 'wren' }));
    sessionStorage.setItem('anything', 'x');

    expect(await wipeDevice()).toBe(true);
    // Finished: nothing pending.
    expect(wipePending()).toBe(false);

    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
    expect(await caches.has(SHELL_CACHE)).toBe(true);
    expect(await caches.has(OTHER_CACHE)).toBe(false);
    expect(sessionStorage.length).toBe(0);
    const kept = Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i));
    // All kept, but "wipe pending": set as the wipe started, and cleared once it finished.
    expect(kept.sort()).toEqual(KEPT_ON_WIPE.filter((k) => k !== WIPE_PENDING_KEY).sort());
    expect([...KEPT_ON_WIPE].sort()).toEqual([
      'mealwright.sidebar',
      'mealwright.sign-out-pending',
      'mealwright.theme',
      'mealwright.wipe-pending'
    ]);
    // The old place of the device ID is empty too (cabledrawer 18 Oct), and whose it was.
    expect(localStorage.getItem(OLD_DEVICE_KEY)).toBeNull();
    expect(rememberedLogin()).toBeNull();
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

  it('the login it was last written for carries on: kept, and nothing written (cabledrawer 18 Oct)', async () => {
    await startDevice({ ...ARLO, id: 2, name: 'Wren', username: 'wren' });
    expect(rememberedLogin()).toEqual({ id: 2, username: 'wren' });
    await setMeta({ device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const mend = breakPhone();
    expect(await wipeIfAnotherLogin({ id: 2 })).toBe('kept');
    await startDevice({ ...ARLO, id: 2, name: 'Wren', username: 'wren' });
    // Anyone else still can't.
    expect(await wipeIfAnotherLogin(ARLO)).toBe(UNREADABLE);
    mend();
    expect(await databaseThere()).toBe(true);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await readQueue()).toHaveLength(1);
  });

  it('“Carry on anyway” wipes it (cabledrawer 18 Oct)', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const mend = breakPhone();
    try {
      expect(await wipeIfAnotherLogin(ARLO, 'anyway')).toBe('wiped');
    } finally {
      mend();
    }
    expect(await databaseThere()).toBe(false);
  });

  it('“Carry on anyway” once it can be read again: the usual warning, with Wren’s changes', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const held = await wipeIfAnotherLogin(ARLO, 'anyway');
    expect(held).toMatchObject({ who: { id: 2 }, count: 1, ids: ['a'] });
    expect(await databaseThere()).toBe(true);
    // And for the login it belongs to, kept.
    expect(await wipeIfAnotherLogin({ id: 2 }, 'anyway')).toBe('kept');
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

describe('“Carry on and lose them” loses only the changes the warning showed', () => {
  it('another tab sends one and queues a different one: as many, but not the same, so it warns again', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    const first = await addToQueue(tick('a'), 2, DEVICE);
    await addToQueue(tick('b'), 2, DEVICE);
    // The warning shows Wren's 2 changes: a and b.
    const shown = (await heldChanges()) as Held;
    expect(shown).toMatchObject({ count: 2, ids: ['a', 'b'] });

    // Meanwhile, in another tab, Wren's change a is sent and she makes a new one, c.
    await dropFromQueue([first.seq!]);
    await addToQueue(tick('c'), 2, DEVICE);

    // Still 2 waiting, but c was never shown: nothing is wiped, and it warns again with c.
    const again = await wipeIfAnotherLogin(ARLO, shown);
    expect(again).toMatchObject({ who: { id: 2 }, count: 2, ids: ['b', 'c'] });
    expect(await databaseThere()).toBe(true);
    expect((await readQueue()).map((e) => e.action.id)).toEqual(['b', 'c']);
    expect(await getMeta('device_id')).toBe(DEVICE);

    // Carrying on after that warning loses b and c, and only then.
    expect(await wipeIfAnotherLogin(ARLO, again as Held)).toBe('wiped');
    expect(await databaseThere()).toBe(false);
  });

  it('fewer than shown (some were sent since): goes ahead', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    const first = await addToQueue(tick('a'), 2, DEVICE);
    await addToQueue(tick('b'), 2, DEVICE);
    const shown = (await heldChanges()) as Held;
    await dropFromQueue([first.seq!]);
    expect(await wipeIfAnotherLogin(ARLO, shown)).toBe('wiped');
    expect(await databaseThere()).toBe(false);
  });

  it('a warning about someone else’s changes covers none of Wren’s', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const someoneElse = { who: { ...ARLO, id: 5, name: 'Sam' }, count: 1, ids: ['a'] };
    expect(await wipeIfAnotherLogin(ARLO, someoneElse)).toMatchObject({ who: { id: 2 } });
    expect(await databaseThere()).toBe(true);
  });
});

describe('adding to the queue and wiping take turns (Web Locks)', () => {
  it('a change added between the wipe’s read and its delete waits, and lands after the wipe, never lost', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const shown = (await heldChanges()) as Held;
    // Another tab adds Wren's change "late" just as the wipe is about to delete.
    let late: Promise<unknown> | null = null;
    vi.spyOn(shoppingSync, 'forget').mockImplementationOnce(() => {
      late = addToQueue(tick('late'), 2, DEVICE);
    });
    expect(await wipeIfAnotherLogin(ARLO, shown)).toBe('wiped');
    expect(late).not.toBeNull();
    await late;
    // It waited for the wipe, so it's in the new database, not deleted unseen.
    expect((await readQueue()).map((e) => e.action.id)).toEqual(['late']);
  });

  it('a change added just before the wipe’s read is seen, and warned about', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const shown = (await heldChanges()) as Held;
    const adding = addToQueue(tick('b'), 2, DEVICE);
    expect(await wipeIfAnotherLogin(ARLO, shown)).toMatchObject({ count: 2, ids: ['a', 'b'] });
    await adding;
    expect(await databaseThere()).toBe(true);
    expect(await readQueue()).toHaveLength(2);
  });

  it('a browser without Web Locks wipes as before', async () => {
    vi.spyOn(navigator, 'locks', 'get').mockReturnValue(undefined as never);
    await setMeta({ ...WREN, device_id: DEVICE });
    const entry = await addToQueue(tick('a'), 2, DEVICE);
    expect(entry.seq).toBeGreaterThan(0);
    const shown = (await heldChanges()) as Held;
    expect(await wipeIfAnotherLogin(ARLO, shown)).toBe('wiped');
    expect(await databaseThere()).toBe(false);
  });
});

describe('a wipe that can’t delete the phone database (cabledrawer 18 Oct)', () => {
  it('everything else goes, and the old login’s data is never opened, shown or used', async () => {
    await setMeta(WREN);
    await addToQueue(tick('r1'), 2, DEVICE);
    const mend = failPhoneDelete();
    expect(await wipeDevice()).toBe(false);
    expect(wipePending()).toBe(true);
    expect(wipeFailed()).toBe(true);
    expect(localStorage.getItem(WIPE_PENDING_KEY)).toBe('failed');
    expect(await databaseThere()).toBe(true);
    // Nothing of Wren's is found, and the database isn't opened again.
    expect(await heldChanges()).toBeNull();
    expect(await lastSignedIn()).toBeNull();
    await expect(openPhone()).rejects.toThrow();
    // Not even after a reload (only the flag in localStorage is left then).
    wipeState.failed = false;
    expect(wipePending()).toBe(true);
    expect(wipeFailed()).toBe(true);
    await expect(openPhone()).rejects.toThrow();
    // Starting the app as Arlo writes nothing.
    await startDevice({ ...ARLO });
    mend();
    wipeState.failed = false;
    localStorage.removeItem(WIPE_PENDING_KEY);
    expect(await getMeta('login_id')).toBe(2);
  });

  it('whoever signs in next, the wipe is tried again first: still failing, nobody gets in', async () => {
    await setMeta(WREN);
    const mend = failPhoneDelete();
    await wipeDevice();
    // Even Wren herself (the wipe was chosen already).
    expect(await wipeIfAnotherLogin({ id: 2 })).toBe('wipe-failed');
    expect(await wipeIfAnotherLogin(ARLO)).toBe('wipe-failed');
    mend();
    expect(await wipeIfAnotherLogin(ARLO)).toBe('wiped');
    expect(await databaseThere()).toBe(false);
    expect(wipePending()).toBe(false);
    expect(localStorage.getItem(WIPE_PENDING_KEY)).toBeNull();
    // Then as usual.
    await startDevice({ ...ARLO });
    expect(await getMeta('login_id')).toBe(3);
  });

  it('while a wipe is still deleting, it is pending but not failed', async () => {
    await setMeta(WREN);
    const seen: [boolean, boolean][] = [];
    const real = indexedDB.deleteDatabase.bind(indexedDB);
    vi.spyOn(indexedDB, 'deleteDatabase').mockImplementation((name) => {
      // What another tab sees while this one is deleting.
      wipeState.failed = false;
      seen.push([wipePending(), wipeFailed()]);
      return real(name);
    });
    expect(await wipeDevice()).toBe(true);
    expect(seen).toEqual([[true, false]]);
    expect(localStorage.getItem(WIPE_PENDING_KEY)).toBeNull();
    expect(wipePending()).toBe(false);
  });

  it('a different login’s own wipe failing says so', async () => {
    await setMeta(WREN);
    const mend = failPhoneDelete();
    expect(await wipeIfAnotherLogin(ARLO)).toBe('wipe-failed');
    expect(wipePending()).toBe(true);
    mend();
  });
});
