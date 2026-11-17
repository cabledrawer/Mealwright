// Settings → Your sign-in and Sign-in for everyone (F252; formerly one Sign-in section, 0.9 O2): the
// household's part is its own page for admins, and "Your sign-in" asks for nothing of it.

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

describe('Settings → Your sign-in and Sign-in for everyone', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(part: 'mine' | 'everyone', admin: boolean) {
    requests = fakeApi({
      'GET /me/sign-in': [200, MINE],
      'GET /sso/settings': [
        200,
        {
          secret_set: false,
          button_name: '',
          admin_linked: false,
          switch_on: false,
          password_sign_in: true,
          kept_warning: null
        }
      ]
    });
    component = mount(SignInSection, {
      target: document.body,
      props: { device: 'phone', admin, part }
    });
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

  it('Your sign-in shows this account only, and asks for nothing of the household', async () => {
    open('mine', true);
    await expect.element(page.getByText('iPhone · Safari')).toBeVisible();
    expect(page.getByText('Single sign-on').elements()).toEqual([]);
    expect(page.getByText('For the household (admins)').elements()).toEqual([]);
    expect(requests.some((r) => r.path.startsWith('/sso'))).toBe(false);
    expect(requests.some((r) => r.path === '/api-tokens')).toBe(false);
  });

  it('Sign-in for everyone shows single sign-on and the password switch, and not the sessions', async () => {
    open('everyone', true);
    await expect.element(page.getByText('Single sign-on')).toBeVisible();
    await expect.element(page.getByText('Password sign-in')).toBeVisible();
    expect(page.getByText('iPhone · Safari').elements()).toEqual([]);
    expect(requests.some((r) => r.path === '/me/sign-in')).toBe(false);
  });

  it('Sign-in for everyone shows a member nothing (the page itself is refused by the layout)', async () => {
    open('everyone', false);
    expect(page.getByText('Single sign-on').elements()).toEqual([]);
    expect(requests.some((r) => r.path.startsWith('/sso'))).toBe(false);
  });
});
