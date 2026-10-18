import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deviceId } from '$lib/offline/device';
import { getMeta, phoneDatabaseName, phoneExists, setMeta } from '$lib/offline/phone';
import { addToQueue, loadCopy, readQueue, saveCopy } from '$lib/offline/store';
import { markSignOutPending, SIGN_OUT_PENDING_KEY } from '$lib/offline/signOutPending';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { makeAction } from '$lib/shopping/actions';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { fakeApi } from '$lib/testing/fakeApi';
import { fakeShopping, sampleCopy } from '$lib/testing/fakeShopping';
import { dropPhone, freshPhone } from '$lib/testing/phone';
import { load } from './+layout';

type LoadEvent = Parameters<typeof load>[0];

const open = () =>
  load({
    fetch: (...args: Parameters<typeof fetch>) => fetch(...args),
    url: new URL('http://mealwright.test/shopping'),
    untrack: <T>(fn: () => T) => fn()
  } as unknown as LoadEvent);

const WREN = { login_id: 2, login_name: 'Wren', username: 'wren', role: 'member', protocol: 1 };
const DEVICE = '11111111-2222-4333-8444-555555555555';
const signedInAs = (id: number, name: string) => ({
  'GET /setup': [200, { needs_setup: false }] as [number, unknown],
  'GET /me': [200, { id, name, username: name.toLowerCase(), role: 'member', theme: 'auto' }] as [
    number,
    unknown
  ]
});

/** Wren's phone: her copy of the list, her device ID, and `count` changes waiting. */
async function wrensPhone(count: number) {
  await setMeta({ ...WREN, device_id: DEVICE });
  await saveCopy(null, sampleCopy());
  for (let i = 0; i < count; i++) {
    await addToQueue(makeAction({ kind: 'tick', item_id: 'i-onions' }), 2, DEVICE);
  }
}

describe('opening the app (11.4)', () => {
  beforeEach(() => {
    freshPhone();
    session.me = null;
    network.reset();
  });

  afterEach(async () => {
    await dropPhone();
    vi.unstubAllGlobals();
    network.reset();
  });

  it('opens as the last signed-in person when the server can’t be reached', async () => {
    await setMeta(WREN);
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await open();
    expect(session.me).toMatchObject({ id: 2, name: 'Wren', username: 'wren', role: 'member' });
  });

  it('does the same when the reverse proxy can’t reach the server (503)', async () => {
    await setMeta(WREN);
    fakeApi({ 'GET /setup': [503, null] });
    await open();
    expect(session.me).toMatchObject({ id: 2, name: 'Wren' });
  });

  it('offline on a device nobody has signed in on: the sign-in page', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await expect(open()).rejects.toMatchObject({
      status: 307,
      location: '/sign-in?next=%2Fshopping'
    });
    expect(session.me).toBeNull();
    // Looking for whoever was here didn't make a new, empty phone database.
    expect((await indexedDB.databases()).map((db) => db.name)).not.toContain(phoneDatabaseName());
  });

  it('offline after signing out offline: the sign-in page, not the last person', async () => {
    await setMeta(WREN);
    markSignOutPending();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await expect(open()).rejects.toMatchObject({ status: 307 });
    expect(session.me).toBeNull();
    localStorage.removeItem(SIGN_OUT_PENDING_KEY);
  });

  it('a server that answers “not signed in” still goes to sign in, whoever was here', async () => {
    await setMeta(WREN);
    fakeApi({
      'GET /setup': [200, { needs_setup: false }],
      'GET /me': [401, { detail: 'Not signed in.' }]
    });
    await expect(open()).rejects.toMatchObject({
      status: 307,
      location: '/sign-in?next=%2Fshopping'
    });
    expect(session.me).toBeNull();
  });

  it('a server error that isn’t about reaching it is not hidden', async () => {
    await setMeta(WREN);
    fakeApi({ 'GET /setup': [500, { detail: 'Something broke.' }] });
    await expect(open()).rejects.toMatchObject({ status: 500 });
    expect(session.me).toBeNull();
  });

  it('a different login always starts clean: the copy goes, and a new device ID is made', async () => {
    await wrensPhone(0);
    fakeApi(signedInAs(3, 'Arlo'));
    await open();
    expect(session.me).toMatchObject({ id: 3, name: 'Arlo' });
    // Wren's copy is gone; the database now holds only Arlo, with a new device ID.
    expect(await loadCopy()).toBeNull();
    expect(await getMeta('login_id')).toBe(3);
    const fresh = await getMeta('device_id');
    expect(fresh).toMatch(/^[0-9a-f-]{36}$/);
    expect(fresh).not.toBe(DEVICE);
    expect(deviceId()).toBe(fresh);
  });

  it('the same login after its session ran out keeps the copy, the queue and the device ID, and sends the queue', async () => {
    await wrensPhone(2);
    const copy = sampleCopy();
    const { requests } = fakeShopping(copy, signedInAs(2, 'Wren'));
    await open();
    expect(session.me).toMatchObject({ id: 2, name: 'Wren' });
    expect(await loadCopy()).not.toBeNull();
    expect(await readQueue()).toHaveLength(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
    // Then the app starts the shopping list, which sends what was waiting, from the same device.
    await shoppingSync.start();
    await vi.waitFor(() => expect(shoppingSync.queue).toHaveLength(0));
    const sent = requests.filter((r) => r.path === '/shopping/actions');
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toMatchObject({ login_id: 2, device_id: DEVICE });
    expect(await readQueue()).toHaveLength(0);
    shoppingSync.forget();
  });

  it('a different login (signed in in another tab) never wipes or sends changes still waiting', async () => {
    await wrensPhone(1);
    fakeApi(signedInAs(3, 'Arlo'));
    await open();
    expect(await phoneExists()).toBe(true);
    expect(await readQueue()).toHaveLength(1);
  });
});
