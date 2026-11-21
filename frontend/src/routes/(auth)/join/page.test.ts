// A one-time sign-in link (0.9 A1): the person chooses their password and is signed in straight
// away (F254, cabledrawer 20 Nov); a used or run-out link says so. Link hardening (cabledrawer 13 Nov): the secret is after a
// `#`, taken out of the address bar first, and posted in the body. A link that works says whose
// it is (name and username, F269, cabledrawer 21 Nov); one that doesn't names nobody.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { goto } from '$app/navigation';
import type { Me } from '#lib/api.js';
import { takeTurnedAway, type Held } from '#lib/offline/held.js';
import { wipeIfAnotherLogin } from '#lib/offline/wipe.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Join from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));
vi.mock('#lib/offline/wipe.js', async (real) => ({
  ...(await real<typeof import('#lib/offline/wipe.js')>()),
  wipeIfAnotherLogin: vi.fn()
}));

const LINK = {
  kind: 'join',
  expires_at: '2026-11-12T10:00:00Z',
  min_password: 12,
  name: 'Sam Test',
  username: 'sam.test'
};
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
    vi.mocked(goto).mockReset();
    vi.mocked(wipeIfAnotherLogin).mockReset();
    session.me = null;
    takeTurnedAway();
  });

  it('takes the secret out of the address bar and sends it only in the body', async () => {
    open({ 'POST /join': [200, { username: 'sam', me: null }] });
    expect(location.href).not.toContain(SECRET);
    await expect.element(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0]!.path).toBe('/join/look');
    expect(requests[0]!.body).toEqual({ token: SECRET });
    for (const request of requests) expect(request.url).not.toContain(SECRET);
  });

  it('says whose link it is (F269), then saves a password of 12 characters or more', async () => {
    open({ 'POST /join': [200, { username: 'sam', me: null }] });
    await expect.element(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
    await expect
      .element(page.getByTestId('link-whose'))
      .toHaveTextContent(
        'Hi Sam Test. Your username is sam.test — you’ll need it to sign in next time.'
      );
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

  const SAM: Me = { id: 7, username: 'sam', name: 'Sam', role: 'member', theme: 'auto' };

  it('F254: saving the password signs them in and goes to Today', async () => {
    vi.mocked(wipeIfAnotherLogin).mockResolvedValue('kept');
    open({ 'POST /join': [200, { username: 'sam', me: SAM }] });
    await page.getByLabelText('Password').fill('a long kitchen password');
    await page.getByRole('button', { name: 'Save my password' }).click();
    await vi.waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/', { replace: true, refreshAll: true })
    );
    expect(wipeIfAnotherLogin).toHaveBeenCalledWith(SAM, null);
    expect(session.me).toEqual(SAM);
    // Nothing else asked of the server: the link's answer is the sign-in.
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /join/look', 'POST /join']);
  });

  it("F254: with another login's changes waiting here, signs out again and sends them to sign in", async () => {
    const alexs: Held = {
      who: { id: 3, username: 'alex', name: 'Alex', role: 'member' },
      count: 2,
      ids: ['a', 'b']
    };
    vi.mocked(wipeIfAnotherLogin).mockResolvedValue(alexs);
    open({ 'POST /join': [200, { username: 'sam', me: SAM }], 'DELETE /session': [204, null] });
    await page.getByLabelText('Password').fill('a long kitchen password');
    await page.getByRole('button', { name: 'Save my password' }).click();
    await expect.element(page.getByRole('heading', { name: 'You’re all set' })).toBeVisible();
    expect(requests.some((r) => r.method === 'DELETE' && r.path === '/session')).toBe(true);
    expect(goto).not.toHaveBeenCalled();
    expect(session.me).toBeNull();
    // The sign-in page is filled in for them, so its warning names them.
    expect(takeTurnedAway()).toBe('sam');
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

  it('a link without its secret asks the server nothing, and says what is true', async () => {
    // Reloaded, or a tab restored, after the secret left the address bar (16b review R-L2).
    open({}, '');
    await expect.element(page.getByRole('heading', { name: 'Sign-in link' })).toBeVisible();
    await expect
      .element(page.getByText('Open the link again from the message it came in.'))
      .toBeVisible();
    expect(document.body.textContent).not.toContain('used or has run out');
    expect(page.getByRole('button', { name: 'Try again' }).query()).toBeNull();
    expect(requests).toHaveLength(0);
  });

  it('the "works once" note is plain muted text, not a button-like box (F268)', async () => {
    open();
    const note = page.getByText(/This link works once\./);
    await expect.element(note).toBeVisible();
    const noteStyle = getComputedStyle(note.element());
    const buttonStyle = getComputedStyle(
      page.getByRole('button', { name: 'Save my password' }).element()
    );
    expect(noteStyle.backgroundColor).toBe('rgba(0, 0, 0, 0)');
    expect(noteStyle.backgroundColor).not.toBe(buttonStyle.backgroundColor);
    expect(noteStyle.fontWeight).not.toBe(buttonStyle.fontWeight);
  });

  it('a Reset password link asks for a new password and says whose it is (F269)', async () => {
    open({ 'POST /join/look': [200, { ...LINK, kind: 'reset' }] });
    await expect
      .element(page.getByRole('heading', { name: 'Choose a new password' }))
      .toBeVisible();
    await expect
      .element(page.getByText('Your recipes, plans and history stay as they are.'))
      .toBeVisible();
    expect(document.body.textContent).not.toContain('Welcome');
    await expect
      .element(page.getByTestId('link-whose'))
      .toHaveTextContent(
        'Hi Sam Test. Your username is sam.test — you’ll need it to sign in next time.'
      );
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
