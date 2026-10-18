// Signing out (docs/dev/sync-protocol.md section 12): sending first for up to 5 s, the wipe
// before the server sign-out, and the "sign-out pending" flag when the server can't be
// reached (cabledrawer 18 Oct: it outlasts the wipe, and once back the server session is ended
// before any other request).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getMe } from '$lib/api';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { makeAction } from '$lib/shopping/actions';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { fakeApi, type FakeRequest } from '$lib/testing/fakeApi';
import { ME } from '$lib/testing/fakeShopping';
import { breakPhone, dropPhone, freshPhone } from '$lib/testing/phone';
import { UNREADABLE } from './held';
import { addToQueue } from './store';
import { phoneDatabaseName, setMeta } from './phone';
import { endSession, signOutHere, trySending } from './signOut';
import {
  endPendingSignOut,
  endPendingSignOutWhenOnline,
  markSignOutPending,
  SIGN_OUT_PENDING_KEY,
  signOutPending
} from './signOutPending';
import { signOutState } from './unfinished.svelte';
import { wipeDevice } from './wipe';

const exists = async () =>
  (await indexedDB.databases()).some((db) => db.name === phoneDatabaseName());

const said = (requests: FakeRequest[]) => requests.map((r) => `${r.method} ${r.path}`);

const unreachable = () => {
  const tried: string[] = [];
  vi.stubGlobal('fetch', (input: string, init: RequestInit = {}) => {
    tried.push(`${init.method ?? 'GET'} ${String(input)}`);
    return Promise.reject(new TypeError('Failed to fetch'));
  });
  return tried;
};

beforeEach(() => {
  freshPhone();
  session.me = { ...ME };
  network.reset();
  localStorage.removeItem(SIGN_OUT_PENDING_KEY);
  signOutState.unfinished = false;
});

afterEach(async () => {
  vi.restoreAllMocks();
  await dropPhone();
  vi.unstubAllGlobals();
  network.reset();
  localStorage.removeItem(SIGN_OUT_PENDING_KEY);
});

describe('the "sign-out pending" flag', () => {
  it('outlasts the wipe, which deletes the phone database', async () => {
    await setMeta({ login_id: 1, login_name: 'Tess', username: 'tess' });
    markSignOutPending();
    await wipeDevice();
    expect(await exists()).toBe(false);
    expect(signOutPending()).toBe(true);
    expect(localStorage.getItem(SIGN_OUT_PENDING_KEY)).toBe('1');
  });

  it('once back, the server session is ended before any other request', async () => {
    markSignOutPending();
    const requests = fakeApi({
      'DELETE /session': [204, null],
      'GET /me': [401, { detail: 'Not signed in.' }]
    });
    expect(await getMe()).toBeNull();
    expect(said(requests)).toEqual(['DELETE /session', 'GET /me']);
    expect(signOutPending()).toBe(false);
  });

  it('while the server still can’t be reached, nothing else is sent', async () => {
    markSignOutPending();
    const tried = unreachable();
    await expect(api('GET', '/pantry')).rejects.toMatchObject({ status: 0 });
    expect(tried).toEqual(['DELETE /api/v1/session']);
    expect(signOutPending()).toBe(true);
  });

  it('a session already gone (401) counts as ended', async () => {
    markSignOutPending();
    const requests = fakeApi({
      'DELETE /session': [401, { detail: 'Not signed in.' }],
      'GET /pantry': [200, []]
    });
    await api('GET', '/pantry');
    expect(said(requests)).toEqual(['DELETE /session', 'GET /pantry']);
    expect(signOutPending()).toBe(false);
  });

  it('a server that answers but won’t end it: “couldn’t finish signing out”, until it does', async () => {
    markSignOutPending();
    let answer: [number, unknown] = [500, { detail: 'Something broke.' }];
    fakeApi({ 'DELETE /session': () => answer });
    expect(await endPendingSignOut()).toBe(false);
    expect(signOutState.unfinished).toBe(true);
    expect(signOutPending()).toBe(true);
    answer = [204, null];
    expect(await endPendingSignOut()).toBe(true);
    expect(signOutState.unfinished).toBe(false);
    expect(signOutPending()).toBe(false);
  });

  it('the reverse proxy saying it can’t reach the server (503) is only offline', async () => {
    markSignOutPending();
    fakeApi({ 'DELETE /session': [503, null] });
    expect(await endPendingSignOut()).toBe(false);
    expect(signOutState.unfinished).toBe(false);
    expect(signOutPending()).toBe(true);
  });

  it('the connection check ends the session before asking the server anything else', async () => {
    markSignOutPending();
    vi.useFakeTimers({ toFake: ['setTimeout', 'setInterval', 'Date'] });
    const asked: string[] = [];
    vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
      asked.push(`${init.method ?? 'GET'} ${String(input)}`);
      return new Response(null, { status: 204 });
    });
    try {
      network.failed();
      await network.tryNow();
    } finally {
      vi.useRealTimers();
    }
    expect(asked).toEqual(['DELETE /api/v1/session', 'GET /api/v1/version']);
    expect(signOutPending()).toBe(false);
  });
  it('the browser coming back online ends it, even with nothing else to send', async () => {
    markSignOutPending();
    const requests = fakeApi({ 'DELETE /session': [204, null] });
    const stop = endPendingSignOutWhenOnline();
    try {
      window.dispatchEvent(new Event('online'));
      await vi.waitFor(() => expect(signOutPending()).toBe(false));
    } finally {
      stop();
    }
    expect(said(requests)).toEqual(['DELETE /session']);
  });
});

describe('ending the session without wiping (the app turning a login away)', () => {
  it('ended: true, and nothing is wiped', async () => {
    await setMeta({ login_id: 2, login_name: 'Wren', username: 'wren' });
    const requests = fakeApi({ 'DELETE /session': [204, null] });
    expect(await endSession()).toBe(true);
    expect(said(requests)).toEqual(['DELETE /session']);
    expect(signOutState.unfinished).toBe(false);
    expect(await exists()).toBe(true);
  });

  it('a session already gone (401) counts as ended', async () => {
    fakeApi({ 'DELETE /session': [401, { detail: 'Not signed in.' }] });
    expect(await endSession()).toBe(true);
    expect(signOutState.unfinished).toBe(false);
  });

  it('refused or out of reach: false, “couldn’t finish signing out”, and nothing is wiped', async () => {
    await setMeta({ login_id: 2, login_name: 'Wren', username: 'wren' });
    fakeApi({ 'DELETE /session': [500, { detail: 'Something broke.' }] });
    expect(await endSession()).toBe(false);
    expect(signOutState.unfinished).toBe(true);
    unreachable();
    expect(await endSession()).toBe(false);
    expect(signOutState.unfinished).toBe(true);
    expect(await exists()).toBe(true);
  });

  it('a sign-out already pending is the one ended, with one DELETE', async () => {
    markSignOutPending();
    const requests = fakeApi({ 'DELETE /session': [204, null] });
    expect(await endSession()).toBe(true);
    expect(said(requests)).toEqual(['DELETE /session']);
    expect(signOutPending()).toBe(false);
  });
});

describe('signing out here', () => {
  it('online: wipes this browser first, then ends the server session', async () => {
    await setMeta({ login_id: 1, login_name: 'Tess', username: 'tess' });
    const asked: { request: string; databaseThere: boolean }[] = [];
    vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
      asked.push({ request: `${init.method} ${String(input)}`, databaseThere: await exists() });
      return new Response(null, { status: 204 });
    });
    await signOutHere();
    expect(asked).toEqual([{ request: 'DELETE /api/v1/session', databaseThere: false }]);
    expect(await exists()).toBe(false);
    expect(signOutPending()).toBe(false);
    expect(session.me).toBeNull();
  });

  it('offline: wipes at once, sends nothing, and leaves the flag for later', async () => {
    await setMeta({ login_id: 1, login_name: 'Tess', username: 'tess' });
    await addToQueue(makeAction({ kind: 'tick', item_id: 'i-onions' }), ME.id, 'device-1');
    network.offline = true;
    const tried = unreachable();
    await signOutHere();
    expect(tried).toEqual([]);
    expect(await exists()).toBe(false);
    expect(signOutPending()).toBe(true);
    expect(session.me).toBeNull();
  });
});

describe('sending first (for up to 5 s)', () => {
  it('nothing waiting: done at once', async () => {
    const tried = unreachable();
    expect(await trySending()).toBe(0);
    expect(tried).toEqual([]);
  });

  it('everything sent: none left', async () => {
    await addToQueue(makeAction({ kind: 'tick', item_id: 'i-onions' }), ME.id, 'device-1');
    await shoppingSync.open();
    fakeApi({
      'POST /shopping/actions': (request) => {
        const body = request.body as { actions: { id: string }[] };
        return [
          200,
          { results: body.actions.map((a, i) => ({ id: a.id, seq: 1 + i, status: 'applied' })) }
        ];
      }
    });
    expect(await trySending()).toBe(0);
  });

  it('server out of reach: gives up after the time and says how many are left', async () => {
    await addToQueue(makeAction({ kind: 'tick', item_id: 'a' }), ME.id, 'device-1');
    await addToQueue(makeAction({ kind: 'tick', item_id: 'b' }), ME.id, 'device-1');
    await shoppingSync.open();
    vi.stubGlobal('fetch', () => new Promise<Response>(() => undefined));
    const started = Date.now();
    expect(await trySending(100)).toBe(2);
    expect(Date.now() - started).toBeLessThan(2000);
  });

  it('a refusal of the whole batch leaves them waiting too', async () => {
    await addToQueue(makeAction({ kind: 'tick', item_id: 'a' }), ME.id, 'device-1');
    await shoppingSync.open();
    fakeApi({ 'POST /shopping/actions': [401, { detail: 'Not signed in.' }] });
    expect(await trySending()).toBe(1);
  });

  it('counts changes the list hadn’t read, straight from the phone database', async () => {
    // Queued (say, in another tab) without this tab's list knowing.
    await addToQueue(makeAction({ kind: 'tick', item_id: 'a' }), ME.id, 'device-1');
    await addToQueue(makeAction({ kind: 'tick', item_id: 'b' }), 99, 'device-1');
    const tried = unreachable();
    expect(shoppingSync.waiting).toBe(0);
    expect(await trySending()).toBe(1);
    expect(tried).toEqual([]);
  });

  it('a phone database that can’t be read: “couldn’t read”, never 0', async () => {
    await addToQueue(makeAction({ kind: 'tick', item_id: 'a' }), ME.id, 'device-1');
    const mend = breakPhone();
    unreachable();
    expect(await trySending()).toBe(UNREADABLE);
    mend();
    expect(await trySending()).toBe(1);
  });
});
