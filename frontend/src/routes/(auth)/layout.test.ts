// The sign-in page opens while the server can't be reached: right after signing out
// offline (docs/dev/sync-protocol.md section 12).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { fakeApi } from '$lib/testing/fakeApi';
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
      setup: { needs_setup: false, plain_http_allowed: true }
    });
  });

  it('counts plain http:// as not allowed when the server never said', async () => {
    fakeApi({ 'GET /setup': [503, null] });
    await expect(open('/sign-in')).resolves.toEqual({
      setup: { needs_setup: false, plain_http_allowed: false }
    });
  });

  it('a server error that isn’t about reaching it is not hidden', async () => {
    fakeApi({ 'GET /setup': [500, { detail: 'Something broke.' }] });
    await expect(open('/sign-in')).rejects.toMatchObject({ status: 500 });
  });
});
