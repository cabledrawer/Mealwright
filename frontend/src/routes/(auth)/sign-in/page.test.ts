import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { startDevice } from '$lib/offline/device';
import { turnAway } from '$lib/offline/held';
import { getMeta, phoneDatabaseName, setMeta } from '$lib/offline/phone';
import { addToQueue, dropFromQueue, readQueue } from '$lib/offline/store';
import { fakeApi, type FakeRequest } from '$lib/testing/fakeApi';
import { breakPhone, dropPhone, freshPhone } from '$lib/testing/phone';
import SignIn from './+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const navigation = vi.hoisted(() => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => navigation);
vi.mock('$app/state', () => ({ page: { url: new URL('http://mealwright.test/sign-in') } }));

const DEVICE = '11111111-2222-4333-8444-555555555555';
const WREN = { id: 2, name: 'Wren', username: 'wren', role: 'member', theme: 'auto' };
const ARLO = { id: 3, name: 'Arlo', username: 'arlo', role: 'member', theme: 'auto' };
const tick = (id: string) => ({
  id,
  made_at: '2026-10-18T09:00:00Z',
  seen: 0,
  kind: 'tick' as const,
  item_id: 'i'
});

/** Wren signed in here, and left `count` changes waiting when her sign-in ran out. */
async function wrensPhone(count: number) {
  await setMeta({
    device_id: DEVICE,
    login_id: 2,
    login_name: 'Wren',
    username: 'wren',
    role: 'member',
    protocol: 1
  });
  for (let i = 0; i < count; i++) await addToQueue(tick(`r${i}`), 2, DEVICE);
}

describe('signing in on a phone holding waiting changes (11.5)', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let requests: FakeRequest[];

  function serve() {
    requests = fakeApi({
      'POST /session': (request) => {
        const who = (request.body as { username: string }).username.trim().toLowerCase();
        return who === 'wren' ? [200, WREN] : [200, ARLO];
      },
      'DELETE /session': [204, null]
    });
  }

  function show() {
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(
      mount(SignIn, {
        target,
        props: { data: { setup: { needs_setup: false, plain_http_allowed: false } } } as never
      })
    );
    flushSync();
  }

  async function fillIn(username: string) {
    await userEvent.fill(page.getByLabelText('Username'), username);
    await userEvent.fill(page.getByLabelText('Password'), 'a long password');
  }

  beforeEach(async () => {
    freshPhone();
    navigation.goto.mockClear();
    serve();
    // The bottom tabs' layout: "this phone".
    await page.viewport(390, 800);
  });

  afterEach(async () => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    await dropPhone();
  });

  it('asks the same person to sign in again, keeping the changes and the device', async () => {
    await wrensPhone(3);
    show();
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent('Please sign in again. Your 3 changes are kept on this phone.');
    await fillIn('Wren');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /session']);
    expect(await readQueue()).toHaveLength(3);
    expect(await getMeta('device_id')).toBe(DEVICE);
  });

  it('FE-3: another login is warned, never sends, and carrying on wipes the phone', async () => {
    await wrensPhone(3);
    show();
    await fillIn('arlo');
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent(
        "Wren's 3 changes are waiting on this phone. Sign in as Wren to send them."
      );
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 3 changes haven't been sent yet. If you carry on, they're lost.");
    // Nothing has gone to the server yet, and nothing ever goes from Wren's queue.
    expect(requests).toEqual([]);

    await page.getByRole('button', { name: 'Carry on and lose them' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /session']);
    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
    // A new device ID is made on the next start: the old one is gone with the database.
    expect(await getMeta('device_id')).toBeUndefined();
  });

  it('carrying on with a wrong password wipes nothing: Wren’s changes stay', async () => {
    await wrensPhone(3);
    let right = false;
    requests = fakeApi({
      'POST /session': () =>
        right ? [200, ARLO] : [401, { detail: 'That username and password don’t match.' }],
      'DELETE /session': [204, null]
    });
    show();
    await fillIn('arlo');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.getByRole('button', { name: 'Carry on and lose them' }).click();
    await vi.waitFor(() => expect(requests).toHaveLength(1));
    await expect.element(page.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(await readQueue()).toHaveLength(3);
    expect(await getMeta('device_id')).toBe(DEVICE);

    // The right password this time: warned again, and only carrying on then wipes.
    right = true;
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.getByRole('button', { name: 'Carry on and lose them' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
  });

  it('a different login always starts clean, even with nothing waiting (cabledrawer 18 Oct)', async () => {
    await wrensPhone(0);
    show();
    await fillIn('arlo');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /session']);
    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
  });

  it('on the sidebar layout it says “this computer”', async () => {
    await wrensPhone(2);
    await page.viewport(1280, 800);
    show();
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent('Please sign in again. Your 2 changes are kept on this computer.');
    await fillIn('arlo');
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent(
        "Wren's 2 changes are waiting on this computer. Sign in as Wren to send them."
      );
  });

  it('“Sign in as Wren instead” keeps everything and puts Wren’s username in', async () => {
    await wrensPhone(1);
    show();
    await fillIn('arlo');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 1 change hasn't been sent yet. If you carry on, it's lost.");
    await page.getByRole('button', { name: 'Sign in as Wren instead' }).click();
    await expect.element(page.getByLabelText('Username')).toHaveValue('wren');
    await expect.element(page.getByLabelText('Password')).toHaveValue('');
    await expect.element(page.getByLabelText('Password')).toHaveFocus();
    expect(page.getByRole('alert').elements()).toEqual([]);
    expect(requests).toEqual([]);
    expect(await readQueue()).toHaveLength(1);
  });

  it('another login after all (the server says so): signs it out again, and warns', async () => {
    await wrensPhone(2);
    requests = fakeApi({ 'POST /session': [200, ARLO], 'DELETE /session': [204, null] });
    show();
    // Typed as Wren, but the server signed in someone else.
    await fillIn('wren');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 2 changes haven't been sent yet. If you carry on, they're lost.");
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'POST /session',
      'DELETE /session'
    ]);
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(await readQueue()).toHaveLength(2);
  });

  it('after the app turned Arlo away over Wren’s change: his username is in, he’s warned, and carrying on wipes, with a new device ID', async () => {
    await wrensPhone(1);
    turnAway('arlo');
    show();
    await expect.element(page.getByLabelText('Username')).toHaveValue('arlo');
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent("Wren's 1 change is waiting on this phone. Sign in as Wren to send it.");
    await userEvent.fill(page.getByLabelText('Password'), 'a long password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 1 change hasn't been sent yet. If you carry on, it's lost.");
    expect(requests).toEqual([]);
    await page.getByRole('button', { name: 'Carry on and lose it' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
    // The app then starts as Arlo, with a device ID of his own.
    await startDevice(ARLO);
    const fresh = await getMeta('device_id');
    expect(fresh).toMatch(/^[0-9a-f-]{36}$/);
    expect(fresh).not.toBe(DEVICE);
    expect(await getMeta('login_id')).toBe(3);
    expect(await readQueue()).toEqual([]);
  });

  it('changes queued in another tab after this page opened are read again: warned, never wiped', async () => {
    await wrensPhone(0);
    show();
    await expect.element(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
    expect(page.getByRole('status').elements()).toEqual([]);
    // Meanwhile, in another tab, Wren queues 2 changes and her sign-in runs out.
    await addToQueue(tick('t1'), 2, DEVICE);
    await addToQueue(tick('t2'), 2, DEVICE);
    await fillIn('arlo');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 2 changes haven't been sent yet. If you carry on, they're lost.");
    expect(requests).toEqual([]);
    expect(await readQueue()).toHaveLength(2);
    expect(await getMeta('device_id')).toBe(DEVICE);
  });

  it('carrying on loses only what the warning showed: one more queued since, and it warns again', async () => {
    await wrensPhone(1);
    show();
    await fillIn('arlo');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 1 change hasn't been sent yet. If you carry on, it's lost.");
    // Another tab queues one more before Carry on is pressed.
    await addToQueue(tick('t2'), 2, DEVICE);
    await page.getByRole('button', { name: 'Carry on and lose it' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 2 changes haven't been sent yet. If you carry on, they're lost.");
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'POST /session',
      'DELETE /session'
    ]);
    expect(navigation.goto).not.toHaveBeenCalled();
    expect(await readQueue()).toHaveLength(2);
    expect(await getMeta('device_id')).toBe(DEVICE);

    // Carrying on now loses both, and only then.
    await page.getByRole('button', { name: 'Carry on and lose them' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
  });

  it('two tabs: another tab sends the change the warning showed and queues a new one; carrying on warns again, never wipes', async () => {
    await wrensPhone(1);
    show();
    await fillIn('arlo');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 1 change hasn't been sent yet. If you carry on, it's lost.");
    // In Wren's other tab: her change goes, and she makes a new one. Still 1 waiting.
    const [shown] = await readQueue();
    await dropFromQueue([shown!.seq!]);
    await addToQueue(tick('new'), 2, DEVICE);

    await page.getByRole('button', { name: 'Carry on and lose it' }).click();
    // The new change was never shown: warned again, and nothing wiped.
    await vi.waitFor(() =>
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
        'POST /session',
        'DELETE /session'
      ])
    );
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 1 change hasn't been sent yet. If you carry on, it's lost.");
    expect(navigation.goto).not.toHaveBeenCalled();
    expect((await readQueue()).map((e) => e.action.id)).toEqual(['new']);
    expect(await getMeta('device_id')).toBe(DEVICE);

    // Carrying on after this warning loses the new one, and only then.
    await page.getByRole('button', { name: 'Carry on and lose it' }).click();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
    const databases = (await indexedDB.databases()).map((d) => d.name);
    expect(databases).not.toContain(phoneDatabaseName());
  });

  it('says nothing when nothing is waiting', async () => {
    show();
    await expect.element(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
    expect(page.getByRole('status').elements()).toEqual([]);
  });

  it('a phone database that can’t be read: says so, sends nothing, and wipes nothing', async () => {
    await wrensPhone(2);
    const mend = breakPhone();
    show();
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent(
        "This phone couldn't check for changes waiting to be sent. Nothing has been deleted."
      );
    await fillIn('arlo');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect.element(page.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    // It looked again on Sign in, still couldn't, and so let nobody in over it.
    expect(requests).toEqual([]);
    expect(navigation.goto).not.toHaveBeenCalled();
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent(
        "This phone couldn't check for changes waiting to be sent. Nothing has been deleted."
      );
    mend();
    expect(await readQueue()).toHaveLength(2);
    expect(await getMeta('login_id')).toBe(2);
    expect(await getMeta('device_id')).toBe(DEVICE);

    // Readable again: Sign in looks again, and Arlo gets the usual warning.
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent("Wren's 2 changes haven't been sent yet. If you carry on, they're lost.");
    expect(requests).toEqual([]);
  });

  it('on a computer it says “this computer” couldn’t check', async () => {
    await wrensPhone(1);
    await page.viewport(1280, 800);
    const mend = breakPhone();
    show();
    await expect
      .element(page.getByRole('status'))
      .toHaveTextContent(
        "This computer couldn't check for changes waiting to be sent. Nothing has been deleted."
      );
    mend();
  });
});
