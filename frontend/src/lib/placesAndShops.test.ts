// The household's shops and places, held in memory: every way of signing out forgets them,
// so the next login sees none of the last one's, without a reload (#47).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, sessionEnded } from '#lib/api.js';
import { network } from '#lib/network.svelte.js';
import { signOutHere } from '#lib/offline/signOut.js';
import { addToQueue } from '#lib/offline/store.js';
import { setMeta } from '#lib/offline/phone.js';
import { SIGN_OUT_PENDING_KEY } from '#lib/offline/signOutPending.js';
import { session } from '#lib/session.svelte.js';
import { makeAction } from '#lib/shopping/actions.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { placesAndShops } from './placesAndShops.svelte';

type Routes = Parameters<typeof fakeApi>[0];

const WRENS: Routes = {
  'GET /places': [200, [{ id: 1, name: 'Wren’s fridge', kind: 'fridge' }]],
  'GET /shops': [200, [{ id: 1, name: 'Wren’s corner shop' }]]
};
const ARLOS: Routes = {
  'GET /places': [200, [{ id: 7, name: 'Arlo’s freezer', kind: 'freezer' }]],
  'GET /shops': [200, [{ id: 7, name: 'Arlo’s market' }]]
};

/** Wren is signed in and her shops and places have been fetched. */
async function wrensLoaded(more: Routes = {}) {
  fakeApi({ ...WRENS, ...more });
  await placesAndShops.load();
  expect(placesAndShops.places.map((p) => p.name)).toEqual(['Wren’s fridge']);
  expect(placesAndShops.shops.map((s) => s.name)).toEqual(['Wren’s corner shop']);
}

/** Arlo signs in next (no reload): he sees only his own. */
async function arloSeesOnlyHis() {
  expect(placesAndShops.places).toEqual([]);
  expect(placesAndShops.shops).toEqual([]);
  // (Signed out offline, the old session is ended first, as before any request.)
  const requests = fakeApi({ ...ARLOS, 'DELETE /session': [204, null] });
  await placesAndShops.load();
  const asked = requests.map((r) => `${r.method} ${r.path}`).filter((r) => r.startsWith('GET'));
  expect(asked.sort()).toEqual(['GET /places', 'GET /shops']);
  expect(placesAndShops.places.map((p) => p.name)).toEqual(['Arlo’s freezer']);
  expect(placesAndShops.shops.map((s) => s.name)).toEqual(['Arlo’s market']);
}

beforeEach(async () => {
  freshPhone();
  session.me = { ...ME };
  network.reset();
  placesAndShops.forget();
  await setMeta({ login_id: ME.id, login_name: ME.name, username: ME.username });
});

afterEach(async () => {
  placesAndShops.forget();
  await dropPhone();
  vi.unstubAllGlobals();
  network.reset();
  localStorage.removeItem(SIGN_OUT_PENDING_KEY);
});

describe('signing out forgets the household’s shops and places', () => {
  it('the Sign out button', async () => {
    await wrensLoaded({ 'DELETE /session': [204, null] });
    expect(await signOutHere()).toBe('signed-out');
    await arloSeesOnlyHis();
  });

  it('the sign-out warning’s “Sign out and lose it”', async () => {
    await wrensLoaded();
    const shown = await addToQueue(makeAction({ kind: 'tick', item_id: 'a' }), ME.id, 'device-1');
    network.offline = true;
    expect(await signOutHere([shown.action.id])).toBe('signed-out');
    network.reset();
    await arloSeesOnlyHis();
  });

  it('a 401 that signs you out', async () => {
    await wrensLoaded({ 'GET /pantry': [401, { detail: 'Not signed in.' }] });
    await expect(api('GET', '/pantry')).rejects.toMatchObject({ status: 401 });
    await arloSeesOnlyHis();
  });

  it('the live stream saying you’ve been signed out', async () => {
    await wrensLoaded();
    sessionEnded();
    await arloSeesOnlyHis();
  });

  it('an answer that comes after signing out is dropped, not shown to the next login', async () => {
    let answer!: () => void;
    const answered = new Promise<void>((done) => (answer = done));
    fakeApi(WRENS);
    const fetched = globalThis.fetch;
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      await answered;
      return fetched(...args);
    });
    const loading = placesAndShops.load();
    sessionEnded();
    answer();
    await loading;
    await arloSeesOnlyHis();
  });

  it('a shop added just before signing out isn’t kept for the next login', async () => {
    await wrensLoaded({ 'POST /shops': [201, { id: 2, name: 'Wren’s market' }] });
    let answer!: () => void;
    const answered = new Promise<void>((done) => (answer = done));
    const fetched = globalThis.fetch;
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      await answered;
      return fetched(...args);
    });
    const adding = placesAndShops.addShop('Wren’s market');
    sessionEnded();
    answer();
    await adding;
    expect(placesAndShops.shops).toEqual([]);
    await arloSeesOnlyHis();
  });
  it('"+ Place" adds the place, last, with the name tidied and the kind sent', async () => {
    await wrensLoaded();
    const requests = fakeApi({
      ...WRENS,
      'POST /places': [201, { id: 2, name: 'Garage fridge', kind: 'fridge' }]
    });
    const made = await placesAndShops.addPlace('  Garage fridge ', 'fridge');
    expect(made).toEqual({ id: 2, name: 'Garage fridge', kind: 'fridge' });
    expect(requests[0]?.body).toEqual({ name: 'Garage fridge', kind: 'fridge' });
    expect(placesAndShops.places.map((p) => p.name)).toEqual(['Wren’s fridge', 'Garage fridge']);
  });

  it('a place the household already has is picked, not added twice', async () => {
    await wrensLoaded({
      'POST /places': [
        409,
        {
          code: 'name_taken',
          detail: 'There’s already a place called Wren’s fridge.',
          place: { id: 1, name: 'Wren’s fridge', kind: 'fridge' }
        }
      ]
    });
    const made = await placesAndShops.addPlace('wren’s FRIDGE', 'cupboard');
    expect(made).toEqual({ id: 1, name: 'Wren’s fridge', kind: 'fridge' });
    expect(placesAndShops.places.map((p) => p.name)).toEqual(['Wren’s fridge']);
  });

  it('a shop the household already has is picked, not added twice (409 name_taken)', async () => {
    await wrensLoaded({
      'POST /shops': [
        409,
        {
          code: 'name_taken',
          detail: 'There’s already a shop called Wren’s corner shop.',
          shop: { id: 1, name: 'Wren’s corner shop' }
        }
      ]
    });
    const made = await placesAndShops.addShop('wren’s CORNER shop');
    expect(made).toEqual({ id: 1, name: 'Wren’s corner shop' });
    expect(placesAndShops.shops.map((s) => s.name)).toEqual(['Wren’s corner shop']);
  });

  it('a place that is already held by the other server list is put in once', async () => {
    await wrensLoaded({
      'POST /places': [
        409,
        {
          code: 'name_taken',
          detail: 'x',
          place: { id: 9, name: 'Larder', kind: 'cupboard' }
        }
      ]
    });
    await placesAndShops.addPlace('larder', 'cupboard');
    await placesAndShops.addPlace('larder', 'cupboard');
    expect(placesAndShops.places.filter((p) => p.id === 9)).toHaveLength(1);
  });

  it('a place added just before signing out isn’t kept for the next login', async () => {
    await wrensLoaded({ 'POST /places': [201, { id: 2, name: 'Wren’s shed', kind: 'cupboard' }] });
    let answer!: () => void;
    const answered = new Promise<void>((done) => (answer = done));
    const fetched = globalThis.fetch;
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      await answered;
      return fetched(...args);
    });
    const adding = placesAndShops.addPlace('Wren’s shed', 'cupboard');
    sessionEnded();
    answer();
    await adding;
    expect(placesAndShops.places).toEqual([]);
    await arloSeesOnlyHis();
  });
  it('a place added before the list was fetched leaves the whole list, not just the new place', async () => {
    fakeApi({
      ...WRENS,
      'GET /places': [
        200,
        [
          { id: 1, name: 'Wren’s fridge', kind: 'fridge' },
          { id: 2, name: 'Shed', kind: 'cupboard' }
        ]
      ],
      'POST /places': [201, { id: 2, name: 'Shed', kind: 'cupboard' }]
    });
    expect(placesAndShops.places).toEqual([]);
    await placesAndShops.addPlace('Shed', 'cupboard');
    expect(placesAndShops.places.map((p) => p.name)).toEqual(['Wren’s fridge', 'Shed']);
  });

  describe('a place made on another phone (M1)', () => {
    const WITH_SHED: Routes = {
      'GET /places': [
        200,
        [
          { id: 1, name: 'Wren’s fridge', kind: 'fridge' },
          { id: 5, name: 'Shed', kind: 'cupboard' }
        ]
      ],
      'GET /shops': [200, []]
    };

    it('load(true) fetches again after they are loaded', async () => {
      await wrensLoaded();
      fakeApi(WITH_SHED);
      await placesAndShops.load(true);
      expect(placesAndShops.places.map((p) => p.name)).toEqual(['Wren’s fridge', 'Shed']);
    });

    it('an answer asked for before a place or shop was added keeps the new one', async () => {
      await wrensLoaded({
        'POST /places': [201, { id: 2, name: 'Garage fridge', kind: 'fridge' }],
        'POST /shops': [201, { id: 2, name: 'Wren’s market' }]
      });
      let answer!: () => void;
      const answered = new Promise<void>((done) => (answer = done));
      const fetched = globalThis.fetch;
      vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
        if ((args[1]?.method ?? 'GET') === 'GET') await answered;
        return fetched(...args);
      });
      // The editor opens (fetching again), then "+ Place" and "+ Shop" answer first.
      const loading = placesAndShops.load(true);
      await placesAndShops.addPlace('Garage fridge', 'fridge');
      await placesAndShops.addShop('Wren’s market');
      answer();
      await loading;
      expect(placesAndShops.places.map((p) => p.name)).toEqual(['Wren’s fridge', 'Garage fridge']);
      expect(placesAndShops.shops.map((s) => s.name)).toEqual([
        'Wren’s corner shop',
        'Wren’s market'
      ]);
      // A fetch asked for afterwards is the server's whole word.
      fakeApi(WRENS);
      await placesAndShops.load(true);
      expect(placesAndShops.places.map((p) => p.name)).toEqual(['Wren’s fridge']);
    });

    it('a picker given a place that is not in the list fetches them again, once', async () => {
      await wrensLoaded();
      const requests = fakeApi(WITH_SHED);
      await placesAndShops.reloadFor(5);
      expect(placesAndShops.places.map((p) => p.id)).toEqual([1, 5]);
      const asked = requests.filter((r) => r.path === '/places').length;
      expect(asked).toBe(1);
      // A place the server does not have either isn't asked about again and again.
      await placesAndShops.reloadFor(99);
      await placesAndShops.reloadFor(99);
      expect(requests.filter((r) => r.path === '/places')).toHaveLength(2);
    });

    it('several pickers given the same unknown place at once fetch once', async () => {
      await wrensLoaded();
      const requests = fakeApi(WITH_SHED);
      await Promise.all([placesAndShops.reloadFor(5), placesAndShops.reloadFor(5)]);
      expect(placesAndShops.places.map((p) => p.id)).toEqual([1, 5]);
      expect(requests.filter((r) => r.path === '/places')).toHaveLength(1);
    });

    it('a place that is in the list, or none, fetches nothing', async () => {
      await wrensLoaded();
      const requests = fakeApi(WITH_SHED);
      await placesAndShops.reloadFor(1);
      await placesAndShops.reloadFor(null);
      expect(requests).toHaveLength(0);
    });
  });
});
