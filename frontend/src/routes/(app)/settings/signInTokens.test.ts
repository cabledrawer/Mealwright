// Settings → Sign-in (0.9 O2): admins see "For the household (admins)" with the API tokens row
// and how many tokens there are (the mockup Dark-SignInSettings09); members don't.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import SignInSection from './SignInSection.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const MINE = {
  has_password: true,
  password_changed_at: null,
  sessions: [
    {
      id: 1,
      device: 'iPhone · Safari',
      last_used_at: '2026-11-12T09:00:00Z',
      remember: true,
      this_device: true
    }
  ]
};

const token = (id: number) => ({
  id,
  name: `Token ${id}`,
  scope: 'read',
  created_at: '2026-11-01T09:00:00Z',
  last_used_at: null,
  expires_on: null
});

describe('Settings → Sign-in: the API tokens row', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(admin: boolean) {
    requests = fakeApi({
      'GET /me/sign-in': [200, MINE],
      'GET /api-tokens': [200, { tokens: [token(2), token(1)], today: '2026-11-12' }]
    });
    component = mount(SignInSection, { target: document.body, props: { device: 'phone', admin } });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  it('an admin sees the row, with how many tokens there are, leading to the list', async () => {
    open(true);
    await expect.element(page.getByText('For the household (admins)')).toBeVisible();
    const row = page.getByRole('link', { name: /API tokens/ });
    await expect
      .element(row)
      .toHaveAttribute('href', expect.stringMatching(/\/settings\/api-tokens$/));
    await expect.element(page.getByTestId('api-token-count')).toHaveTextContent('2');
  });

  it('a member sees neither the row nor asks for the tokens', async () => {
    open(false);
    await expect.element(page.getByText('iPhone · Safari')).toBeVisible();
    expect(page.getByText('For the household (admins)').elements()).toEqual([]);
    expect(page.getByRole('link', { name: /API tokens/ }).elements()).toEqual([]);
    expect(requests.some((r) => r.path === '/api-tokens')).toBe(false);
  });
});
