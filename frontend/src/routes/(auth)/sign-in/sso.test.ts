// The sign-in page with single sign-on (0.9 O1): the "Sign in with …" button, the password
// form hidden while password sign-in is off, and the sentence for ?sso=<code>.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { signOutState } from '#lib/offline/unfinished.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { load } from './+page.js';
import SignIn from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const where = vi.hoisted(() => ({ url: new URL('http://mealwright.test/sign-in') }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/state', () => ({ page: where }));

const SETUP = { needs_setup: false, plain_http_allowed: false };

describe('signing in with single sign-on', () => {
  const mounted: ReturnType<typeof mount>[] = [];

  function show(options?: { password: boolean; sso_button: string | null }) {
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(SignIn, { target, props: { data: { setup: SETUP, options } } as never }));
    flushSync();
  }

  beforeEach(async () => {
    freshPhone();
    signOutState.unfinished = false;
    where.url = new URL('http://mealwright.test/sign-in');
    await page.viewport(390, 800);
  });

  afterEach(async () => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    await dropPhone();
  });

  it('shows the form, "or" and the button, which starts at the server and keeps Remember', async () => {
    show({ password: true, sso_button: 'Authentik' });
    await expect.element(page.getByLabelText('Username')).toBeVisible();
    await expect.element(page.getByText('or', { exact: true })).toBeVisible();
    const button = page.getByRole('link', { name: 'Sign in with Authentik' });
    await expect.element(button).toHaveAttribute('href', '/api/v1/sso/start?remember=true');
    await page.getByRole('switch', { name: 'Remember this phone' }).click();
    await expect.element(button).toHaveAttribute('href', '/api/v1/sso/start?remember=false');
  });

  it('with password sign-in off, shows only Remember and the button', async () => {
    show({ password: false, sso_button: 'Authentik' });
    await expect.element(page.getByRole('link', { name: 'Sign in with Authentik' })).toBeVisible();
    await expect.element(page.getByRole('switch', { name: 'Remember this phone' })).toBeVisible();
    expect(document.querySelector('#username')).toBeNull();
    expect(document.querySelector('#password')).toBeNull();
    expect(document.body.textContent).not.toContain('Forgot your password?');
    expect(document.querySelector('.or')).toBeNull();
  });

  it('without single sign-on, shows no button (and no answer means the form only)', async () => {
    show(undefined);
    await expect.element(page.getByLabelText('Username')).toBeVisible();
    expect(document.querySelector('a.sso')).toBeNull();
  });

  it('says why single sign-on sent the browser back, never the code itself', async () => {
    where.url = new URL('http://mealwright.test/sign-in?sso=not_let_in');
    show({ password: true, sso_button: 'Authentik' });
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(
        'Your sign-in server doesn’t put you in a group Mealwright lets in. Ask your household’s admin.'
      );
    unmount(mounted.pop()!);
    document.body.innerHTML = '';
    where.url = new URL('http://mealwright.test/sign-in?sso=%3Cscript%3E');
    show({ password: true, sso_button: 'Authentik' });
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Your sign-in server gave an answer Mealwright couldn’t use.');
  });

  it('loads what the page offers, and falls back to the form when the server can’t say', async () => {
    fakeApi({ 'GET /sign-in-options': [200, { password: false, sso_button: 'Keycloak' }] });
    const offered = (await load({ fetch } as never)) as { options: unknown };
    expect(offered.options).toEqual({ password: false, sso_button: 'Keycloak' });
    fakeApi({ 'GET /sign-in-options': [500, { detail: 'no' }] });
    const fallback = (await load({ fetch } as never)) as { options: unknown };
    expect(fallback.options).toEqual({ password: true, sso_button: null });
  });
});
