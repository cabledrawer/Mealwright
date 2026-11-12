// Settings → Sign-in → Single sign-on (0.9 O1): set up on a computer, the secret never shown,
// the callback address from this browser, groups to roles, the test's result, and password
// sign-in turned off only once an admin signs in with single sign-on.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { SsoSetup } from '#lib/client/sso.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Setup from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));

const TESS = { id: 1, name: 'Tess', username: 'tess', role: 'admin', theme: 'auto' };

const SAVED: SsoSetup = {
  issuer: 'https://id.example.org',
  client_id: 'mealwright',
  secret_set: true,
  button_name: 'Authentik',
  redirect_uri: `${location.origin}/auth/callback`,
  group_claim: 'groups',
  group_roles: [{ group: 'mealwright-admins', role: 'admin' }],
  anyone_else: 'none',
  make_accounts: true,
  password_sign_in: true,
  admin_linked: false,
  switch_on: true,
  test: null
};

describe('single sign-on setup', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let requests: FakeRequest[];

  function show() {
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(Setup, { target }));
    flushSync();
  }

  beforeEach(async () => {
    session.me = TESS as never;
    await page.viewport(1300, 900);
  });

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    session.me = null;
  });

  it('on a phone, says to set it up on a computer and asks nothing', async () => {
    await page.viewport(390, 800);
    requests = fakeApi({});
    show();
    await expect.element(page.getByText('Set up on a computer')).toBeVisible();
    expect(requests).toEqual([]);
  });

  it('shows the saved setup, never the secret, and this browser’s callback address', async () => {
    fakeApi({ 'GET /sso/settings': [200, SAVED] });
    show();
    await expect
      .element(page.getByLabelText('Issuer address'))
      .toHaveValue('https://id.example.org');
    await expect.element(page.getByLabelText('Client secret')).toHaveValue('');
    await expect
      .element(page.getByText(`${location.origin}/auth/callback`, { exact: true }))
      .toBeVisible();
    await expect.element(page.getByText('id.example.org', { exact: true })).toBeVisible();
    expect(document.querySelector('.warn')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      'On your home network? Add id.example.org to Privacy › Your own network, and turn on the Single sign-on switch there.'
    );
  });

  it('saves groups and roles; a blank secret keeps the saved one', async () => {
    requests = fakeApi({
      'GET /sso/settings': [200, SAVED],
      'PUT /sso/settings': (request) => [200, { ...SAVED, ...(request.body as object) }]
    });
    show();
    await expect
      .element(page.getByLabelText('Issuer address'))
      .toHaveValue('https://id.example.org');
    await page.getByRole('button', { name: '+ Add a group' }).click();
    await userEvent.fill(page.getByRole('textbox', { name: 'Group' }).nth(1), 'mealwright');
    await page.getByRole('radio', { name: 'Member' }).nth(2).click();
    await page.getByRole('button', { name: 'Save' }).click();
    await expect.element(page.getByText('Saved.')).toBeVisible();
    const put = requests.find((r) => r.method === 'PUT')!;
    expect(put.body).toMatchObject({
      client_secret: '',
      redirect_uri: `${location.origin}/auth/callback`,
      group_roles: [
        { group: 'mealwright-admins', role: 'admin' },
        { group: 'mealwright', role: 'member' }
      ],
      anyone_else: 'member',
      password_sign_in: true
    });
  });

  it('keeps password sign-in on until an admin has signed in with single sign-on', async () => {
    fakeApi({ 'GET /sso/settings': [200, SAVED] });
    show();
    await expect
      .element(page.getByRole('switch', { name: 'Allow password sign-in' }))
      .toBeDisabled();
  });

  it('shows a passed test and lets password sign-in go off', async () => {
    fakeApi({
      'GET /sso/settings': [
        200,
        {
          ...SAVED,
          admin_linked: true,
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
    show();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'Test passed' }))
      .toHaveTextContent('Test passed: signed in as tess, groups mealwright-admins → Admin.');
    await expect
      .element(page.getByRole('switch', { name: 'Allow password sign-in' }))
      .toBeEnabled();
    await expect
      .element(page.getByRole('link', { name: 'Test sign-in' }))
      .toHaveAttribute('target', '_blank');
  });

  it('shows the server’s refusal', async () => {
    fakeApi({
      'GET /sso/settings': [200, SAVED],
      'PUT /sso/settings': [
        422,
        { detail: 'Enter the issuer address, starting with https://.', code: 'bad_issuer' }
      ]
    });
    show();
    await expect
      .element(page.getByLabelText('Issuer address'))
      .toHaveValue('https://id.example.org');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Enter the issuer address, starting with https://.');
  });
});
