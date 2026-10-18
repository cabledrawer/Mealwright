import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { startDevice } from '$lib/offline/device';
import { turnAway } from '$lib/offline/held';
import { getMeta, phoneDatabaseName, setMeta } from '$lib/offline/phone';
import { addToQueue, dropFromQueue, readQueue } from '$lib/offline/store';
import { signOutState } from '$lib/offline/unfinished.svelte';
import { fakeApi, type FakeRequest } from '$lib/testing/fakeApi';
import { breakPhone, dropPhone, failPhoneDelete, freshPhone } from '$lib/testing/phone';
import { wipeDevice } from '$lib/offline/wipe';
import { WIPE_PENDING_KEY, wipePending, wipeState } from '$lib/offline/wipePending.svelte';
import SignIn from './+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const navigation = vi.hoisted(() => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => navigation);
vi.mock('$app/state', () => ({ page: { url: new URL('http://mealwright.test/sign-in') } }));

const DEVICE = '11111111-2222-4333-8444-555555555555';
const CANT_TEXT =
  "This phone couldn't check for changes waiting to be sent. Nothing has been deleted.";
const phoneThere = async () =>
  (await indexedDB.databases()).some((db) => db.name === phoneDatabaseName());
const WREN = { id: 2, name: 'Wren', username: 'wren', role: 'member', theme: 'auto' };
const ARLO = { id: 3, name: 'Arlo', username: 'arlo', role: 'member', theme: 'auto' };
const tick = (id: string) => ({
  id,
  made_at: '2026-10-18T09:00:00Z',
  seen: 0,
  kind: 'tick' as const,
  item_id: 'i'
});

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
    signOutState.unfinished = false;
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
      .toHaveTextContent(
        "You were signed out because Wren's change is waiting on this phone. Sign in as Wren to send it."
      );
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

  describe('why Arlo was signed out (cabledrawer 18 Oct)', () => {
    it('many changes: says why, in place of the usual line', async () => {
      await wrensPhone(3);
      turnAway('arlo');
      show();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(
          "You were signed out because Wren's 3 changes are waiting on this phone. Sign in as Wren to send them."
        );
      expect(page.getByRole('status').elements()).toHaveLength(1);
      // The warning and its buttons are as they were.
      await userEvent.fill(page.getByLabelText('Password'), 'a long password');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent(
          "Wren's 3 changes haven't been sent yet. If you carry on, they're lost."
        );
      await expect
        .element(page.getByRole('button', { name: 'Sign in as Wren instead' }))
        .toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Carry on and lose them' }))
        .toBeVisible();
    });

    it('on a computer it says “this computer”', async () => {
      await wrensPhone(2);
      await page.viewport(1280, 800);
      turnAway('arlo');
      show();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(
          "You were signed out because Wren's 2 changes are waiting on this computer. Sign in as Wren to send them."
        );
    });

    it('opened as usual (nobody turned away): the usual line, not why', async () => {
      await wrensPhone(1);
      show();
      await fillIn('arlo');
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent("Wren's 1 change is waiting on this phone. Sign in as Wren to send it.");
    });

    it('only right after: a page opened again says it the usual way', async () => {
      await wrensPhone(1);
      turnAway('arlo');
      show();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(
          "You were signed out because Wren's change is waiting on this phone. Sign in as Wren to send it."
        );
      for (const component of mounted.splice(0)) unmount(component);
      document.body.innerHTML = '';
      show();
      await fillIn('arlo');
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent("Wren's 1 change is waiting on this phone. Sign in as Wren to send it.");
    });

    it('another username typed in: the usual line', async () => {
      await wrensPhone(1);
      turnAway('arlo');
      show();
      await userEvent.fill(page.getByLabelText('Username'), 'meena');
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent("Wren's 1 change is waiting on this phone. Sign in as Wren to send it.");
    });

    it('while the server hasn’t ended his session, it doesn’t say he was signed out', async () => {
      await wrensPhone(1);
      fakeApi({ 'DELETE /session': [500, { detail: 'Something broke.' }] });
      signOutState.unfinished = true;
      turnAway('arlo');
      show();
      await expect
        .element(
          page.getByText("Wren's 1 change is waiting on this phone. Sign in as Wren to send it.")
        )
        .toHaveAttribute('role', 'status');
      fakeApi({ 'DELETE /session': [204, null] });
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(
          "You were signed out because Wren's change is waiting on this phone. Sign in as Wren to send it."
        );
    });
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

  describe('a phone database that can’t be read (cabledrawer 18 Oct)', () => {
    const CANT_CHECK = CANT_TEXT;
    const ANYWAY = 'Carry on anyway — anything waiting on this phone may be lost';

    it('another login: says so on Sign in, with Try again and Carry on anyway; sends and wipes nothing', async () => {
      await wrensPhone(2);
      const mend = breakPhone();
      show();
      await expect.element(page.getByRole('status')).toHaveTextContent(CANT_CHECK);
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      // A press always says what happened: the warning, read out.
      await expect.element(page.getByRole('alert')).toHaveTextContent(CANT_CHECK);
      await expect.element(page.getByRole('button', { name: 'Try again' })).toBeVisible();
      await expect.element(page.getByRole('button', { name: ANYWAY })).toBeVisible();
      // The line it replaces isn't there twice.
      expect(page.getByText(CANT_CHECK).elements()).toHaveLength(1);
      expect(requests).toEqual([]);
      expect(navigation.goto).not.toHaveBeenCalled();

      // Try again, still unreadable: the warning again, read out again.
      const before = page.getByRole('alert').element();
      await page.getByRole('button', { name: 'Try again' }).click();
      await vi.waitFor(() => expect(page.getByRole('alert').element()).not.toBe(before));
      await expect.element(page.getByRole('alert')).toHaveTextContent(CANT_CHECK);
      expect(requests).toEqual([]);
      mend();
      expect(await readQueue()).toHaveLength(2);
      expect(await getMeta('login_id')).toBe(2);
      expect(await getMeta('device_id')).toBe(DEVICE);

      // Readable again: Try again looks again, and Arlo gets the usual warning.
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent(
          "Wren's 2 changes haven't been sent yet. If you carry on, they're lost."
        );
      expect(requests).toEqual([]);
    });

    it('the same login carries on: signs in, keeping and writing nothing new', async () => {
      await wrensPhone(2);
      await startDevice(WREN);
      const mend = breakPhone();
      show();
      await fillIn('Wren');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /session']);
      mend();
      expect(await readQueue()).toHaveLength(2);
      expect(await getMeta('login_id')).toBe(2);
      expect(await getMeta('device_id')).toBe(DEVICE);
    });

    it('Carry on anyway: signs in, then wipes this phone, as at signing out', async () => {
      await wrensPhone(2);
      const mend = breakPhone();
      show();
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.getByRole('button', { name: ANYWAY }).click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      mend();
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /session']);
      expect(await phoneThere()).toBe(false);
    });

    it('Carry on anyway with a wrong password wipes nothing', async () => {
      await wrensPhone(1);
      requests = fakeApi({
        'POST /session': [401, { detail: 'That username and password don’t match.' }]
      });
      const mend = breakPhone();
      show();
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.getByRole('button', { name: ANYWAY }).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('That username and password don’t match.');
      mend();
      expect(await readQueue()).toHaveLength(1);
      expect(await getMeta('login_id')).toBe(2);
    });

    it('Carry on anyway, but readable by then and Wren’s changes there: the usual warning, nothing wiped', async () => {
      await wrensPhone(2);
      const mend = breakPhone();
      show();
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect.element(page.getByRole('button', { name: ANYWAY })).toBeVisible();
      mend();
      await page.getByRole('button', { name: ANYWAY }).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent(
          "Wren's 2 changes haven't been sent yet. If you carry on, they're lost."
        );
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
        'POST /session',
        'DELETE /session'
      ]);
      expect(navigation.goto).not.toHaveBeenCalled();
      expect(await readQueue()).toHaveLength(2);
    });

    it('Carry on anyway, and the phone database then can’t be deleted: signed out again, and it says so', async () => {
      await wrensPhone(1);
      const mendRead = breakPhone();
      const mendDelete = failPhoneDelete();
      show();
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.getByRole('button', { name: ANYWAY }).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent(
          "This phone couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again."
        );
      mendRead();
      mendDelete();
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
        'POST /session',
        'DELETE /session'
      ]);
      expect(navigation.goto).not.toHaveBeenCalled();
      expect(wipePending()).toBe(true);
    });

    it('on a computer it says “this computer”', async () => {
      await wrensPhone(1);
      await page.viewport(1280, 800);
      const mend = breakPhone();
      show();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(
          "This computer couldn't check for changes waiting to be sent. Nothing has been deleted."
        );
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect
        .element(
          page.getByRole('button', {
            name: 'Carry on anyway — anything waiting on this computer may be lost'
          })
        )
        .toBeVisible();
      mend();
    });
  });

  describe('couldn’t finish signing out (the server answered, but kept the session)', () => {
    const UNFINISHED = "Couldn't finish signing out on this phone.";
    let refuse = true;

    beforeEach(() => {
      refuse = true;
      requests = fakeApi({
        'POST /session': [200, ARLO],
        'DELETE /session': () => (refuse ? [500, { detail: 'Something broke.' }] : [204, null])
      });
    });

    it('says so once, “Try again” asks again, and it goes once the session has ended', async () => {
      await wrensPhone(1);
      signOutState.unfinished = true;
      turnAway('arlo');
      show();
      // On opening the page: a status (an alert there on load may not be read out).
      await expect.element(page.getByText(UNFINISHED)).toHaveAttribute('role', 'status');
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByRole('button', { name: 'Try again' })).toBeEnabled();
      // Still refused: the same one line, not another, read out this time.
      expect(page.getByText(UNFINISHED).elements()).toHaveLength(1);
      await expect.element(page.getByRole('alert')).toHaveTextContent(UNFINISHED);
      refuse = false;
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByText(UNFINISHED)).not.toBeInTheDocument();
      expect(page.getByRole('button', { name: /^Try/ }).elements()).toEqual([]);
      expect(page.getByRole('alert').elements()).toEqual([]);
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
        'DELETE /session',
        'DELETE /session'
      ]);
      // Nothing wiped meanwhile, and nothing else sent.
      expect(navigation.goto).not.toHaveBeenCalled();
      expect(await readQueue()).toHaveLength(1);
      expect(await getMeta('device_id')).toBe(DEVICE);
    });

    it('another login after all, and the server won’t end it: says so beside the warning, and wipes nothing', async () => {
      await wrensPhone(2);
      show();
      await fillIn('wren');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect.element(page.getByText(UNFINISHED)).toBeVisible();
      await expect
        .element(
          page.getByText("Wren's 2 changes haven't been sent yet. If you carry on, they're lost.")
        )
        .toBeVisible();
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
        'POST /session',
        'DELETE /session'
      ]);
      expect(signOutState.unfinished).toBe(true);
      expect(navigation.goto).not.toHaveBeenCalled();
      expect(await readQueue()).toHaveLength(2);
      expect(await getMeta('login_id')).toBe(2);
    });

    it('a sign-in that goes through clears it', async () => {
      signOutState.unfinished = true;
      show();
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      expect(signOutState.unfinished).toBe(false);
    });

    it('on a computer it says “this computer”', async () => {
      await page.viewport(1280, 800);
      signOutState.unfinished = true;
      show();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent("Couldn't finish signing out on this computer.");
    });
  });

  describe('a wipe that couldn’t delete the phone database (cabledrawer 18 Oct)', () => {
    const WIPE_FAILED =
      "This phone couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again.";

    it('says so on opening; Try again that fails says so again; once deleted, it goes', async () => {
      await wrensPhone(2);
      const mend = failPhoneDelete();
      await wipeDevice();
      show();
      // On opening the page: a status, not an alert (read out without interrupting).
      await expect.element(page.getByRole('status')).toHaveTextContent(WIPE_FAILED);
      // Nothing of Wren's is shown.
      expect(page.getByText(/Wren/).elements()).toEqual([]);
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByRole('alert')).toHaveTextContent(WIPE_FAILED);
      mend();
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByText(WIPE_FAILED)).not.toBeInTheDocument();
      expect(wipePending()).toBe(false);
      expect(await phoneThere()).toBe(false);
      expect(requests).toEqual([]);
    });

    it('a wipe another tab is still running says nothing; once it fails there, it says so', async () => {
      await wrensPhone(2);
      // Another tab has started wiping (sync protocol 12) and is still deleting.
      localStorage.setItem(WIPE_PENDING_KEY, '1');
      show();
      await expect.element(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
      expect(page.getByText(/couldn't delete/).elements()).toEqual([]);
      expect(page.getByRole('button', { name: 'Try again' }).elements()).toEqual([]);
      // Nothing of Wren's is shown meanwhile either.
      expect(page.getByText(/Wren/).elements()).toEqual([]);
      // Its delete then fails: that tab's flag says so, and this one hears it.
      localStorage.setItem(WIPE_PENDING_KEY, 'failed');
      dispatchEvent(new StorageEvent('storage', { key: WIPE_PENDING_KEY, newValue: 'failed' }));
      await expect.element(page.getByRole('status')).toHaveTextContent(WIPE_FAILED);
      // And a Try again in that tab that works takes it away here too.
      localStorage.removeItem(WIPE_PENDING_KEY);
      dispatchEvent(new StorageEvent('storage', { key: WIPE_PENDING_KEY, newValue: null }));
      await expect.element(page.getByText(WIPE_FAILED)).not.toBeInTheDocument();
      expect(requests).toEqual([]);
    });

    it('a wipe left unfinished by a closed tab: Sign in finishes it before letting anyone in', async () => {
      await wrensPhone(2);
      localStorage.setItem(WIPE_PENDING_KEY, '1');
      show();
      await fillIn('wren');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      expect(await phoneThere()).toBe(false);
      expect(wipePending()).toBe(false);
    });

    it('a delete that failed in another tab or before a reload says so', async () => {
      await wrensPhone(1);
      const mend = failPhoneDelete();
      await wipeDevice();
      mend();
      // This tab didn't run that wipe: only the flag in localStorage knows.
      wipeState.failed = false;
      show();
      await expect.element(page.getByRole('status')).toHaveTextContent(WIPE_FAILED);
    });

    it('Sign in tries the wipe again first: still failing, it says so and sends nothing', async () => {
      await wrensPhone(1);
      const mend = failPhoneDelete();
      await wipeDevice();
      show();
      await fillIn('wren');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect.element(page.getByRole('alert')).toHaveTextContent(WIPE_FAILED);
      expect(requests).toEqual([]);
      expect(navigation.goto).not.toHaveBeenCalled();
      mend();
      await page.getByRole('button', { name: 'Sign in' }).click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /session']);
      expect(await phoneThere()).toBe(false);
    });

    it('while Sign in tries the wipe again, it shows it’s working and can’t be pressed twice', async () => {
      await wrensPhone(1);
      const mend = failPhoneDelete();
      await wipeDevice();
      mend();
      show();
      await fillIn('wren');
      // Another tab holds the queue lock, so the wipe waits (as a slow delete would).
      let release = () => {};
      const held = new Promise<void>((done) => (release = done));
      let locked = () => {};
      const lockTaken = new Promise<void>((done) => (locked = done));
      void navigator.locks.request(`${phoneDatabaseName()}.queue`, () => {
        locked();
        return held;
      });
      await lockTaken;
      await page.getByRole('button', { name: 'Sign in' }).click();
      const working = page.getByRole('button', { name: 'Signing in…' });
      await expect.element(working).toBeDisabled();
      await expect.element(page.getByRole('button', { name: 'Trying…' })).toBeDisabled();
      // Enter in the form while it's working does nothing more.
      await userEvent.type(page.getByLabelText('Password'), '{Enter}');
      release();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalledTimes(1));
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /session']);
      expect(await phoneThere()).toBe(false);
    });

    it('a different login’s wipe failing after its sign-in: signed out again, and it says so', async () => {
      await wrensPhone(0);
      const mend = failPhoneDelete();
      show();
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect.element(page.getByRole('alert')).toHaveTextContent(WIPE_FAILED);
      mend();
      expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
        'POST /session',
        'DELETE /session'
      ]);
      expect(navigation.goto).not.toHaveBeenCalled();
      expect(wipePending()).toBe(true);
    });

    it('on a computer it says “this computer”', async () => {
      await page.viewport(1280, 800);
      const mend = failPhoneDelete();
      await wrensPhone(0);
      await wipeDevice();
      mend();
      show();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(
          "This computer couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again."
        );
    });
  });
  describe('every Try again is the same button, saying “Trying…” while it tries (cabledrawer 18 Oct)', () => {
    const isShared = (name: string) => {
      const el = page.getByRole('button', { name, exact: true }).element();
      return el.classList.contains('primary') && !el.classList.contains('quiet');
    };

    it('couldn’t finish signing out', async () => {
      signOutState.unfinished = true;
      show();
      await expect.element(page.getByRole('button', { name: 'Try again' })).toBeVisible();
      expect(isShared('Try again')).toBe(true);
      let answer: (reply: Response) => void = () => {};
      vi.stubGlobal('fetch', () => new Promise<Response>((done) => (answer = done)));
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByRole('button', { name: 'Trying…' })).toBeDisabled();
      answer(new Response(null, { status: 204 }));
      await expect.element(page.getByText(/Couldn't finish signing out/)).not.toBeInTheDocument();
      expect(page.getByRole('button', { name: /^Try/ }).elements()).toEqual([]);
      vi.unstubAllGlobals();
    });

    it('a wipe that couldn’t delete the phone database', async () => {
      await wrensPhone(1);
      const mend = failPhoneDelete();
      await wipeDevice();
      mend();
      show();
      await expect.element(page.getByRole('button', { name: 'Try again' })).toBeVisible();
      expect(isShared('Try again')).toBe(true);
      // Another tab holds the queue lock, so the wipe waits.
      let release = () => {};
      const held = new Promise<void>((done) => (release = done));
      let locked = () => {};
      const lockTaken = new Promise<void>((done) => (locked = done));
      void navigator.locks.request(`${phoneDatabaseName()}.queue`, () => {
        locked();
        return held;
      });
      await lockTaken;
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByRole('button', { name: 'Trying…' })).toBeDisabled();
      release();
      await expect.element(page.getByText(/couldn't delete/)).not.toBeInTheDocument();
      expect(page.getByRole('button', { name: /^Try/ }).elements()).toEqual([]);
      expect(await phoneThere()).toBe(false);
    });

    it('couldn’t check for changes waiting', async () => {
      await wrensPhone(1);
      const mend = breakPhone();
      show();
      await fillIn('arlo');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await expect.element(page.getByRole('button', { name: 'Try again' })).toBeVisible();
      expect(isShared('Try again')).toBe(true);
      const release = holdDatabaseList();
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByRole('button', { name: 'Trying…' })).toBeDisabled();
      release();
      await expect.element(page.getByRole('button', { name: 'Try again' })).toBeEnabled();
      await expect.element(page.getByRole('alert')).toHaveTextContent(CANT_TEXT);
      mend();
      expect(requests).toEqual([]);
    });
  });
});
