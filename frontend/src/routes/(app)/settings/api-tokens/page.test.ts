// Settings → Sign-in → API tokens (0.9 O2): the list, making a token (shown once, with Copy
// and Done), and deleting one, which asks first.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { ApiToken, ApiTokens } from '#lib/apiTokens.js';
import { network } from '#lib/network.svelte.js';
import { contrastOf } from '#lib/testing/contrast.js';
import { toasts } from '#lib/toast.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Tokens from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const TODAY = '2026-11-12';
const SECRET = 'mw_ro_' + 'a'.repeat(43);

const ha: ApiToken = {
  id: 1,
  name: 'Home Assistant',
  scope: 'read',
  created_at: '2026-11-01T09:00:00Z',
  last_used_at: null,
  expires_on: null
};
const backup: ApiToken = { ...ha, id: 2, name: 'Backup script', scope: 'full' };

const listOf = (tokens: ApiToken[]): [number, ApiTokens] => [200, { tokens, today: TODAY }];

describe('Settings → Sign-in → API tokens', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];
  let tokens: ApiToken[] = [];

  function open(routes: Parameters<typeof fakeApi>[0] = {}) {
    requests = fakeApi({
      'GET /api-tokens': () => listOf(tokens),
      ...routes
    });
    component = mount(Tokens, { target: document.body });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
    toasts.dismiss();
    tokens = [backup, ha];
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    toasts.dismiss();
  });

  const sent = (method: string, path: string) =>
    requests.filter((r) => r.method === method && r.path === path);

  it('lists the tokens as drawn', async () => {
    open();
    await expect.element(page.getByRole('heading', { name: 'API tokens', level: 1 })).toBeVisible();
    await expect.element(page.getByText('Home Assistant')).toBeVisible();
    await expect.element(page.getByText('Read-only · never expires · never used')).toBeVisible();
    await expect.element(page.getByText('Full access · never expires · never used')).toBeVisible();
    await expect
      .element(page.getByText('Admins only. Tokens never see passwords or sign-in settings.'))
      .toBeVisible();
    await expect
      .element(page.getByRole('button', { name: '1 year' }))
      .toHaveAttribute('aria-pressed', 'true');
    await expect
      .element(page.getByRole('button', { name: 'Read only' }))
      .toHaveAttribute('aria-pressed', 'true');
  });

  it('the back link ‹ Sign-in lands on Settings’ Sign-in section (L5)', async () => {
    open();
    await expect
      .element(page.getByRole('link', { name: 'Sign-in' }).first())
      .toHaveAttribute('href', '/settings?section=sign-in');
  });

  it.each(['light', 'dark'])(
    'Delete and an error line reach 4.5:1 on their background in the %s theme (L6)',
    async (theme) => {
      document.documentElement.setAttribute('data-theme', theme);
      try {
        open();
        await expect.element(page.getByText('Home Assistant')).toBeVisible();
        const del = (await page
          .getByRole('button', { name: 'Delete Home Assistant token' })
          .element()) as HTMLElement;
        expect(contrastOf(del)).toBeGreaterThanOrEqual(4.5);
        await userEvent.click(page.getByRole('button', { name: 'Make token' }));
        const error = (await page.getByText('Give the token a name.').element()) as HTMLElement;
        expect(contrastOf(error)).toBeGreaterThanOrEqual(4.5);
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    }
  );

  it('makes a token, shows it once with Copy, and Done hides it for good', async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    open({
      'POST /api-tokens': (request) => {
        tokens = [{ ...ha, id: 3, name: 'Shopping widget', expires_on: '2026-12-12' }, ...tokens];
        return [201, { token: SECRET, made: tokens[0], body: request.body }];
      }
    });
    await userEvent.click(page.getByRole('button', { name: 'Make token' }));
    await expect.element(page.getByText('Give the token a name.')).toBeVisible();
    expect(sent('POST', '/api-tokens')).toHaveLength(0);

    await userEvent.fill(page.getByLabelText('Name'), '  Shopping widget ');
    await userEvent.click(page.getByRole('button', { name: '30 days' }));
    await userEvent.click(page.getByRole('button', { name: 'Make token' }));
    await expect.element(page.getByText(SECRET)).toBeVisible();
    expect(sent('POST', '/api-tokens')[0]!.body).toEqual({
      name: 'Shopping widget',
      scope: 'read',
      expires_on: '2026-12-12'
    });
    await expect
      .element(page.getByText('You won’t see this token again.', { exact: false }))
      .toBeVisible();
    await expect.element(page.getByText('Shopping widget')).toBeVisible();

    await userEvent.click(page.getByRole('button', { name: 'Copy' }));
    expect(writeText).toHaveBeenCalledWith(SECRET);
    await expect.element(page.getByRole('button', { name: 'Copied' })).toBeVisible();
    await userEvent.click(page.getByRole('button', { name: 'Done' }));
    expect(document.body.textContent).not.toContain(SECRET);
    await expect.element(page.getByRole('button', { name: 'Make token' })).toBeVisible();
  });

  it('sends Read and change, Never, or the picked date', async () => {
    open({ 'POST /api-tokens': () => [201, { token: SECRET, made: ha }] });
    await userEvent.fill(page.getByLabelText('Name'), 'Backup');
    await userEvent.click(page.getByRole('button', { name: 'Read and change' }));
    await userEvent.click(page.getByRole('button', { name: 'Never' }));
    await userEvent.click(page.getByRole('button', { name: 'Make token' }));
    await expect.element(page.getByText(SECRET)).toBeVisible();
    expect(sent('POST', '/api-tokens')[0]!.body).toEqual({
      name: 'Backup',
      scope: 'full',
      expires_on: null
    });
    await userEvent.click(page.getByRole('button', { name: 'Done' }));
    await userEvent.fill(page.getByLabelText('Name'), 'Later');
    await userEvent.click(page.getByRole('button', { name: 'Pick a date' }));
    await userEvent.fill(page.getByLabelText('Last day it works'), '2027-01-31');
    await userEvent.click(page.getByRole('button', { name: 'Make token' }));
    await vi.waitFor(() => expect(sent('POST', '/api-tokens')).toHaveLength(2));
    expect(sent('POST', '/api-tokens')[1]!.body).toEqual({
      name: 'Later',
      scope: 'full',
      expires_on: '2027-01-31'
    });
  });

  it('shows the server’s words when it refuses', async () => {
    open({
      'POST /api-tokens': [
        409,
        { detail: 'The household has 50 tokens. Delete one first.', code: 'too_many_tokens' }
      ]
    });
    await userEvent.fill(page.getByLabelText('Name'), 'One more');
    await userEvent.click(page.getByRole('button', { name: 'Make token' }));
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('The household has 50 tokens. Delete one first.');
  });

  it('asks before deleting; Keep it sends nothing, Delete does', async () => {
    open({
      'DELETE /api-tokens/1': () => {
        tokens = [backup];
        return [204, null];
      }
    });
    await userEvent.click(page.getByRole('button', { name: 'Delete Home Assistant token' }));
    const ask = page.getByRole('alertdialog', { name: 'Delete the Home Assistant token?' });
    await expect.element(ask).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Keep it' })).toHaveFocus();
    await userEvent.click(page.getByRole('button', { name: 'Keep it' }));
    expect(sent('DELETE', '/api-tokens/1')).toHaveLength(0);

    await userEvent.click(page.getByRole('button', { name: 'Delete Home Assistant token' }));
    await userEvent.click(ask.getByRole('button', { name: 'Delete' }));
    await vi.waitFor(() => expect(sent('DELETE', '/api-tokens/1')).toHaveLength(1));
    await expect.element(page.getByText('Home Assistant')).not.toBeInTheDocument();
    await expect.element(page.getByRole('status')).toHaveTextContent('Deleted Home Assistant.');
  });

  it('says why when the list can’t be had (a member, say)', async () => {
    open({
      'GET /api-tokens': [403, { detail: 'Only an admin can do this.', code: 'admins_only' }]
    });
    await expect.element(page.getByRole('alert')).toHaveTextContent('Only an admin can do this.');
    await expect.element(page.getByRole('button', { name: 'Make token' })).not.toBeInTheDocument();
  });

  it('pads the card’s words from its edge, for a member as for a loading list (L10)', async () => {
    open({
      'GET /api-tokens': [403, { detail: 'Only an admin can do this.', code: 'admins_only' }]
    });
    await expect.element(page.getByRole('alert')).toBeVisible();
    const words = page.getByRole('alert').element() as HTMLElement;
    const style = getComputedStyle(words);
    expect(parseFloat(style.paddingLeft)).toBeGreaterThanOrEqual(12);
    expect(parseFloat(style.paddingRight)).toBeGreaterThanOrEqual(12);
  });
});
