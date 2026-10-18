// Settings → Sign out (docs/dev/sync-protocol.md section 12): send what's waiting first, and
// warn before losing what still can't be sent.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '$lib/network.svelte';
import { phoneDatabaseName, setMeta } from '$lib/offline/phone';
import { SIGN_OUT_PENDING_KEY, signOutPending } from '$lib/offline/signOutPending';
import { addToQueue, readQueue } from '$lib/offline/store';
import { session } from '$lib/session.svelte';
import { makeAction } from '$lib/shopping/actions';
import { shoppingSync } from '$lib/shopping/sync.svelte';
import { fakeApi, type FakeRequest } from '$lib/testing/fakeApi';
import { ME } from '$lib/testing/fakeShopping';
import { breakPhone, dropPhone, failPhoneDelete, freshPhone } from '$lib/testing/phone';
import { wipePending } from '$lib/offline/wipePending.svelte';
import Settings from './+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const navigation = vi.hoisted(() => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => navigation);

const WARNING = "3 changes haven't been sent yet. If you sign out now, they're lost.";
const CANT_CHECK =
  "This phone couldn't check for changes waiting to be sent. Nothing has been deleted.";
const ANYWAY = 'Sign out anyway — anything waiting on this phone may be lost';

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
    vi.restoreAllMocks();
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

  it('Stay signed in is a real button, as Try again is, on the quiet fill (cabledrawer 18 Oct)', async () => {
    await show(3);
    await button('Sign out').click();
    await expect.element(button('Stay signed in')).toBeVisible();
    const stay = button('Stay signed in').element() as HTMLButtonElement;
    const main = button('Try sending now').element() as HTMLButtonElement;
    expect(stay.tagName).toBe('BUTTON');
    expect(stay.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    expect(stay.getBoundingClientRect().width).toBe(main.getBoundingClientRect().width);
    const look = getComputedStyle(stay);
    expect(look.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
    expect(look.backgroundColor).not.toBe(getComputedStyle(main).backgroundColor);
    expect(look.textDecorationLine).toBe('none');
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

  it('another tab queued more since the warning: warns again with the new count, wipes nothing', async () => {
    await show(1);
    await button('Sign out').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("1 change hasn't been sent yet. If you sign out now, it's lost.");
    // Meanwhile, another tab of the app queues 3 more.
    for (const item of ['b', 'c', 'd']) {
      await addToQueue(makeAction({ kind: 'tick', item_id: item }), ME.id, 'device-1');
    }
    await button('Sign out and lose it').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("4 changes haven't been sent yet. If you sign out now, they're lost.");
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(await exists()).toBe(true);
    expect(await readQueue()).toHaveLength(4);
    expect(signOutPending()).toBe(false);
    expect(session.me).not.toBeNull();

    // Warned about all 4: losing them goes ahead.
    await button('Sign out and lose them').click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(await exists()).toBe(false);
  });

  it('one change: “Sign out and lose it”', async () => {
    await show(1);
    await button('Sign out').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("1 change hasn't been sent yet. If you sign out now, it's lost.");
    await expect.element(button('Sign out and lose it')).toBeVisible();
  });

  it('a phone database that can’t be read: says so, and doesn’t sign out or wipe', async () => {
    await show(0);
    await addToQueue(makeAction({ kind: 'tick', item_id: 'other-tab' }), ME.id, 'device-1');
    const requests = reachable();
    const mend = breakPhone();
    await button('Sign out').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(
        "This phone couldn't check for changes waiting to be sent. Nothing has been deleted."
      );
    await expect.element(button('Try again')).toBeVisible();
    await expect.element(button('Stay signed in')).toBeVisible();
    await expect.element(button(ANYWAY)).toBeVisible();
    expect(page.getByRole('button', { name: /lose/ }).elements()).toEqual([]);
    expect(requests).toEqual([]);
    expect(navigation.goto).not.toHaveBeenCalled();
    mend();
    expect(await exists()).toBe(true);
    expect(await readQueue()).toHaveLength(1);

    // Readable again: Try again finds the change the list hadn't read, and warns as usual.
    await button('Try again').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("1 change hasn't been sent yet. If you sign out now, it's lost.");
    expect(navigation.goto).not.toHaveBeenCalled();
  });

  it('Stay signed in closes the couldn’t-check warning', async () => {
    await show(0);
    const mend = breakPhone();
    await button('Sign out').click();
    await button('Stay signed in').click();
    expect(page.getByRole('alert').elements()).toEqual([]);
    await expect.element(button('Sign out')).toBeEnabled();
    mend();
    expect(await exists()).toBe(true);
  });

  describe('Sign out anyway, when the phone couldn’t check (cabledrawer 18 Oct)', () => {
    it('wipes this browser as usual, ends the session and goes to sign in', async () => {
      await show(0);
      await addToQueue(makeAction({ kind: 'tick', item_id: 'unseen' }), ME.id, 'device-1');
      const requests = reachable();
      const mend = breakPhone();
      await button('Sign out').click();
      await button(ANYWAY).click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      mend();
      expect(navigation.goto).toHaveBeenCalledWith('/sign-in', {
        replaceState: true,
        invalidateAll: true
      });
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['DELETE /session']);
      expect(await exists()).toBe(false);
      expect(session.me).toBeNull();
    });

    it('readable again by then, with a change waiting: the usual warning instead, nothing wiped', async () => {
      await show(0);
      const mend = breakPhone();
      await button('Sign out').click();
      await expect.element(button(ANYWAY)).toBeVisible();
      mend();
      await addToQueue(makeAction({ kind: 'tick', item_id: 'unseen' }), ME.id, 'device-1');
      await button(ANYWAY).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent("1 change hasn't been sent yet. If you sign out now, it's lost.");
      expect(navigation.goto).not.toHaveBeenCalled();
      expect(await readQueue()).toHaveLength(1);
    });

    it('the phone database can’t be deleted either: still signed out, and the wipe left pending', async () => {
      await show(0);
      const requests = reachable();
      const mendRead = breakPhone();
      const mendDelete = failPhoneDelete();
      await button('Sign out').click();
      await button(ANYWAY).click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      mendRead();
      mendDelete();
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['DELETE /session']);
      expect(session.me).toBeNull();
      expect(wipePending()).toBe(true);
    });

    it('Try again that still can’t check says so again, read out again', async () => {
      await show(0);
      const mend = breakPhone();
      await button('Sign out').click();
      await expect.element(page.getByRole('alert')).toHaveTextContent(CANT_CHECK);
      const before = page.getByRole('alert').element();
      await button('Try again').click();
      await vi.waitFor(() => expect(page.getByRole('alert').element()).not.toBe(before));
      await expect.element(page.getByRole('alert')).toHaveTextContent(CANT_CHECK);
      mend();
    });

    it('on a computer it says “this computer”', async () => {
      await page.viewport(1280, 800);
      await show(0);
      const mend = breakPhone();
      await button('Sign out').click();
      await expect
        .element(button('Sign out anyway — anything waiting on this computer may be lost'))
        .toBeVisible();
      mend();
      await page.viewport(390, 800);
    });
  });
});
