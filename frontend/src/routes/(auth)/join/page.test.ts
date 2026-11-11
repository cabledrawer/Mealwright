// A one-time sign-in link (0.9 A1): the person chooses their password, then signs in as anyone
// else; a used or run-out link says so.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Join from './[token]/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));
vi.mock('$app/state', () => ({
  page: { params: { token: 'secret-token' }, url: new URL('http://x/join/secret-token') }
}));

const LINK = {
  name: 'Joss',
  username: 'joss',
  expires_at: '2026-11-12T10:00:00Z',
  min_password: 12
};

describe('Join with a sign-in link', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(routes: Parameters<typeof fakeApi>[0] = {}) {
    requests = fakeApi({ 'GET /join/secret-token': [200, LINK], ...routes });
    component = mount(Join, {
      target: document.body,
      props: { data: { setup: { needs_setup: false, plain_http_allowed: false } } } as never
    });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('greets the person by name, and saves a password of 12 characters or more', async () => {
    open({ 'POST /join/secret-token': [204, null] });
    await expect.element(page.getByRole('heading', { name: 'Welcome, Joss' })).toBeVisible();
    await expect.element(page.getByText('Username: joss')).toBeVisible();
    await page.getByLabelText('Password').fill('short');
    await page.getByRole('button', { name: 'Save my password' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent('Use at least 12 characters.');
    expect(requests.filter((r) => r.method === 'POST')).toHaveLength(0);
    await page.getByLabelText('Password').fill('a long kitchen password');
    await userEvent.keyboard('{Enter}');
    await expect.element(page.getByRole('heading', { name: 'You’re all set' })).toBeVisible();
    expect(requests.filter((r) => r.method === 'POST')[0]!.body).toEqual({
      password: 'a long kitchen password'
    });
    await expect
      .element(page.getByRole('link', { name: 'Sign in' }))
      .toHaveAttribute('href', '/sign-in');
  });

  it('says so when the link has been used or has run out', async () => {
    open({
      'GET /join/secret-token': [
        404,
        { code: 'link_gone', detail: 'This sign-in link has been used or has run out.' }
      ]
    });
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('This sign-in link has been used or has run out.');
    expect(page.getByLabelText('Password').query()).toBeNull();
  });
});
