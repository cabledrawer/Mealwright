// A Reset password link, "/reset#<secret>" (Pe1): the sign-in link's page, with a reset's
// heading and words, also where the link can't be used (16b review R-L2).

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Reset from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));

const SECRET = 'Rs7secret-token_2';
const GONE =
  'This sign-in link has been used or has run out. Ask your household’s admin for a new one.';

describe('A Reset password link', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];
  const before = location.pathname + location.search;

  function open(routes: Parameters<typeof fakeApi>[0] = {}, hash = `#${SECRET}`) {
    history.replaceState(history.state, '', `${before}${hash}`);
    requests = fakeApi(routes);
    component = mount(Reset, {
      target: document.body,
      props: {
        data: { setup: { needs_setup: false, plain_http_allowed: false }, signedIn: false }
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

  it('without its secret, names the reset link and says to open it again', async () => {
    open({}, '');
    await expect.element(page.getByRole('heading', { name: 'Reset password link' })).toBeVisible();
    await expect
      .element(page.getByText('Open the link again from the message it came in.'))
      .toBeVisible();
    expect(requests).toHaveLength(0);
  });

  it('used or run out, says so of a reset link', async () => {
    open({ 'POST /join/look': [404, { code: 'link_gone', detail: GONE }] });
    await expect.element(page.getByRole('heading', { name: 'Reset password link' })).toBeVisible();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(
        'This reset link has been used or has run out. Ask your household’s admin for a new one.'
      );
  });
});
