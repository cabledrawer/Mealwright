// Back from the sign-in server (0.9 O1): posts what came back once, signs in, shows a test's
// result, or says why not. The code leaves the address bar at once.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { session } from '#lib/session.svelte.js';
import Callback from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const navigation = vi.hoisted(() => ({
  goto: vi.fn<(address?: string, options?: object) => Promise<void>>(async () => {})
}));
const where = vi.hoisted(() => ({ url: new URL('http://mealwright.test/auth/callback') }));
vi.mock('$app/navigation', () => navigation);
vi.mock('$app/state', () => ({ page: where }));

const WREN = { id: 2, name: 'Wren', username: 'wren', role: 'member', theme: 'auto' };

describe('the single sign-on callback', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let requests: FakeRequest[];

  function show(query: string) {
    where.url = new URL(`http://mealwright.test/auth/callback${query}`);
    history.replaceState(null, '', `/auth/callback${query}`);
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(Callback, { target }));
    flushSync();
  }

  beforeEach(async () => {
    freshPhone();
    navigation.goto.mockClear();
    session.me = null;
    await page.viewport(390, 800);
  });

  afterEach(async () => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    await dropPhone();
  });

  it('signs in, once, and the code leaves the address bar', async () => {
    requests = fakeApi({ 'POST /sso/finish': [200, { done: 'signed_in', me: WREN, test: null }] });
    show('?state=s1&code=c1');
    expect(location.search).toBe('');
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /sso/finish']);
    expect(requests[0]!.body).toEqual({ state: 's1', code: 'c1', error: null });
    expect(session.me?.username).toBe('wren');
    expect(navigation.goto.mock.calls[0]![1]).toMatchObject({ replace: true, refreshAll: true });
  });

  it('says why when the server refuses, with a way back to sign in', async () => {
    fakeApi({
      'POST /sso/finish': [
        400,
        { detail: 'Signing in was cancelled at your sign-in server.', code: 'cancelled' }
      ]
    });
    show('?state=s1&error=access_denied');
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Signing in was cancelled at your sign-in server.');
    await expect.element(page.getByRole('link', { name: 'Back to sign in' })).toBeVisible();
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(session.me).toBeNull();
  });

  it('shows a passed test, and the way back to the setup', async () => {
    fakeApi({
      'POST /sso/finish': [
        200,
        {
          done: 'tested',
          me: null,
          test: {
            passed: true,
            username: 'tess',
            groups: ['mealwright-admins'],
            role: 'admin',
            message: null,
            code: null
          }
        }
      ]
    });
    show('?state=s1&code=c1');
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent('Test passed: signed in as tess, groups mealwright-admins → Admin.');
    await expect.element(page.getByRole('link', { name: 'Back to single sign-on' })).toBeVisible();
    expect(navigation.goto).not.toHaveBeenCalled();
  });

  it('without a state, sends nothing and says to try again', async () => {
    requests = fakeApi({});
    show('?code=c1');
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('That sign-in took too long or was already used. Try again.');
    expect(requests).toEqual([]);
  });
});
