import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api';
import { setMeta } from '$lib/offline/phone';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { fakeApi } from '$lib/testing/fakeApi';
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

  it('can’t open offline on a device nobody has signed in on', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await expect(open()).rejects.toBeInstanceOf(ApiError);
    expect(session.me).toBeNull();
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
});
