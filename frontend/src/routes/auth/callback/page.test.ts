// Back from the sign-in server (0.9 O1): posts what came back once, signs in, shows a test's
// result, or says why not. The code leaves the address bar at once. D3: back to Delete
// everything once confirmed there. S7: "Sign out" on "Almost there" tells the server.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { markConfirming } from '#lib/client/sso.js';
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
const leave = vi.hoisted(() => ({ goToSignInServer: vi.fn<(url: string) => void>() }));
vi.mock('#lib/client/sso.js', async (original) => ({
  ...(await original<typeof import('#lib/client/sso.js')>()),
  goToSignInServer: leave.goToSignInServer
}));

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
    leave.goToSignInServer.mockClear();
    session.me = null;
    sessionStorage.clear();
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

  it('goes to the sign-in server once more when the server says "again"', async () => {
    requests = fakeApi({
      'POST /sso/finish': [
        200,
        { done: 'again', me: null, test: null, url: 'https://id.example.org/authorize?state=s2' }
      ]
    });
    show('?state=s1&code=c1');
    await vi.waitFor(() =>
      expect(leave.goToSignInServer).toHaveBeenCalledWith(
        'https://id.example.org/authorize?state=s2'
      )
    );
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /sso/finish']);
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(session.me).toBeNull();
  });

  it('without a state, sends nothing and says to try again', async () => {
    requests = fakeApi({});
    show('?code=c1');
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('That sign-in took too long or was already used. Try again.');
    expect(requests).toEqual([]);
  });

  it('waits for an admin with no session: "Almost there" (Pe3/M2)', async () => {
    requests = fakeApi({
      'POST /sso/finish': [200, { done: 'waiting', me: null, test: null, username: 'lorna.s' }]
    });
    show('?state=s1&code=c1');
    await expect.element(page.getByRole('heading', { name: 'Almost there' })).toBeVisible();
    await expect
      .element(page.getByText(/You signed in with single sign-on as lorna\.s, but this kitchen/))
      .toBeVisible();
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent(
        'Nothing in Mealwright is open to you until then. Once they’ve linked you, sign in again.'
      );
    await expect
      .element(page.getByRole('link', { name: 'Sign in again' }))
      .toHaveAttribute('href', '/api/v1/sso/start?remember=false');
    expect(session.me).toBeNull();
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /sso/finish']);
  });

  it('"Sign out" on "Almost there" tells the server, then goes to sign in (S7)', async () => {
    requests = fakeApi({
      'POST /sso/finish': [200, { done: 'waiting', me: null, test: null, username: 'lorna.s' }],
      'DELETE /session': [204, null]
    });
    show('?state=s1&code=c1');
    await page.getByRole('button', { name: 'Sign out' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'POST /sso/finish',
      'DELETE /session'
    ]);
    expect(navigation.goto.mock.calls[0]).toEqual(['/sign-in', { replace: true }]);
  });

  it('goes back to Delete everything once an admin has confirmed it there (D3)', async () => {
    markConfirming(true);
    requests = fakeApi({ 'POST /sso/finish': [200, { done: 'confirmed', me: null, test: null }] });
    show('?state=s1&code=c1');
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(navigation.goto.mock.calls[0]).toEqual([
      '/settings/your-data/delete',
      { replace: true }
    ]);
    expect(sessionStorage.length).toBe(0);
    expect(session.me).toBeNull();
  });

  it('goes back to Your data once an admin has confirmed a lower Keep there (R6)', async () => {
    markConfirming(true, Date.now(), 'backups');
    requests = fakeApi({ 'POST /sso/finish': [200, { done: 'confirmed', me: null, test: null }] });
    show('?state=s1&code=c1');
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(navigation.goto.mock.calls[0]).toEqual(['/settings/your-data', { replace: true }]);
    expect(sessionStorage.length).toBe(0);
  });

  it('when that confirming is refused, the way back goes to Your data (R6)', async () => {
    markConfirming(true, Date.now(), 'backups');
    fakeApi({ 'POST /sso/finish': [400, { detail: 'Not you.', code: 'not_you' }] });
    show('?state=s1&code=c1');
    await expect
      .element(page.getByRole('link', { name: 'Back to Backups & your data' }))
      .toHaveAttribute('href', '/settings/your-data');
  });

  it('when confirming Delete everything is refused, the way back goes there (D3)', async () => {
    markConfirming(true);
    const detail =
      'That was another account at your sign-in server, not the one linked to you here. Delete everything wasn’t confirmed.';
    fakeApi({ 'POST /sso/finish': [400, { detail, code: 'not_you' }] });
    show('?state=s1&code=c1');
    await expect.element(page.getByRole('alert')).toHaveTextContent(detail);
    await expect
      .element(page.getByRole('link', { name: 'Back to Delete everything' }))
      .toHaveAttribute('href', '/settings/your-data/delete');
  });

  it('a confirming given up on long ago doesn’t change a later way back', async () => {
    markConfirming(true, Date.now() - 11 * 60_000);
    fakeApi({ 'POST /sso/finish': [400, { detail: 'Try again.', code: 'expired' }] });
    show('?state=s1&code=c1');
    await expect.element(page.getByRole('link', { name: 'Back to sign in' })).toBeVisible();
  });
});
