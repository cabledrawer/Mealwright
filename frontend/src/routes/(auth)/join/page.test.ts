// A one-time sign-in link (0.9 A1): the person chooses their password, then signs in as anyone
// else; a used or run-out link says so. Link hardening (cabledrawer 13 Nov): the secret is after a
// `#`, taken out of the address bar first, and posted in the body; nobody is named before the
// password is set, the username only after.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Join from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));

const LINK = { kind: 'join', expires_at: '2026-11-12T10:00:00Z', min_password: 12 };
const SECRET = 'Xp4secret-token_9';

describe('Join with a sign-in link', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];
  const before = location.pathname + location.search;

  function open(routes: Parameters<typeof fakeApi>[0] = {}, hash = `#${SECRET}`, signedIn = false) {
    history.replaceState(history.state, '', `${before}${hash}`);
    requests = fakeApi({ 'POST /join/look': [200, LINK], ...routes });
    component = mount(Join, {
      target: document.body,
      props: {
        data: { setup: { needs_setup: false, plain_http_allowed: false }, signedIn }
      } as never
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
    history.replaceState(history.state, '', before);
    vi.unstubAllGlobals();
  });

  it('takes the secret out of the address bar and sends it only in the body', async () => {
    open({ 'POST /join': [200, { username: 'sam' }] });
    expect(location.href).not.toContain(SECRET);
    await expect.element(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]!.path).toBe('/join/look');
    expect(requests[0]!.body).toEqual({ token: SECRET });
    for (const request of requests) expect(request.url).not.toContain(SECRET);
  });

  it('names nobody before the password is set, and saves one of 12 characters or more', async () => {
    open({ 'POST /join': [200, { username: 'sam' }] });
    await expect.element(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
    expect(document.body.textContent).not.toContain('Username');
    expect(document.body.textContent).not.toContain('sam');
    await page.getByLabelText('Password').fill('short');
    await page.getByRole('button', { name: 'Save my password' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent('Use at least 12 characters.');
    expect(requests.filter((r) => r.path === '/join')).toHaveLength(0);
    await page.getByLabelText('Password').fill('a long kitchen password');
    await userEvent.keyboard('{Enter}');
    await expect.element(page.getByRole('heading', { name: 'You’re all set' })).toBeVisible();
    await expect.element(page.getByText('Your password is saved. Sign in as sam.')).toBeVisible();
    const sent = requests.filter((r) => r.path === '/join');
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body).toEqual({ token: SECRET, password: 'a long kitchen password' });
    await expect
      .element(page.getByRole('link', { name: 'Sign in' }))
      .toHaveAttribute('href', '/sign-in');
  });

  it('says so when the link has been used or has run out', async () => {
    open({
      'POST /join/look': [
        404,
        { code: 'link_gone', detail: 'This sign-in link has been used or has run out.' }
      ]
    });
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('This sign-in link has been used or has run out.');
    expect(page.getByLabelText('Password').query()).toBeNull();
  });

  it('a link without its secret asks the server nothing', async () => {
    open({}, '');
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(
        'This sign-in link has been used or has run out. Ask your household’s admin for a new one.'
      );
    expect(requests).toHaveLength(0);
  });

  it('a Reset password link asks for a new password, naming nobody', async () => {
    open({ 'POST /join/look': [200, { ...LINK, kind: 'reset' }] });
    await expect
      .element(page.getByRole('heading', { name: 'Choose a new password' }))
      .toBeVisible();
    await expect
      .element(page.getByText('Your recipes, plans and history stay as they are.'))
      .toBeVisible();
    expect(document.body.textContent).not.toContain('Welcome');
  });

  describe('opened where someone is already signed in (Pe2)', () => {
    const REFUSED = [
      'Someone is already signed in on this device. Sign-in links only work where nobody is signed in.',
      'The link hasn’t been used. Open it on another device, or sign out here first and then open it again.'
    ];

    async function seesTheRefusal() {
      await expect
        .element(page.getByRole('heading', { name: 'This link can’t be used here' }))
        .toBeVisible();
      const text = document.body.textContent!.replace(/\s+/g, ' ');
      for (const line of REFUSED) expect(text).toContain(line);
      await expect
        .element(page.getByRole('link', { name: 'Go to Today' }))
        .toHaveAttribute('href', '/');
      // No names, no sign-out, no password.
      expect(page.getByRole('button', { name: /sign out/i }).query()).toBeNull();
      expect(page.getByLabelText('Password').query()).toBeNull();
    }

    it('refuses without asking the server, and still clears the secret', async () => {
      open({}, `#${SECRET}`, true);
      await seesTheRefusal();
      expect(location.href).not.toContain(SECRET);
      expect(requests).toHaveLength(0);
    });

    it('refuses when the server finds someone signed in here', async () => {
      open({
        'POST /join/look': [409, { code: 'signed_in_here', detail: REFUSED[0] }]
      });
      await seesTheRefusal();
    });

    it('refuses when the server finds someone signed in on saving', async () => {
      open({ 'POST /join': [409, { code: 'signed_in_here', detail: REFUSED[0] }] });
      await page.getByLabelText('Password').fill('a long kitchen password');
      await page.getByRole('button', { name: 'Save my password' }).click();
      await seesTheRefusal();
    });
  });
});
