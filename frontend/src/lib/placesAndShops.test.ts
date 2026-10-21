// The household's shops and places, held in memory: every way of signing out forgets them,
// so the next login sees none of the last one's, without a reload (#47).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, sessionEnded } from '$lib/api';
import { network } from '$lib/network.svelte';
import { signOutHere } from '$lib/offline/signOut';
import { addToQueue } from '$lib/offline/store';
import { setMeta } from '$lib/offline/phone';
import { SIGN_OUT_PENDING_KEY } from '$lib/offline/signOutPending';
import { session } from '$lib/session.svelte';
import { makeAction } from '$lib/shopping/actions';
import { fakeApi } from '$lib/testing/fakeApi';
import { ME } from '$lib/testing/fakeShopping';
import { dropPhone, freshPhone } from '$lib/testing/phone';
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
});
