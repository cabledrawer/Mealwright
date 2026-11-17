// A login made by single sign-on has no password (L7, whole-0.9 review): Settings → Your sign-in leaves
// out "Change password", and the Change password page says so (the words are cabledrawer's, 12 Nov)
// instead of asking for a current password the person doesn't have.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import Password from './password/+page.svelte';
import SignInSection from './SignInSection.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const mine = (hasPassword: boolean) => ({
  has_password: hasPassword,
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
});

const WORDS = 'This login has no password to change: it signs in with single sign-on.';

describe('a login with no password', () => {
  let component: ReturnType<typeof mount> | null = null;

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

  function openSection(hasPassword: boolean) {
    fakeApi({ 'GET /me/sign-in': [200, mine(hasPassword)] });
    component = mount(SignInSection, {
      target: document.body,
      props: { device: 'phone', admin: false, part: 'mine' }
    });
    flushSync();
  }

  function openPage(hasPassword: boolean) {
    fakeApi({ 'GET /me/sign-in': [200, mine(hasPassword)] });
    component = mount(Password, { target: document.body });
    flushSync();
  }

  it('Sign-in has no Change password row', async () => {
    openSection(false);
    await expect.element(page.getByText('iPhone · Safari')).toBeVisible();
    expect(page.getByText('Change password').elements()).toEqual([]);
  });

  it('Sign-in still has the row for a login with a password', async () => {
    openSection(true);
    await expect.element(page.getByText('iPhone · Safari')).toBeVisible();
    await expect.element(page.getByText('Change password')).toBeVisible();
  });

  it('Change password says so in place of the form', async () => {
    openPage(false);
    await expect.element(page.getByText(WORDS)).toBeVisible();
    expect(page.getByLabelText('Current password').elements()).toEqual([]);
    expect(page.getByRole('button', { name: 'Change password' }).elements()).toEqual([]);
  });

  it('Change password shows the form for a login with a password', async () => {
    openPage(true);
    await expect.element(page.getByLabelText('Current password')).toBeVisible();
    expect(page.getByText(WORDS).elements()).toEqual([]);
  });
});
