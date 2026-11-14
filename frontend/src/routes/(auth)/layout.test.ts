// The sign-in page opens while the server can't be reached: right after signing out
// offline (docs/dev/sync-protocol.md section 12).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { load } from './+layout';

type LoadEvent = Parameters<typeof load>[0];

const open = (path: string) =>
  load({
    fetch: (...args: Parameters<typeof fetch>) => fetch(...args),
    url: new URL(`http://mealwright.test${path}`)
  } as unknown as LoadEvent);

describe('the sign-in page while the server can’t be reached', () => {
  beforeEach(() => {
    session.setup = null;
    network.reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    network.reset();
  });

  it('still shows, with what the server said last', async () => {
    session.setup = { needs_setup: false, plain_http_allowed: true };
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await expect(open('/sign-in')).resolves.toEqual({
      setup: { needs_setup: false, plain_http_allowed: true },
      signedIn: false
    });
  });

  it('counts plain http:// as not allowed when the server never said', async () => {
    fakeApi({ 'GET /setup': [503, null] });
    await expect(open('/sign-in')).resolves.toEqual({
      setup: { needs_setup: false, plain_http_allowed: false },
      signedIn: false
    });
  });

  it('a server error that isn’t about reaching it is not hidden', async () => {
    fakeApi({ 'GET /setup': [500, { detail: 'Something broke.' }] });
    await expect(open('/sign-in')).rejects.toMatchObject({ status: 500 });
  });
});

describe('someone already signed in', () => {
  const SETUP = { needs_setup: false, plain_http_allowed: false };
  const ME = { username: 'sam', role: 'member', member_id: 1 };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('goes straight on from the sign-in page', async () => {
    fakeApi({ 'GET /setup': [200, SETUP], 'GET /me': [200, ME] });
    await expect(open('/sign-in')).rejects.toMatchObject({ status: 307, location: '/' });
  });

  it('stays on a sign-in or Reset password link, which then refuses (Pe2)', async () => {
    fakeApi({ 'GET /setup': [200, SETUP], 'GET /me': [200, ME] });
    await expect(open('/join')).resolves.toEqual({ setup: SETUP, signedIn: true });
    await expect(open('/reset')).resolves.toEqual({ setup: SETUP, signedIn: true });
  });

  it('a link page signed out is just the link page', async () => {
    fakeApi({ 'GET /setup': [200, SETUP], 'GET /me': [401, { code: 'not_signed_in' }] });
    await expect(open('/join')).resolves.toEqual({ setup: SETUP, signedIn: false });
  });
});
