// Settings → Sign out (docs/dev/sync-protocol.md section 12): send what's waiting first, and
// warn before losing what still can't be sent.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '$lib/network.svelte';
import { phoneDatabaseName, setMeta } from '$lib/offline/phone';
import { SIGN_OUT_PENDING_KEY, signOutPending } from '$lib/offline/signOutPending';
import { readQueue } from '$lib/offline/store';
import { session } from '$lib/session.svelte';
import { makeAction } from '$lib/shopping/actions';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { fakeApi, type FakeRequest } from '$lib/testing/fakeApi';
import { ME } from '$lib/testing/fakeShopping';
import { dropPhone, freshPhone } from '$lib/testing/phone';
import Settings from './+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const navigation = vi.hoisted(() => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => navigation);

const WARNING = "3 changes haven't been sent yet. If you sign out now, they're lost.";

const exists = async () =>
  (await indexedDB.databases()).some((db) => db.name === phoneDatabaseName());

/** The server can't be reached: every request fails at once. */
function unreachable() {
  vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
}

/** The server is there, and takes every change. */
function reachable(): FakeRequest[] {
  return fakeApi({
    'POST /shopping/actions': (request) => {
      const body = request.body as { actions: { id: string }[] };
      return [
        200,
        { results: body.actions.map((a, i) => ({ id: a.id, seq: 1 + i, status: 'applied' })) }
      ];
    },
    'DELETE /session': [204, null]
  });
}

describe('signing out', () => {
  const mounted: ReturnType<typeof mount>[] = [];

  async function show(waiting: number) {
    await setMeta({ login_id: ME.id, login_name: ME.name, username: ME.username });
    unreachable();
    for (let i = 0; i < waiting; i++) {
      void shoppingSync.enqueue(makeAction({ kind: 'tick', item_id: `i${i}` })).catch(() => {});
    }
    await vi.waitFor(() => expect(shoppingSync.waiting).toBe(waiting));
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(Settings, { target }));
    flushSync();
  }

  const button = (name: string) => page.getByRole('button', { name, exact: true });

  beforeEach(() => {
    freshPhone();
    session.me = { ...ME };
    network.reset();
    navigation.goto.mockClear();
    localStorage.removeItem(SIGN_OUT_PENDING_KEY);
  });

  afterEach(async () => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    await dropPhone();
    vi.unstubAllGlobals();
    network.reset();
    localStorage.removeItem(SIGN_OUT_PENDING_KEY);
  });

  it('nothing waiting: just signs out, wiping this browser first', async () => {
    await show(0);
    const requests = reachable();
    await button('Sign out').click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(navigation.goto).toHaveBeenCalledWith('/sign-in', {
      replaceState: true,
      invalidateAll: true
    });
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['DELETE /session']);
    expect(await exists()).toBe(false);
    expect(page.getByRole('alert').elements()).toEqual([]);
  });

  it('changes that can’t be sent: the warning, with its three choices', async () => {
    await show(3);
    await button('Sign out').click();
    await expect.element(page.getByRole('alert')).toHaveTextContent(WARNING);
    await expect.element(button('Try sending now')).toBeVisible();
    await expect.element(button('Stay signed in')).toBeVisible();
    await expect.element(button('Sign out and lose them')).toBeVisible();
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(await readQueue()).toHaveLength(3);
  });

  it('Stay signed in keeps the changes', async () => {
    await show(3);
    await button('Sign out').click();
    await button('Stay signed in').click();
    expect(page.getByRole('alert').elements()).toEqual([]);
    expect(await readQueue()).toHaveLength(3);
    expect(shoppingSync.waiting).toBe(3);
    expect(navigation.goto).not.toHaveBeenCalled();
  });

  it('Try sending now, still out of reach: says so, and the warning stays', async () => {
    await show(3);
    await button('Sign out').click();
    await button('Try sending now').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(`${WARNING}Still can't reach your server.`);
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(await readQueue()).toHaveLength(3);
  });

  it('Try sending now, server back: sends them all, then signs out as asked', async () => {
    await show(3);
    await button('Sign out').click();
    await expect.element(page.getByRole('alert')).toBeVisible();
    const requests = reachable();
    await button('Try sending now').click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    const said = requests.map((r) => `${r.method} ${r.path}`);
    expect(said.at(-1)).toBe('DELETE /session');
    expect(said).toContain('POST /shopping/actions');
    expect(await exists()).toBe(false);
  });

  it('Sign out and lose them: wiped, and the server sign-out left pending', async () => {
    await show(3);
    await button('Sign out').click();
    await button('Sign out and lose them').click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(await exists()).toBe(false);
    expect(shoppingSync.waiting).toBe(0);
    expect(signOutPending()).toBe(true);
    expect(session.me).toBeNull();
  });

  it('one change: “Sign out and lose it”', async () => {
    await show(1);
    await button('Sign out').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("1 change hasn't been sent yet. If you sign out now, it's lost.");
    await expect.element(button('Sign out and lose it')).toBeVisible();
  });
});
