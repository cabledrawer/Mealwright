// Settings › Your sign-in › Sign out (docs/dev/sync-protocol.md section 12): send what's waiting first, and
// warn before losing what still can't be sent.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { CHECK_MODE_STORAGE_KEY, checkMode } from '#lib/checkMode.svelte.js';
import { kitchen } from '#lib/freshness.svelte.js';
import { network } from '#lib/network.svelte.js';
import { phoneDatabaseName, setMeta } from '#lib/offline/phone.js';
import { SIGN_OUT_PENDING_KEY, signOutPending } from '#lib/offline/signOutPending.js';
import { addToQueue, readQueue } from '#lib/offline/store.js';
import { session } from '#lib/session.svelte.js';
import { household } from '#lib/people.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { HOUSEHOLD, person, people } from '#lib/testing/fakePeople.js';
import { makeAction } from '#lib/shopping/actions.js';
import { shoppingSync } from '#lib/shopping/sync.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { breakPhone, dropPhone, failPhoneDelete, freshPhone } from '#lib/testing/phone.js';
import { wipePending } from '#lib/offline/wipePending.svelte.js';
import Amounts from './amounts/+page.svelte';
import Appearance from './appearance/+page.svelte';
import SignIn from './sign-in/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const navigation = vi.hoisted(() => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => navigation);

const WARNING = '3 changes haven’t been sent yet. If you sign out now, they’re lost.';
const CANT_CHECK =
  'This phone couldn’t check for changes waiting to be sent. Nothing has been deleted.';
const ANYWAY = 'Sign out anyway. Anything waiting on this phone may be lost';

/**
 * Hold the browser's list of databases (phoneExists asks it before any read), so a look at
 * the phone database waits until released. Returns the release, which also restores it.
 */
function holdDatabaseList(): () => void {
  const real = indexedDB.databases.bind(indexedDB);
  let release = () => {};
  const gate = new Promise<void>((done) => (release = done));
  const spy = vi.spyOn(indexedDB, 'databases').mockImplementation(async () => {
    await gate;
    return real();
  });
  return () => {
    release();
    spy.mockRestore();
  };
}

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
    mounted.push(mount(SignIn, { target }));
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
      replace: true,
      refreshAll: true
    });
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['DELETE /session']);
    expect(await exists()).toBe(false);
    expect(page.getByRole('alert').elements()).toEqual([]);
  });

  it('where you’re signed in, unreachable: said in the list, not read out as an alert', async () => {
    await show(0);
    await expect
      .element(page.getByTestId('signed-in-places'))
      .toHaveTextContent('Can’t reach your Mealwright server. Check your connection.');
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
      .toHaveTextContent(`${WARNING}Still can’t reach your server.`);
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
      .toHaveTextContent('1 change hasn’t been sent yet. If you sign out now, it’s lost.');
    // Meanwhile, another tab of the app queues 3 more.
    for (const item of ['b', 'c', 'd']) {
      await addToQueue(makeAction({ kind: 'tick', item_id: item }), ME.id, 'device-1');
    }
    await button('Sign out and lose it').click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('4 changes haven’t been sent yet. If you sign out now, they’re lost.');
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
      .toHaveTextContent('1 change hasn’t been sent yet. If you sign out now, it’s lost.');
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
        'This phone couldn’t check for changes waiting to be sent. Nothing has been deleted.'
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
      .toHaveTextContent('1 change hasn’t been sent yet. If you sign out now, it’s lost.');
    expect(navigation.goto).not.toHaveBeenCalled();
  });

  it('Try again is the shared button, and says “Trying…” while it looks (cabledrawer 18 Oct)', async () => {
    await show(0);
    const mend = breakPhone();
    await button('Sign out').click();
    await expect.element(button('Try again')).toBeVisible();
    expect(button('Try again').element().classList.contains('mw-button')).toBe(true);
    expect(button('Try again').element().classList.contains('quiet')).toBe(false);
    const release = holdDatabaseList();
    await button('Try again').click();
    await expect.element(button('Trying…')).toBeDisabled();
    release();
    await expect.element(button('Try again')).toBeEnabled();
    await expect.element(page.getByRole('alert')).toHaveTextContent(CANT_CHECK);
    mend();
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
        replace: true,
        refreshAll: true
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
        .toHaveTextContent('1 change hasn’t been sent yet. If you sign out now, it’s lost.');
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
        .element(button('Sign out anyway. Anything waiting on this computer may be lost'))
        .toBeVisible();
      mend();
      await page.viewport(390, 800);
    });
  });
});

describe('the pint switch (Amounts)', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  const household = (pints: 'uk' | 'us') => ({ name: 'Home', pints });

  function open() {
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(Amounts, { target }));
    flushSync();
  }

  beforeEach(() => {
    session.me = { ...ME };
    network.reset();
  });

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  const pints = () => page.getByRole('switch', { name: 'Read pints as US pints' });

  it('shows UK pints as off, and sends the change when it is switched on', async () => {
    const requests = fakeApi({
      'GET /household': [200, household('uk')],
      'PATCH /household': [200, household('us')]
    });
    open();
    await expect.element(page.getByRole('heading', { name: 'Amounts' })).toBeVisible();
    await expect.element(pints()).not.toBeChecked();
    await expect
      .element(page.getByText('A pint is 568 ml (UK). Switch on for 473 ml (US).'))
      .toBeVisible();
    await pints().click();
    await expect.element(pints()).toBeChecked();
    await expect.element(page.getByText('A pint is 473 ml (US).')).toBeVisible();
    expect(requests.filter((r) => r.method === 'PATCH').map((r) => r.body)).toEqual([
      { pints: 'us' }
    ]);
  });

  it('shows UK again after an Undo of the change to US pints', async () => {
    fakeApi({
      'GET /household': [200, household('uk')],
      'PATCH /household': [200, household('us')]
    });
    open();
    await pints().click();
    await expect.element(pints()).toBeChecked();
    // Recent changes undoes it: the server says UK again, and the page is told.
    fakeApi({ 'GET /household': [200, household('uk')] });
    kitchen.changed({ elsewhere: true });
    await expect.element(pints()).not.toBeChecked();
  });

  it('shows US pints as on', async () => {
    fakeApi({ 'GET /household': [200, household('us')] });
    open();
    await expect.element(pints()).toBeChecked();
  });

  it('puts the switch back and says why when the server will not take it', async () => {
    fakeApi({
      'GET /household': [200, household('uk')],
      'PATCH /household': [403, { detail: 'Only the household’s admin can change this.' }]
    });
    open();
    await pints().click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Only the household’s admin can change this.');
    await expect.element(pints()).not.toBeChecked();
  });

  it('puts the switch back when the server can’t be reached', async () => {
    const requests = fakeApi({ 'GET /household': [200, household('uk')] });
    open();
    await expect.element(pints()).toBeVisible();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await pints().click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Can’t reach your Mealwright server. Nothing was changed.');
    await expect.element(pints()).not.toBeChecked();
    expect(requests.filter((r) => r.method === 'PATCH')).toEqual([]);
  });

  it('is off for a member, who is told an admin can change it', async () => {
    session.me = { ...ME, role: 'member' };
    fakeApi({ 'GET /household': [200, household('uk')] });
    open();
    await expect.element(pints()).toBeDisabled();
    await expect.element(page.getByText(/Only an admin can change this\./)).toBeVisible();
  });

  it('is not shown when the household can’t be read', async () => {
    const requests = fakeApi({});
    open();
    await vi.waitFor(() => expect(requests.some((r) => r.path.endsWith('/household'))).toBe(true));
    await new Promise((done) => setTimeout(done, 200));
    expect(pints().elements()).toEqual([]);
  });

  it('shows once the connection comes back, when Settings was opened offline', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    open();
    await new Promise((done) => setTimeout(done, 200));
    expect(pints().elements()).toEqual([]);
    vi.unstubAllGlobals();
    fakeApi({ 'GET /household': [200, household('uk')] });
    network.backAgain++;
    flushSync();
    await expect.element(pints()).toBeVisible();
  });
});

describe('Checking a recipe on the phone (Appearance, F141)', () => {
  const mounted: ReturnType<typeof mount>[] = [];

  beforeEach(() => {
    session.me = { ...ME };
    network.reset();
    localStorage.removeItem(CHECK_MODE_STORAGE_KEY);
    checkMode.reload();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(Appearance, { target }));
    flushSync();
  });

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    localStorage.removeItem(CHECK_MODE_STORAGE_KEY);
    checkMode.reload();
  });

  const focus = () => page.getByRole('radio', { name: /^Focus/ });
  const one = () => page.getByRole('radio', { name: /^One at a time/ });

  it('offers Focus and One at a time, with Focus chosen until it is changed', async () => {
    await expect.element(page.getByText('Checking a recipe on the phone')).toBeVisible();
    await expect.element(focus()).toBeChecked();
    await expect.element(one()).not.toBeChecked();
    await expect
      .element(page.getByText('On a computer, Check always shows the whole list.'))
      .toBeVisible();
  });

  it('keeps One at a time on this device, and Focus puts the default back', async () => {
    await one().click();
    await expect.element(one()).toBeChecked();
    expect(localStorage.getItem(CHECK_MODE_STORAGE_KEY)).toBe('one');
    expect(checkMode.choice).toBe('one');
    await focus().click();
    await expect.element(focus()).toBeChecked();
    expect(localStorage.getItem(CHECK_MODE_STORAGE_KEY)).toBeNull();
    expect(checkMode.choice).toBe('focus');
  });
});

describe('how amounts are shown (Amounts, 0.9 U2)', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  const household = (amounts_shown: 'as_written' | 'metric') => ({
    name: 'Home',
    pints: 'uk',
    amounts_shown
  });

  beforeEach(() => {
    session.me = { ...ME };
    network.reset();
  });

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  function open() {
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(Amounts, { target }));
    flushSync();
  }

  const asWritten = () => page.getByRole('radio', { name: 'As the recipe says (cups stay cups)' });
  const metric = () => page.getByRole('radio', { name: 'Metric: grams and ml' });

  it('shows the household’s choice and sends a change', async () => {
    const requests = fakeApi({
      'GET /household': [200, household('as_written')],
      'PATCH /household': [200, household('metric')]
    });
    open();
    await expect.element(asWritten()).toBeChecked();
    await expect.element(metric()).not.toBeChecked();
    // Cups come after 1.0, and nothing on screen converts yet: the page says both.
    await expect
      .element(page.getByText(/Cups and ounces as a choice come after version 1\.0\./))
      .toBeVisible();
    await expect.element(page.getByText(/your choice is kept\./)).toBeVisible();
    await metric().click();
    await expect.element(metric()).toBeChecked();
    expect(requests.filter((r) => r.method === 'PATCH').map((r) => r.body)).toEqual([
      { amounts_shown: 'metric' }
    ]);
  });

  it('goes back and says why when the server will not take it', async () => {
    fakeApi({
      'GET /household': [200, household('as_written')],
      'PATCH /household': [403, { detail: 'Only the household’s admin can change this.' }]
    });
    open();
    await metric().click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Only the household’s admin can change this.');
    await expect.element(asWritten()).toBeChecked();
  });

  it('is off for a member', async () => {
    session.me = { ...ME, role: 'member' };
    fakeApi({ 'GET /household': [200, household('metric')] });
    open();
    await expect.element(metric()).toBeChecked();
    await expect.element(asWritten()).toBeDisabled();
    await expect.element(metric()).toBeDisabled();
  });
});

describe('your own reset link, on Your sign-in', () => {
  // A member isn't shown the Household pages, so the way to cancel a reset link made for them is
  // here (placement proposed, for cabledrawer).
  let view: ReturnType<typeof mount> | undefined;
  afterEach(() => {
    if (view) unmount(view);
    view = undefined;
    document.body.innerHTML = '';
    household.forget();
    vi.unstubAllGlobals();
  });

  it('a member sees an unused link made for them and cancels it', async () => {
    let pending = true;
    session.me = { ...ME, role: 'member' };
    const me = () =>
      person(2, 'Sam', {
        is_me: true,
        login: {
          username: 'sam',
          role: 'member',
          shared: false,
          has_password: true,
          signs_in: true,
          link_pending: false,
          link_used_at: null,
          reset_pending: pending
        }
      });
    const seen = fakeApi({
      'GET /people': () => [200, people([me()], { can_change: false })],
      'GET /household': [200, HOUSEHOLD],
      'DELETE /me/reset-link': () => {
        pending = false;
        return [204, null];
      }
    });
    const target = document.body.appendChild(document.createElement('div'));
    view = mount(SignIn, { target });
    flushSync();
    const line = page.getByText('Someone made a reset link for your password', { exact: false });
    await expect.element(line).toBeVisible();
    await page.getByRole('button', { name: 'Cancel the link' }).click();
    await vi.waitFor(() =>
      expect(seen.filter((r) => r.method === 'DELETE' && r.path === '/me/reset-link')).toHaveLength(
        1
      )
    );
    await vi.waitFor(() => expect(line.query()).toBeNull());
    expect(toasts.current?.message).toBe('Reset link cancelled');
  });
  it('shows a link made after the list was loaded earlier (it reads the list each time it opens)', async () => {
    let pending = false;
    session.me = { ...ME, role: 'member' };
    const me = () =>
      person(2, 'Sam', {
        is_me: true,
        login: {
          username: 'sam',
          role: 'member',
          shared: false,
          has_password: true,
          signs_in: true,
          link_pending: false,
          link_used_at: null,
          reset_pending: pending
        }
      });
    fakeApi({
      'GET /people': () => [200, people([me()], { can_change: false })],
      'GET /household': [200, HOUSEHOLD]
    });
    await household.load();
    expect(household.loaded).toBe(true);
    pending = true;
    const target = document.body.appendChild(document.createElement('div'));
    view = mount(SignIn, { target });
    flushSync();
    await expect
      .element(page.getByText('Someone made a reset link for your password', { exact: false }))
      .toBeVisible();
  });
});
