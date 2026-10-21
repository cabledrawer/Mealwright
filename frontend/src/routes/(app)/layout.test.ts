import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deviceId, startDevice } from '$lib/offline/device';
import { heldChanges, takeTurnedAway } from '$lib/offline/held';
import { getMeta, phoneDatabaseName, setMeta } from '$lib/offline/phone';
import { addToQueue, loadCopy, readQueue, saveCopy } from '$lib/offline/store';
import { markSignOutPending, SIGN_OUT_PENDING_KEY } from '$lib/offline/signOutPending';
import { signOutState } from '$lib/offline/unfinished.svelte';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { makeAction } from '$lib/shopping/actions';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { fakeApi } from '$lib/testing/fakeApi';
import { fakeShopping, sampleCopy } from '$lib/testing/fakeShopping';
import { breakPhone, dropPhone, failPhoneDelete, freshPhone } from '$lib/testing/phone';
import { wipeDevice } from '$lib/offline/wipe';
import { wipePending } from '$lib/offline/wipePending.svelte';
import { releaseServerLists, serverListsHeld } from '$lib/offline/confirmed';
import { askAgain, restart, START_WAIT_MS } from '$lib/offline/opening';
import { placesAndShops } from '$lib/placesAndShops.svelte';
import { SETUP } from '$lib/session.svelte';
import { load as signInLoad } from '../(auth)/+layout';
import { load } from './+layout';

type LoadEvent = Parameters<typeof load>[0];

const said = (requests: { method: string; path: string }[]) =>
  requests.map((r) => `${r.method} ${r.path}`);

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
    signOutState.unfinished = false;
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

  it('another login’s waiting changes: the app signs this login out again and sends it to the warning, touching nothing', async () => {
    await wrensPhone(1);
    const requests = fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
    await expect(open()).rejects.toMatchObject({
      status: 307,
      location: '/sign-in?next=%2Fshopping'
    });
    // Wren's phone exactly as it was: her `meta`, her device ID, her copy and her change.
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('login_name')).toBe('Wren');
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).not.toBeNull();
    expect(await readQueue()).toHaveLength(1);
    expect(await heldChanges()).toMatchObject({ who: { id: 2, name: 'Wren' }, count: 1 });
    // Arlo's session is ended, nothing is sent, and the sign-in page will name him.
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'GET /setup',
      'GET /me',
      'DELETE /session'
    ]);
    expect(session.me).toBeNull();
    expect(takeTurnedAway()).toBe('arlo');
  });

  it('then Wren signs back in: her waiting change is sent, from her device', async () => {
    await wrensPhone(1);
    let me: [number, unknown] = [
      200,
      { id: 3, name: 'Arlo', username: 'arlo', role: 'member', theme: 'auto' }
    ];
    const { requests } = fakeShopping(sampleCopy(), {
      'GET /setup': [200, { needs_setup: false }],
      'GET /me': () => me,
      'DELETE /session': [204, null]
    });
    await expect(open()).rejects.toMatchObject({ status: 307 });
    takeTurnedAway();
    expect(requests.filter((r) => r.path === '/shopping/actions')).toEqual([]);

    me = [200, { id: 2, name: 'Wren', username: 'wren', role: 'member', theme: 'auto' }];
    await open();
    expect(session.me).toMatchObject({ id: 2, name: 'Wren' });
    await shoppingSync.start();
    await vi.waitFor(() => expect(shoppingSync.queue).toHaveLength(0));
    const sent = requests.filter((r) => r.path === '/shopping/actions');
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toMatchObject({ login_id: 2, device_id: DEVICE });
    expect(await readQueue()).toHaveLength(0);
    shoppingSync.forget();
  });

  it('a phone database that can’t be read: this login is signed out again, and nothing is wiped or written', async () => {
    await wrensPhone(1);
    const requests = fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
    const mend = breakPhone();
    try {
      await expect(open()).rejects.toMatchObject({
        status: 307,
        location: '/sign-in?next=%2Fshopping'
      });
    } finally {
      mend();
    }
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'GET /setup',
      'GET /me',
      'DELETE /session'
    ]);
    expect(session.me).toBeNull();
    expect(takeTurnedAway()).toBe('arlo');
    // Wren's phone exactly as it was.
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).not.toBeNull();
    expect(await readQueue()).toHaveLength(1);
  });

  it('a wipe that couldn’t delete the phone database: tried again, and still failing, nobody gets in', async () => {
    await wrensPhone(1);
    const mend = failPhoneDelete();
    await wipeDevice();
    const requests = fakeApi({ ...signedInAs(2, 'Wren'), 'DELETE /session': [204, null] });
    try {
      await expect(open()).rejects.toMatchObject({
        status: 307,
        location: '/sign-in?next=%2Fshopping'
      });
    } finally {
      mend();
    }
    // Signed out again, and not "turned away" (the sign-in page says the wipe failed).
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'GET /setup',
      'GET /me',
      'DELETE /session'
    ]);
    expect(session.me).toBeNull();
    expect(takeTurnedAway()).toBe('');
    expect(wipePending()).toBe(true);

    // Offline, nobody is "last signed in" either.
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await expect(open()).rejects.toMatchObject({ status: 307 });
    expect(session.me).toBeNull();
    vi.unstubAllGlobals();

    // Mended: the next start finishes the wipe, and Wren starts clean.
    fakeApi(signedInAs(2, 'Wren'));
    await open();
    expect(session.me).toMatchObject({ id: 2 });
    expect(wipePending()).toBe(false);
    expect(await readQueue()).toEqual([]);
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).not.toBe(DEVICE);
  });

  it('a phone database that can’t be read, and the login it was written for: carries on, wiping and writing nothing (cabledrawer 18 Oct)', async () => {
    await wrensPhone(1);
    await startDevice({ id: 2, name: 'Wren', username: 'wren', role: 'member' });
    const requests = fakeApi(signedInAs(2, 'Wren'));
    const mend = breakPhone();
    try {
      await open();
    } finally {
      mend();
    }
    expect(session.me).toMatchObject({ id: 2 });
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['GET /setup', 'GET /me']);
    expect(takeTurnedAway()).toBe('');
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).not.toBeNull();
    expect(await readQueue()).toHaveLength(1);
  });

  it('the server won’t end Arlo’s session (DELETE fails, GET /me works): one trip to the sign-in page, no bouncing back', async () => {
    await wrensPhone(1);
    const requests = fakeApi({
      ...signedInAs(3, 'Arlo'),
      'DELETE /session': [500, { detail: 'Something broke.' }]
    });
    await expect(open()).rejects.toMatchObject({
      status: 307,
      location: '/sign-in?next=%2Fshopping'
    });
    expect(signOutState.unfinished).toBe(true);
    // The sign-in page then stays: it doesn't send Arlo's cookie back into the app.
    const signInPage = () =>
      signInLoad({
        fetch: (...args: Parameters<typeof fetch>) => fetch(...args),
        url: new URL('http://mealwright.test/sign-in?next=%2Fshopping')
      } as unknown as Parameters<typeof signInLoad>[0]);
    await expect(signInPage()).resolves.toMatchObject({ setup: { needs_setup: false } });
    await expect(signInPage()).resolves.toMatchObject({ setup: { needs_setup: false } });
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'GET /setup',
      'GET /me',
      'DELETE /session',
      'GET /setup',
      'GET /setup'
    ]);
    // Nothing wiped: Wren's phone exactly as it was.
    expect(session.me).toBeNull();
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).not.toBeNull();
    expect(await readQueue()).toHaveLength(1);
    expect(takeTurnedAway()).toBe('arlo');
  });

  it('a session already gone (401) counts as signed out: the sign-in page works as usual', async () => {
    await wrensPhone(1);
    fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [401, { detail: 'Not signed in.' }] });
    await expect(open()).rejects.toMatchObject({ status: 307 });
    expect(signOutState.unfinished).toBe(false);
    takeTurnedAway();
  });
});

describe('opening the app on a weak signal (cabledrawer 20 Oct, hand test)', () => {
  const { rerun } = restart;
  const begin = async (): Promise<void> => {
    await open();
  };
  /** The layout running again for a late answer (in the app: invalidateAll). */
  let reruns: Promise<void>[];
  let releases: (() => void)[];

  /** A server whose answers hang until release(): `asked` lists each request as it is made. */
  function slowServer(answer: typeof fetch) {
    const asked: string[] = [];
    let release!: () => void;
    const released = new Promise<void>((done) => (release = done));
    releases.push(release);
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      asked.push(
        `${args[1]?.method ?? 'GET'} ${
          String(args[0])
            .replace(/^\/api\/v1/, '')
            .split('?')[0]
        }`
      );
      await released;
      return answer(...args);
    });
    return { asked, release };
  }

  /** fakeApi's answers, slowly. */
  function slowly(routes: Parameters<typeof fakeApi>[0]) {
    const requests = fakeApi(routes);
    return { ...slowServer(globalThis.fetch), requests };
  }

  /** Only these requests ("GET /me") hang until release(); the rest answer at once. */
  function holdOnly(held: string[]) {
    const inner = globalThis.fetch;
    const asked: string[] = [];
    let release!: () => void;
    const released = new Promise<void>((done) => (release = done));
    releases.push(release);
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      const name = `${args[1]?.method ?? 'GET'} ${
        String(args[0])
          .replace(/^\/api\/v1/, '')
          .split('?')[0]
      }`;
      asked.push(name);
      if (held.includes(name)) await released;
      return inner(...args);
    });
    return { asked, release };
  }

  const timed = async <T>(work: () => Promise<T>) => {
    const started = performance.now();
    const result = await work();
    return { result, ms: performance.now() - started };
  };

  beforeEach(() => {
    freshPhone();
    session.me = null;
    network.reset();
    signOutState.unfinished = false;
    reruns = [];
    releases = [];
    restart.rerun = () => {
      const again = begin();
      reruns.push(again);
      return again.then(
        () => undefined,
        () => undefined
      );
    };
  });

  afterEach(async () => {
    for (const release of releases) release();
    await Promise.allSettled(reruns);
    releaseServerLists();
    restart.rerun = rerun;
    shoppingSync.forget();
    takeTurnedAway();
    await dropPhone();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    network.reset();
  });

  it('opens at once as the last signed-in person, and the same login then carries on in place', async () => {
    await wrensPhone(1);
    const server = slowly(signedInAs(2, 'Wren'));
    const { ms } = await timed(begin);
    expect(ms).toBeLessThan(START_WAIT_MS + 500);
    expect(session.me).toMatchObject({ id: 2, name: 'Wren' });
    expect(serverListsHeld()).not.toBeNull();
    const opened = session.me;

    server.release();
    await vi.waitFor(() => expect(serverListsHeld()).toBeNull());
    expect(reruns).toHaveLength(1);
    await expect(reruns[0]).resolves.toBeUndefined();
    // The same person, the very same object (so the layout keeps its Undo), not started again.
    expect(session.me).toBe(opened);
    expect(server.requests.map((r) => `${r.method} ${r.path}`)).toEqual(['GET /setup', 'GET /me']);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).not.toBeNull();
    expect(await readQueue()).toHaveLength(1);
  });

  it('the list isn’t asked for until the server has said who is signed in; sending starts at once', async () => {
    await wrensPhone(1);
    const copy = sampleCopy();
    const shop = fakeShopping(copy, signedInAs(2, 'Wren'));
    // Only the start's questions hang: the send is answered at once, so only the hold keeps
    // the list from being asked for.
    const server = holdOnly(['GET /setup', 'GET /me']);
    await begin();
    await shoppingSync.start();
    await vi.waitFor(() => expect(shoppingSync.queue).toHaveLength(0));
    const listed = shoppingSync.refresh();
    await new Promise((done) => setTimeout(done, 200));
    // The waiting change has gone (11.6) and is applied once; the list is not asked for.
    expect(server.asked).toEqual(['GET /setup', 'POST /shopping/actions']);
    expect(shop.actions).toHaveLength(1);

    server.release();
    await listed;
    const order = shop.requests.map((r) => `${r.method} ${r.path}`);
    expect(order.indexOf('GET /me')).toBeLessThan(order.indexOf('GET /shopping/changes'));
    // Sent once, and applied once.
    expect(shop.actions).toHaveLength(1);
  });

  it('a late “not signed in”: the sign-in page, nothing wiped, and the list never asked for', async () => {
    await wrensPhone(1);
    const server = slowly({
      'GET /setup': [200, { needs_setup: false }],
      'GET /me': [401, { detail: 'Not signed in.' }]
    });
    await begin();
    expect(session.me).toMatchObject({ id: 2 });
    const listed = shoppingSync.refresh().catch((error: unknown) => error);

    server.release();
    await vi.waitFor(() => expect(reruns).toHaveLength(1));
    await expect(reruns[0]).rejects.toMatchObject({
      status: 307,
      location: '/sign-in?next=%2Fshopping'
    });
    expect(await listed).toMatchObject({ status: 401, detail: 'Please sign in again.' });
    expect(session.me).toBeNull();
    expect(server.asked).toEqual(['GET /setup', 'GET /me']);
    // Wren's phone exactly as it was (11.5: her change waits for her).
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).not.toBeNull();
    expect(await readQueue()).toHaveLength(1);
  });

  it('a late different login, with changes waiting: signed out again and sent to the warning, touching nothing', async () => {
    await wrensPhone(1);
    const saved = await loadCopy();
    const server = slowly({
      ...signedInAs(3, 'Arlo'),
      'DELETE /session': [204, null],
      'POST /shopping/actions': [409, { code: 'other_login', detail: 'Another login.' }]
    });
    await begin();
    expect(session.me).toMatchObject({ id: 2, name: 'Wren' });
    // The app starts sending Wren's change meanwhile: the server turns it away (11.5).
    await shoppingSync.start();
    const listed = shoppingSync.refresh().catch((error: unknown) => error);

    server.release();
    await vi.waitFor(() => expect(reruns).toHaveLength(1));
    await expect(reruns[0]).rejects.toMatchObject({
      status: 307,
      location: '/sign-in?next=%2Fshopping'
    });
    expect(await listed).toMatchObject({ status: 401, detail: 'Please sign in again.' });
    expect(session.me).toBeNull();
    expect(takeTurnedAway()).toBe('arlo');
    expect(server.requests.map((r) => `${r.method} ${r.path}`).sort()).toEqual(
      ['DELETE /session', 'GET /me', 'GET /setup', 'POST /shopping/actions'].sort()
    );
    // Wren's phone exactly as it was: her `meta`, her device ID, her copy and her change.
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('login_name')).toBe('Wren');
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).toEqual(saved);
    expect(await readQueue()).toHaveLength(1);
    expect(await heldChanges()).toMatchObject({ who: { id: 2, name: 'Wren' }, count: 1 });
  });

  it('a late different login with nothing waiting: nothing wiped while the screen is up; signed out to the sign-in page, and the next start wipes', async () => {
    await wrensPhone(0);
    const saved = await loadCopy();
    const server = slowly({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
    await begin();
    expect(session.me).toMatchObject({ id: 2 });
    await shoppingSync.start();
    expect(shoppingSync.copy).not.toBeNull();
    placesAndShops.places = [{ id: 9, name: 'Arlo’s fridge', kind: 'fridge' }];

    server.release();
    await vi.waitFor(() => expect(reruns).toHaveLength(1));
    await expect(reruns[0]).rejects.toMatchObject({
      status: 307,
      location: '/sign-in?next=%2Fshopping'
    });
    expect(session.me).toBeNull();
    // With Arlo's username filled in, as a login turned away at the start.
    expect(takeTurnedAway()).toBe('arlo');
    expect(server.requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'GET /setup',
      'GET /me',
      'DELETE /session'
    ]);
    // Wren's phone untouched; nothing she was shown stays in memory.
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
    expect(await loadCopy()).toEqual(saved);
    expect(shoppingSync.copy).toBeNull();
    expect(placesAndShops.places).toEqual([]);
    expect(serverListsHeld()).toBeNull();

    // Arlo signs in: the next start wipes before anything shows, as on any start.
    fakeApi(signedInAs(3, 'Arlo'));
    await open();
    expect(session.me).toMatchObject({ id: 3, name: 'Arlo' });
    expect(await loadCopy()).toBeNull();
    expect(await getMeta('login_id')).toBe(3);
    expect(await getMeta('device_id')).not.toBe(DEVICE);
    await shoppingSync.start();
    expect(shoppingSync.copy).toBeNull();
  });

  it('a tick while a late different login is being signed out is Wren’s: kept, never sent as Arlo, and warned about', async () => {
    await wrensPhone(0);
    const posted: unknown[] = [];
    fakeApi({
      ...signedInAs(3, 'Arlo'),
      'DELETE /session': [204, null],
      'POST /shopping/actions': (request) => {
        posted.push(request.body);
        return [409, { code: 'other_login', detail: 'Another login.' }];
      }
    });
    const server = holdOnly(['GET /setup', 'GET /me']);
    const signingOut = holdOnly(['DELETE /session']);
    await begin();
    await shoppingSync.start();

    server.release();
    // The answer has come; the sign-out it leads to is still on its way. Wren ticks.
    await vi.waitFor(() => expect(signingOut.asked).toContain('DELETE /session'));
    expect(session.me).toMatchObject({ id: 2 });
    await new Promise<void>((queued) => {
      shoppingSync
        .enqueue(makeAction({ kind: 'tick', item_id: 'i-onions' }), queued)
        .catch(() => {});
    });
    signingOut.release();
    await vi.waitFor(() => expect(reruns).toHaveLength(1));
    await expect(reruns[0]).rejects.toMatchObject({ status: 307 });

    // Her tick is in her own queue, under her login, on her untouched phone.
    const queue = await readQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0]).toMatchObject({ login_id: 2, device_id: DEVICE });
    expect(await getMeta('login_id')).toBe(2);
    expect(await heldChanges()).toMatchObject({ who: { id: 2, name: 'Wren' }, count: 1 });
    // Anything sent named Wren's login (and the server refused it under Arlo's session).
    for (const body of posted) expect(body).toMatchObject({ login_id: 2 });

    // Arlo's next start doesn't wipe it: he's turned away to the warning again.
    takeTurnedAway();
    fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
    await expect(open()).rejects.toMatchObject({ status: 307 });
    expect(takeTurnedAway()).toBe('arlo');
    expect(await readQueue()).toHaveLength(1);
    expect(await getMeta('device_id')).toBe(DEVICE);
  });

  it('a late “needs setting up”: the setup page, nobody signed in, nothing wiped', async () => {
    await wrensPhone(1);
    const server = slowly({ 'GET /setup': [200, { needs_setup: true }] });
    await begin();
    server.release();
    await vi.waitFor(() => expect(reruns).toHaveLength(1));
    await expect(reruns[0]).rejects.toMatchObject({ status: 307, location: SETUP });
    expect(session.me).toBeNull();
    expect(serverListsHeld()).toBeNull();
    expect(await getMeta('login_id')).toBe(2);
    expect(await readQueue()).toHaveLength(1);
  });

  it('a late server error: the error page, and the lists stay held, as who is signed in isn’t known', async () => {
    await wrensPhone(1);
    const server = slowly({ 'GET /setup': [500, { detail: 'Something broke.' }] });
    await begin();
    const listed = shoppingSync.refresh().catch((error: unknown) => error);
    server.release();
    await vi.waitFor(() => expect(reruns).toHaveLength(1));
    await expect(reruns[0]).rejects.toMatchObject({ status: 500 });
    expect(serverListsHeld()).not.toBeNull();
    await new Promise((done) => setTimeout(done, 100));
    expect(server.asked).toEqual(['GET /setup']);
    expect(await getMeta('login_id')).toBe(2);
    expect(await readQueue()).toHaveLength(1);

    // The next start that hears from the server decides, and lets the list through.
    fakeShopping(sampleCopy(), signedInAs(2, 'Wren'));
    await open();
    await expect(listed).resolves.toMatchObject({ cursor: expect.any(Number) });
    expect(serverListsHeld()).toBeNull();
  });

  it('a late answer after a wipe that couldn’t delete the phone database: nobody gets in', async () => {
    await wrensPhone(1);
    const server = slowly({
      ...signedInAs(2, 'Wren'),
      'DELETE /session': [204, null]
    });
    await begin();
    // Another tab's wipe fails meanwhile.
    const mend = failPhoneDelete();
    try {
      await wipeDevice();
      server.release();
      await vi.waitFor(() => expect(reruns).toHaveLength(1));
      await expect(reruns[0]).rejects.toMatchObject({
        status: 307,
        location: '/sign-in?next=%2Fshopping'
      });
    } finally {
      mend();
    }
    expect(session.me).toBeNull();
    // Not "turned away": the sign-in page says the wipe failed.
    expect(takeTurnedAway()).toBe('');
    expect(wipePending()).toBe(true);
    expect(server.requests.map((r) => `${r.method} ${r.path}`)).toContain('DELETE /session');
  });

  it('a late different login after a wipe that couldn’t delete the phone database: not turned away either', async () => {
    await wrensPhone(0);
    const server = slowly({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
    await begin();
    const mend = failPhoneDelete();
    try {
      await wipeDevice();
      server.release();
      await vi.waitFor(() => expect(reruns).toHaveLength(1));
      await expect(reruns[0]).rejects.toMatchObject({ status: 307 });
    } finally {
      mend();
    }
    expect(session.me).toBeNull();
    expect(takeTurnedAway()).toBe('');
    expect(wipePending()).toBe(true);
  });

  it('a late answer that the server still can’t be reached: carries on as opened', async () => {
    await wrensPhone(1);
    const server = slowServer(() => Promise.reject(new TypeError('Failed to fetch')));
    await begin();
    const opened = session.me;
    server.release();
    await vi.waitFor(() => expect(serverListsHeld()).toBeNull());
    expect(reruns).toEqual([]);
    expect(session.me).toBe(opened);
    expect(await readQueue()).toHaveLength(1);
  });

  describe('then the server can be reached again (#47): it’s asked again who is signed in', () => {
    /** A slow start whose late answer was "still no connection". */
    async function openedStillOffline() {
      const server = slowServer(() => Promise.reject(new TypeError('Failed to fetch')));
      await begin();
      server.release();
      await vi.waitFor(() => expect(serverListsHeld()).toBeNull());
      expect(reruns).toEqual([]);
      vi.unstubAllGlobals();
    }

    it('the same login: carries on in place, as it opened', async () => {
      await wrensPhone(1);
      await openedStillOffline();
      const opened = session.me;
      const requests = fakeApi(signedInAs(2, 'Wren'));
      await askAgain();
      expect(said(requests)).toEqual(['GET /setup', 'GET /me']);
      expect(reruns).toHaveLength(1);
      await expect(reruns[0]).resolves.toBeUndefined();
      expect(session.me).toBe(opened);
      expect(serverListsHeld()).toBeNull();
      expect(await getMeta('device_id')).toBe(DEVICE);
      expect(await readQueue()).toHaveLength(1);
      // Known now: never asked again.
      await askAgain();
      expect(said(requests)).toEqual(['GET /setup', 'GET /me']);
    });

    it('a different login: signed out again to the sign-in page, and nothing of Wren’s kept in memory', async () => {
      await wrensPhone(0);
      const saved = await loadCopy();
      await openedStillOffline();
      placesAndShops.places = [{ id: 9, name: 'Wren’s fridge', kind: 'fridge' }];
      const requests = fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
      await askAgain();
      expect(reruns).toHaveLength(1);
      await expect(reruns[0]).rejects.toMatchObject({
        status: 307,
        location: '/sign-in?next=%2Fshopping'
      });
      expect(said(requests)).toEqual(['GET /setup', 'GET /me', 'DELETE /session']);
      expect(session.me).toBeNull();
      expect(takeTurnedAway()).toBe('arlo');
      expect(placesAndShops.places).toEqual([]);
      // Nothing wiped while the screen was up, as for any late answer.
      expect(await getMeta('device_id')).toBe(DEVICE);
      expect(await loadCopy()).toEqual(saved);
    });

    it('nobody signed in: the sign-in page, nothing wiped', async () => {
      await wrensPhone(1);
      await openedStillOffline();
      fakeApi({
        'GET /setup': [200, { needs_setup: false }],
        'GET /me': [401, { detail: 'Not signed in.' }]
      });
      await askAgain();
      await expect(reruns[0]).rejects.toMatchObject({ status: 307 });
      expect(session.me).toBeNull();
      expect(await readQueue()).toHaveLength(1);
    });

    it('the lists are held back until it has answered; still no connection: asked again next time', async () => {
      await wrensPhone(0);
      await openedStillOffline();
      const server = slowServer(() => Promise.reject(new TypeError('Failed to fetch')));
      const asking = askAgain();
      await vi.waitFor(() => expect(server.asked).toEqual(['GET /setup']));
      expect(serverListsHeld()).not.toBeNull();
      // Asked once at a time.
      await askAgain();
      expect(server.asked).toEqual(['GET /setup']);
      server.release();
      await asking;
      expect(serverListsHeld()).toBeNull();
      expect(reruns).toEqual([]);
      vi.unstubAllGlobals();
      fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
      await askAgain();
      await expect(reruns[0]).rejects.toMatchObject({ status: 307 });
      expect(takeTurnedAway()).toBe('arlo');
    });

    it('a server error when asked again: carries on as opened, no error page, and asked again next time', async () => {
      await wrensPhone(0);
      await openedStillOffline();
      const opened = session.me;
      const requests = fakeApi({ 'GET /setup': [500, { detail: 'Something broke.' }] });
      await askAgain();
      expect(said(requests)).toEqual(['GET /setup']);
      expect(reruns).toEqual([]);
      expect(session.me).toBe(opened);
      expect(serverListsHeld()).toBeNull();
      vi.unstubAllGlobals();
      fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
      await askAgain();
      await expect(reruns[0]).rejects.toMatchObject({ status: 307 });
      expect(takeTurnedAway()).toBe('arlo');
    });

    it('opened offline at once: asked as soon as it’s back', async () => {
      await wrensPhone(0);
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      await begin();
      expect(session.me).toMatchObject({ id: 2 });
      vi.unstubAllGlobals();
      fakeApi({ ...signedInAs(3, 'Arlo'), 'DELETE /session': [204, null] });
      await askAgain();
      await expect(reruns[0]).rejects.toMatchObject({ status: 307 });
      expect(session.me).toBeNull();
    });

    it('a start the server answered in time never asks again', async () => {
      await wrensPhone(0);
      const requests = fakeApi(signedInAs(2, 'Wren'));
      await begin();
      expect(said(requests)).toEqual(['GET /setup', 'GET /me']);
      await askAgain();
      expect(said(requests)).toEqual(['GET /setup', 'GET /me']);
      expect(reruns).toEqual([]);
    });
  });

  it('the browser says it’s offline: no wait at all, with or without someone to open as', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    slowServer(() => Promise.reject(new TypeError('Failed to fetch')));
    const nobody = await timed(() => begin().catch((error: unknown) => error));
    expect(nobody.result).toMatchObject({ status: 307, location: '/sign-in?next=%2Fshopping' });
    expect(nobody.ms).toBeLessThan(START_WAIT_MS);

    await setMeta(WREN);
    const wren = await timed(begin);
    expect(wren.ms).toBeLessThan(START_WAIT_MS);
    expect(session.me).toMatchObject({ id: 2, name: 'Wren' });
  });

  it('someone else just signed in waits for the server rather than opening as the last person', async () => {
    await wrensPhone(0);
    session.me = { id: 3, name: 'Arlo', username: 'arlo', role: 'member', theme: 'auto' };
    const server = slowly(signedInAs(3, 'Arlo'));
    let opened = false;
    const opening = begin().then(() => (opened = true));
    await new Promise((done) => setTimeout(done, START_WAIT_MS + 300));
    expect(opened).toBe(false);
    expect(session.me).toMatchObject({ id: 3 });

    server.release();
    await opening;
    expect(session.me).toMatchObject({ id: 3, name: 'Arlo' });
    expect(reruns).toEqual([]);
  });
});
