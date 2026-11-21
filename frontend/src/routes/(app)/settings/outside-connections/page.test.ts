// Settings › Outside connections (0.5 PR 4): the switches and "Your own network", for an admin, for a
// member, and when the server can't be reached.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { OwnNetworkEntry, OwnNetworkList, PrivacySwitches } from '#lib/client/privacy.js';
import type { Change, UndoResult } from '#lib/client/types.js';
import { network } from '#lib/network.svelte.js';
import { privacy } from '#lib/privacy.svelte.js';
import { session } from '#lib/session.svelte.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Privacy from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const entry = (
  id: number,
  kind: OwnNetworkEntry['kind'],
  value: string,
  extra: Partial<OwnNetworkEntry> = {}
): OwnNetworkEntry => ({
  id,
  kind,
  value,
  addresses: null,
  added_by: 'Tess',
  added_on: '2026-10-22',
  ...extra
});

/** A change the server made (D4, BE5: each is in Recent changes, with the server's Undo). */
const change = (id: number, kind: string, summary: string): Change => ({
  id,
  kind,
  at: '2026-11-20T10:00:00Z',
  who: { login_id: 1, name: 'Tess' },
  summary,
  can_undo: true,
  undo_until: '2026-11-27T10:00:00Z',
  undone: null
});

/** The server's answer to Undo of that change. */
const undone = (of: Change, notice: string | null = null): [number, UndoResult] => [
  200,
  {
    result: 'done',
    message: 'Undone',
    change: change(of.id + 100, 'undo', `Undid: ${of.summary}`),
    undone: of,
    food: null,
    brought_back: [],
    notice
  }
];

const wiki = entry(1, 'name', 'wiki.home.example');
const lan = entry(2, 'range', '192.168.1.0/24', { addresses: 256 });

const switches = (a: boolean, b: boolean, can = true): [number, PrivacySwitches] => [
  200,
  {
    switches: [
      { connection: 'recipe_import', on: a },
      { connection: 'recipe_photos', on: b }
    ],
    can_change: can
  }
];

const list = (entries: OwnNetworkEntry[], can = true): [number, OwnNetworkList] => [
  200,
  { entries, limit: 100, can_change: can }
];

const IMPORT = 'Recipe import from links';
const PHOTOS = 'Download recipe photos';
const MEMBER_NOTE =
  'Only an admin can change these, because they decide what Mealwright may contact.';
const OFFLINE_NOTE =
  'You’re offline. This is as it was when you last looked, and it can’t be changed until you’re back online.';

describe('Settings › Outside connections', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(routes: Parameters<typeof fakeApi>[0] = {}) {
    requests = fakeApi({
      'GET /privacy/switches': switches(false, false),
      'GET /privacy/own-network': list([]),
      ...routes
    });
    component = mount(Privacy, { target: document.body });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
    privacy.forget();
    undoHistory.clear();
    toasts.dismiss();
    session.me = { ...ME, role: 'admin' }; // a Household page: an admin's (D4, BE12)
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    privacy.forget();
    undoHistory.clear();
    toasts.dismiss();
    session.me = null;
  });

  const sent = (method: string, path: string) =>
    requests.filter((r) => r.method === method && r.path === path);

  it('shows both switches off to start, and an empty list', async () => {
    open();
    await expect
      .element(page.getByRole('heading', { name: 'Outside connections', level: 1 }))
      .toBeVisible();
    await expect
      .element(
        page.getByText(
          'Nothing leaves this server unless you switch it on, or press Check now in About.'
        )
      )
      .toBeVisible();
    await expect.element(page.getByRole('switch', { name: IMPORT })).not.toBeChecked();
    await expect.element(page.getByRole('switch', { name: PHOTOS })).not.toBeChecked();
    await expect
      .element(page.getByText('Nothing added yet. Every address on your own network is blocked.'))
      .toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Add', exact: true })).toBeVisible();
  });

  it('lines up: switch rows not indented, headings level, the banner as wide as the cards (F75)', async () => {
    await page.viewport(1300, 900);
    open({ 'GET /privacy/own-network': list([wiki, lan]) });
    await expect.element(page.getByRole('switch', { name: IMPORT })).toBeVisible();
    const box = (el: Element) => el.getBoundingClientRect();
    const outside = page.getByRole('heading', { name: 'Outside connections', level: 2 }).element();
    const own = page.getByRole('heading', { name: 'Your own network' }).element();
    // The two headings are level: the pill beside the second doesn't push it down.
    expect(
      Math.abs(box(outside).y + box(outside).height / 2 - (box(own).y + box(own).height / 2))
    ).toBeLessThanOrEqual(1);
    // The first switch row's words start one card padding in, with no empty space before them.
    const card = outside.parentElement!.querySelector('.card')!;
    const words = card.querySelector('li .words')!;
    expect(box(words).left - box(card).left).toBeLessThanOrEqual(24);
    const listed = page.getByRole('list', { name: 'Allowed on your own network' }).element();
    const ownCard = listed.closest('.card')!;
    expect(box(listed.querySelector('li')!).left - box(ownCard).left).toBeLessThanOrEqual(24);
    // The banner is as wide as the two cards together.
    const banner = page
      .getByText('Nothing leaves this server unless you switch it on, or press Check now in About.')
      .element();
    expect(Math.abs(box(banner).right - box(ownCard).right)).toBeLessThanOrEqual(1);
    expect(Math.abs(box(banner).left - box(card).left)).toBeLessThanOrEqual(1);
  });

  it('copes with a link whose # part is not valid text', async () => {
    // Without the fix, the jump throws inside the page's load: an unhandled rejection.
    const unhandled: unknown[] = [];
    const heard = (event: PromiseRejectionEvent) => {
      event.preventDefault();
      unhandled.push(event.reason);
    };
    window.addEventListener('unhandledrejection', heard);
    history.replaceState(null, '', '#%E0');
    try {
      open();
      await expect.element(page.getByRole('switch', { name: IMPORT })).toBeVisible();
      await new Promise((done) => setTimeout(done, 100)); // the jump runs after the load
      expect(unhandled).toEqual([]);
      // The page is still all there.
      await expect.element(page.getByRole('button', { name: 'Add', exact: true })).toBeVisible();
    } finally {
      window.removeEventListener('unhandledrejection', heard);
      history.replaceState(null, '', location.pathname + location.search);
    }
  });

  it('names what is always blocked, link-local included (cabledrawer 23 Oct, question 26)', async () => {
    open();
    await expect.element(page.getByRole('switch', { name: IMPORT })).toBeVisible();
    const note = document.querySelector('.blocked');
    expect(note?.textContent).toBe(
      'Always blocked, even if listed: this server itself (localhost), link-local and cloud “metadata” addresses.'
    );
  });

  it('has the two places the import screen links to', async () => {
    open();
    await expect.element(page.getByRole('switch', { name: IMPORT })).toBeVisible();
    const outside = document.getElementById('outside-connections');
    expect(outside?.textContent).toBe('Outside connections');
    expect(outside?.tagName).toBe('H2');
    expect(document.getElementById('your-own-network')?.textContent).toBe('Your own network');
  });

  it('is loading, then shows what the server says', async () => {
    let answer: (value: Response) => void = () => {};
    vi.stubGlobal(
      'fetch',
      (input: string) =>
        new Promise<Response>((done) => {
          const reply = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
          if (String(input).endsWith('/privacy/switches')) answer = done;
          else done(reply({ entries: [], limit: 100, can_change: true }));
        })
    );
    component = mount(Privacy, { target: document.body });
    flushSync();
    await expect.element(page.getByText('Loading…')).toBeVisible();
    expect(document.querySelector('[role="switch"]')).toBeNull();
    answer(new Response(JSON.stringify(switches(true, false)[1]), { status: 200 }));
    await expect.element(page.getByRole('switch', { name: IMPORT })).toBeChecked();
    await expect.element(page.getByRole('switch', { name: PHOTOS })).not.toBeChecked();
  });

  it('says so when it can’t be loaded, and Try again looks again', async () => {
    let tries = 0;
    open({
      'GET /privacy/switches': () =>
        ++tries === 1 ? [500, { detail: 'Broke.' }] : switches(true, true)
    });
    await expect.element(page.getByRole('alert')).toHaveTextContent('Broke. Try again');
    expect(document.querySelector('[role="switch"]')).toBeNull();
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect.element(page.getByRole('switch', { name: IMPORT })).toBeChecked();
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });

  describe('as an admin', () => {
    it('turns a switch on at once and sends it', async () => {
      open({
        'PUT /privacy/switches/recipe_import': switches(true, false)
      });
      const toggle = page.getByRole('switch', { name: IMPORT });
      await expect.element(toggle).not.toBeChecked();
      await toggle.click();
      await expect.element(toggle).toBeChecked();
      await vi.waitFor(() =>
        expect(sent('PUT', '/privacy/switches/recipe_import')).toHaveLength(1)
      );
      expect(sent('PUT', '/privacy/switches/recipe_import')[0]!.body).toEqual({ on: true });
      // The other switch is its own.
      await expect.element(page.getByRole('switch', { name: PHOTOS })).not.toBeChecked();
      expect(sent('PUT', '/privacy/switches/recipe_photos')).toHaveLength(0);
    });

    it('offers the server’s Undo for a switch, which turns it back off (D4, BE5)', async () => {
      const made = change(34, 'connection_changed', 'Switched recipe import on');
      let on = false;
      open({
        'GET /privacy/switches': () => switches(on, false),
        'PUT /privacy/switches/recipe_import': () => {
          on = true;
          return [200, { ...switches(true, false)[1], change: made }];
        },
        'POST /changes/34/undo': () => {
          on = false;
          return undone(made);
        }
      });
      const toggle = page.getByRole('switch', { name: IMPORT });
      await toggle.click();
      await expect.element(toggle).toBeChecked();
      await vi.waitFor(() => expect(toasts.current?.message).toBe('Switched recipe import on'));
      expect(toasts.current?.action?.label).toBe('Undo');
      toasts.act();
      await expect.element(toggle).not.toBeChecked();
      expect(sent('POST', '/changes/34/undo')).toHaveLength(1);
      expect(sent('PUT', '/privacy/switches/recipe_import')).toHaveLength(1);
    });

    it('the Undo of switching one off shows the server’s sentence and leaves it off (Low 2)', async () => {
      const made = change(35, 'connection_changed', 'Switched recipe import off');
      const SAYS = 'Switch it on in Settings › Outside connections.';
      let on = true;
      open({
        'GET /privacy/switches': () => switches(on, false),
        'PUT /privacy/switches/recipe_import': () => {
          on = false;
          return [200, { ...switches(false, false)[1], change: made }];
        },
        'POST /changes/35/undo': [409, { code: 'cannot_undo', detail: SAYS }]
      });
      const toggle = page.getByRole('switch', { name: IMPORT });
      await expect.element(toggle).toBeChecked();
      await toggle.click();
      await expect.element(toggle).not.toBeChecked();
      await vi.waitFor(() => expect(toasts.current?.message).toBe('Switched recipe import off'));
      toasts.act();
      await vi.waitFor(() => expect(toasts.current?.message).toBe(SAYS));
      expect(sent('POST', '/changes/35/undo')).toHaveLength(1);
      expect(sent('PUT', '/privacy/switches/recipe_import')).toHaveLength(1);
      await expect.element(toggle).not.toBeChecked();
    });

    it('offers no Undo when the switch was already as asked', async () => {
      open({
        'PUT /privacy/switches/recipe_import': [200, { ...switches(true, false)[1], change: null }]
      });
      await page.getByRole('switch', { name: IMPORT }).click();
      await vi.waitFor(() =>
        expect(sent('PUT', '/privacy/switches/recipe_import')).toHaveLength(1)
      );
      await new Promise((done) => setTimeout(done, 50));
      expect(toasts.current).toBeNull();
    });

    it('turns the daily update check on, with its own words (X1)', async () => {
      open({
        'PUT /privacy/switches/update_check': [
          200,
          {
            switches: [
              ...switches(false, false)[1].switches,
              { connection: 'update_check', on: true }
            ],
            can_change: true
          }
        ]
      });
      const toggle = page.getByRole('switch', { name: 'Check for updates daily' });
      await expect.element(toggle).not.toBeChecked();
      await expect
        .element(
          page.getByText(
            'Asks GitHub’s public release list once a day. Sends nothing about you or this server'
          )
        )
        .toBeVisible();
      await toggle.click();
      await expect.element(toggle).toBeChecked();
      await vi.waitFor(() => expect(sent('PUT', '/privacy/switches/update_check')).toHaveLength(1));
      expect(sent('PUT', '/privacy/switches/update_check')[0]!.body).toEqual({ on: true });
      expect(sent('PUT', '/privacy/switches/recipe_import')).toHaveLength(0);
    });

    it('turns it back off', async () => {
      open({
        'GET /privacy/switches': switches(false, true),
        'PUT /privacy/switches/recipe_photos': switches(false, false)
      });
      const toggle = page.getByRole('switch', { name: PHOTOS });
      await expect.element(toggle).toBeChecked();
      await toggle.click();
      await expect.element(toggle).not.toBeChecked();
      await vi.waitFor(() =>
        expect(sent('PUT', '/privacy/switches/recipe_photos')).toHaveLength(1)
      );
      expect(sent('PUT', '/privacy/switches/recipe_photos')[0]!.body).toEqual({ on: false });
    });

    it('puts a switch back, and says why, when the server refuses', async () => {
      open({
        'PUT /privacy/switches/recipe_import': [
          403,
          { detail: 'Only the household’s admin can change this.', code: 'admins_only' }
        ]
      });
      const toggle = page.getByRole('switch', { name: IMPORT });
      await toggle.click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('Only the household’s admin can change this.');
      await expect.element(toggle).not.toBeChecked();
    });

    it('says “You’d be locked out” and keeps single sign-on on for the last admin with only a link', async () => {
      const LOCKED = 'You’d be locked out: first add another admin who signs in with a password.';
      open({
        'GET /privacy/switches': [
          200,
          { switches: [{ connection: 'single_sign_on', on: true }], can_change: true }
        ],
        'PUT /privacy/switches/single_sign_on': [409, { detail: LOCKED, code: 'locked_out' }]
      });
      const toggle = page.getByRole('switch', { name: 'Single sign-on' });
      await expect.element(toggle).toBeChecked();
      await toggle.click();
      await expect.element(page.getByRole('alert')).toHaveTextContent(LOCKED);
      await expect.element(toggle).toBeChecked();
    });

    it('puts a switch back when the server can’t be reached', async () => {
      open();
      const toggle = page.getByRole('switch', { name: PHOTOS });
      await expect.element(toggle).toBeVisible();
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      await toggle.click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('Can’t reach your Mealwright server. Nothing was changed.');
      await expect.element(toggle).not.toBeChecked();
    });

    it('the help line and the example say “for example”, with no word about later features', async () => {
      open({ 'GET /privacy/own-network': list([]) });
      await expect
        .element(
          page.getByText('Each entry is a name, one address, or a range like 192.168.1.0/24.', {
            exact: true
          })
        )
        .toBeVisible();
      await expect
        .element(page.getByPlaceholder('for example wiki.home.lan or 192.168.1.20'))
        .toBeVisible();
      expect(document.body.textContent).not.toContain('single sign-on');
    });

    it('lists what is on it, in plain words', async () => {
      open({
        'GET /privacy/own-network': list([
          wiki,
          lan,
          entry(3, 'address', '192.168.1.20', { added_by: '' })
        ])
      });
      const items = page.getByRole('list', { name: 'Allowed on your own network' });
      await expect.element(items).toBeVisible();
      await expect.element(page.getByText('wiki.home.example')).toBeVisible();
      await expect.element(page.getByText('A name · added by Tess, 22 Oct')).toBeVisible();
      await expect.element(page.getByText('192.168.1.0/24')).toBeVisible();
      await expect
        .element(page.getByText('A range · 256 addresses · added by Tess, 22 Oct'))
        .toBeVisible();
      await expect.element(page.getByText('An address · added 22 Oct')).toBeVisible();
      expect(document.body.textContent).not.toContain('Nothing added yet');
      await expect
        .element(page.getByRole('button', { name: 'Remove wiki.home.example' }))
        .toBeVisible();
    });

    it('adds a name, clears the box, and offers the server’s Undo', async () => {
      const made = change(31, 'own_network_added', 'Added nas.home.example to Your own network');
      let entries: OwnNetworkEntry[] = [];
      open({
        'GET /privacy/own-network': () => list(entries),
        'POST /privacy/own-network': (request) => {
          const added = entry(5, 'name', (request.body as { value: string }).value.toLowerCase());
          entries = [added];
          return [201, { ...added, change: made }];
        },
        'POST /changes/31/undo': () => {
          entries = [];
          return undone(made);
        }
      });
      const box = page.getByRole('textbox', { name: 'Add a name or address' });
      await box.fill('Nas.Home.Example');
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await expect.element(page.getByText('nas.home.example', { exact: true })).toBeVisible();
      await expect.element(box).toHaveValue('');
      expect(sent('POST', '/privacy/own-network')[0]!.body).toEqual({ value: 'Nas.Home.Example' });
      expect(toasts.current?.message).toBe('Added nas.home.example to Your own network');
      expect(toasts.current?.action?.label).toBe('Undo');
      toasts.act();
      await expect
        .element(page.getByText('nas.home.example', { exact: true }))
        .not.toBeInTheDocument();
      // The Undo is the server's (it is in Recent changes); nothing is taken off by hand.
      expect(sent('POST', '/changes/31/undo')).toHaveLength(1);
      expect(sent('DELETE', '/privacy/own-network/5')).toHaveLength(0);
    });

    it('adds with Enter too', async () => {
      open({ 'POST /privacy/own-network': [201, entry(5, 'address', '192.168.1.20')] });
      await page.getByRole('textbox', { name: 'Add a name or address' }).fill('192.168.1.20');
      await page.getByRole('textbox', { name: 'Add a name or address' }).click();
      await userEvent.keyboard('{Enter}');
      await expect.element(page.getByText('192.168.1.20', { exact: true })).toBeVisible();
    });

    it.each([
      [
        422,
        'bad_entry',
        'Type a name (wiki.home.example), an address (192.168.1.20) or a range (192.168.1.0/24).'
      ],
      [
        422,
        'always_blocked',
        'That can’t be added: this server itself (localhost), link-local and cloud “metadata” addresses are always blocked.'
      ],
      [422, 'too_wide', 'That range is too wide. Add a smaller one, like 192.168.1.0/24.'],
      [409, 'already_there', 'That’s already on the list.'],
      [409, 'too_many_entries', 'The list is full: it holds up to 100 entries. Remove one first.']
    ])(
      'shows the server’s own sentence for %i %s and keeps what was typed',
      async (status, code, detail) => {
        open({ 'POST /privacy/own-network': [status, { detail, code }] });
        const box = page.getByRole('textbox', { name: 'Add a name or address' });
        await box.fill('something');
        await page.getByRole('button', { name: 'Add', exact: true }).click();
        await expect.element(page.getByRole('alert')).toHaveTextContent(detail);
        await expect.element(box).toHaveValue('something');
        await expect.element(box).toHaveAttribute('aria-invalid', 'true');
        expect(document.querySelectorAll('li')).toHaveLength(4); // only the four switches
      }
    );

    it('says so when taking the sign-in server off turned password sign-in back on', async () => {
      const notice =
        'Removed. Passwords work again for now, because single sign-on can’t start without that entry: your sign-in server is no longer on Your own network. Add it back and passwords are off again.';
      open({
        'GET /privacy/own-network': list([wiki, lan]),
        'DELETE /privacy/own-network/1': [200, { passwords_back_on: true, notice }]
      });
      await page.getByRole('button', { name: 'Remove wiki.home.example' }).click();
      await expect.element(page.getByRole('status').filter({ hasText: notice })).toBeVisible();
      // The next change clears it.
      await page.getByRole('button', { name: 'Remove 192.168.1.0/24' }).click();
      await expect.element(page.getByText(notice)).not.toBeInTheDocument();
    });

    it('takes an entry off at once; its Undo is the server’s, which won’t put it back (Low 2)', async () => {
      const made = change(
        32,
        'own_network_removed',
        'Removed wiki.home.example from Your own network'
      );
      const SAYS = 'Add it again in Settings › Outside connections.';
      let entries = [wiki, lan];
      open({
        'GET /privacy/own-network': () => list(entries),
        'DELETE /privacy/own-network/1': () => {
          entries = [lan];
          return [200, { passwords_back_on: false, notice: null, change: made }];
        },
        'POST /changes/32/undo': [409, { code: 'cannot_undo', detail: SAYS }]
      });
      await page.getByRole('button', { name: 'Remove wiki.home.example' }).click();
      await expect
        .element(page.getByText('wiki.home.example', { exact: true }))
        .not.toBeInTheDocument();
      await expect.element(page.getByText('192.168.1.0/24')).toBeVisible();
      expect(sent('DELETE', '/privacy/own-network/1')).toHaveLength(1);
      expect(toasts.current?.message).toBe('Removed wiki.home.example from Your own network');
      toasts.act();
      await vi.waitFor(() => expect(toasts.current?.message).toBe(SAYS));
      expect(sent('POST', '/changes/32/undo')).toHaveLength(1);
      expect(sent('POST', '/privacy/own-network')).toHaveLength(0);
      await expect
        .element(page.getByText('wiki.home.example', { exact: true }))
        .not.toBeInTheDocument();
      expect(privacy.entries.map((e) => e.id)).toEqual([2]);
    });

    it('puts an entry back, and says why, when it couldn’t be taken off', async () => {
      open({
        'GET /privacy/own-network': list([wiki, lan]),
        'DELETE /privacy/own-network/1': [500, { detail: 'Broke.' }]
      });
      await page.getByRole('button', { name: 'Remove wiki.home.example' }).click();
      await expect.element(page.getByRole('alert')).toHaveTextContent('Broke.');
      const names = [...document.querySelectorAll('li .value')].map((n) => n.textContent);
      expect(names).toEqual(['wiki.home.example', '192.168.1.0/24']);
      expect(toasts.current).toBeNull();
    });

    it('keeps the entry and says “You’d be locked out” when it is what single sign-on needs', async () => {
      const LOCKED = 'You’d be locked out: first add another admin who signs in with a password.';
      open({
        'GET /privacy/own-network': list([wiki, lan]),
        'DELETE /privacy/own-network/1': [409, { detail: LOCKED, code: 'locked_out' }]
      });
      await page.getByRole('button', { name: 'Remove wiki.home.example' }).click();
      await expect.element(page.getByRole('alert')).toHaveTextContent(LOCKED);
      const names = [...document.querySelectorAll('li .value')].map((n) => n.textContent);
      expect(names).toEqual(['wiki.home.example', '192.168.1.0/24']);
    });

    it('keeps one row per entry when a load brings in what was just added', async () => {
      const five = entry(5, 'name', 'nas.home.example');
      open({
        'POST /privacy/own-network': () => {
          privacy.entries = [five]; // a load() answered while the add was on its way
          return [201, five];
        }
      });
      await page.getByRole('textbox', { name: 'Add a name or address' }).fill('nas.home.example');
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await expect.element(page.getByText('nas.home.example', { exact: true })).toBeVisible();
      expect(privacy.entries.map((e) => e.id)).toEqual([5]);
      expect(document.querySelectorAll('li .value')).toHaveLength(1);
    });

    it('says so when the Undo of adding the sign-in server turned passwords back on', async () => {
      const notice =
        'Removed. Passwords work again for now, because single sign-on can’t start without that entry: your sign-in server is no longer on Your own network. Add it back and passwords are off again.';
      const made = change(33, 'own_network_added', 'Added sso.home.example to Your own network');
      let entries: OwnNetworkEntry[] = [];
      open({
        'GET /privacy/own-network': () => list(entries),
        'POST /privacy/own-network': () => {
          entries = [entry(6, 'name', 'sso.home.example')];
          return [201, { ...entries[0]!, change: made }];
        },
        'POST /changes/33/undo': () => {
          entries = [];
          return undone(made, notice);
        }
      });
      await page.getByRole('textbox', { name: 'Add a name or address' }).fill('sso.home.example');
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await expect.element(page.getByText('sso.home.example', { exact: true })).toBeVisible();
      toasts.act();
      await expect.element(page.getByRole('status').filter({ hasText: notice })).toBeVisible();
      await vi.waitFor(() => expect(toasts.current?.message).toBe(notice));
    });

    it('lets an entry that is already gone go quietly', async () => {
      open({
        'GET /privacy/own-network': list([wiki]),
        'DELETE /privacy/own-network/1': [
          404,
          { detail: 'That entry isn’t here any more.', code: 'not_found' }
        ]
      });
      await page.getByRole('button', { name: 'Remove wiki.home.example' }).click();
      await expect
        .element(page.getByText('wiki.home.example', { exact: true }))
        .not.toBeInTheDocument();
      expect(document.querySelector('[role="alert"]')).toBeNull();
    });
  });

  // A member never opens this page (D4, BE12): what an admin sees when the server says no.
  describe('when the server says they can’t be changed', () => {
    it('shows the switches and the list, and can change neither', async () => {
      open({
        'GET /privacy/switches': switches(true, false, false),
        'GET /privacy/own-network': list([wiki, lan], false)
      });
      const toggle = page.getByRole('switch', { name: IMPORT });
      await expect.element(toggle).toBeChecked();
      await expect.element(toggle).toBeDisabled();
      await expect.element(page.getByRole('switch', { name: PHOTOS })).toBeDisabled();
      await expect.element(page.getByText(MEMBER_NOTE).first()).toBeVisible();
      await expect.element(page.getByText('wiki.home.example')).toBeVisible();
      expect(document.querySelector('button.remove')).toBeNull();
      expect(document.querySelector('form')).toBeNull();
      expect(page.getByRole('button', { name: 'Add', exact: true }).elements()).toHaveLength(0);
    });

    it('never sends a change', async () => {
      open({
        'GET /privacy/switches': switches(false, false, false),
        'GET /privacy/own-network': list([], false)
      });
      const toggle = page.getByRole('switch', { name: IMPORT });
      await expect.element(toggle).toBeDisabled();
      await toggle.click({ force: true }).catch(() => {});
      await privacy.setSwitch('recipe_import', true);
      expect(requests.filter((r) => r.method !== 'GET')).toEqual([]);
      await expect.element(toggle).not.toBeChecked();
    });
  });

  describe('offline', () => {
    it('shows what was last loaded and can’t be changed, and says why', async () => {
      open({
        'GET /privacy/switches': switches(true, false),
        'GET /privacy/own-network': list([wiki])
      });
      await expect.element(page.getByRole('switch', { name: IMPORT })).toBeChecked();
      network.offline = true;
      network.deviceOffline = true;
      await expect.element(page.getByText(OFFLINE_NOTE).first()).toBeVisible();
      await expect.element(page.getByRole('switch', { name: IMPORT })).toBeChecked();
      await expect.element(page.getByRole('switch', { name: IMPORT })).toBeDisabled();
      await expect.element(page.getByText('wiki.home.example')).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Remove wiki.home.example' }))
        .toBeDisabled();
      await expect
        .element(page.getByRole('textbox', { name: 'Add a name or address' }))
        .toBeDisabled();
      await expect.element(page.getByRole('button', { name: 'Add', exact: true })).toBeDisabled();
      // Back online: the same page, changeable again.
      network.offline = false;
      await expect.element(page.getByRole('switch', { name: IMPORT })).toBeEnabled();
    });

    it('says the page needs the server when nothing was ever loaded', async () => {
      network.offline = true;
      network.deviceOffline = true;
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      component = mount(Privacy, { target: document.body });
      flushSync();
      await expect
        .element(page.getByText(/Outside connections needs your Mealwright server\./))
        .toBeVisible();
      expect(document.querySelector('[role="switch"]')).toBeNull();
    });

    it('looks again when the connection comes back', async () => {
      open({ 'GET /privacy/switches': switches(false, false) });
      await expect.element(page.getByRole('switch', { name: IMPORT })).not.toBeChecked();
      fakeApi({
        'GET /privacy/switches': switches(true, false),
        'GET /privacy/own-network': list([wiki])
      });
      network.backAgain++;
      await expect.element(page.getByRole('switch', { name: IMPORT })).toBeChecked();
      await expect.element(page.getByText('wiki.home.example')).toBeVisible();
    });
  });

  it('forgets everything when signing out, so the next login starts empty', async () => {
    open({
      'GET /privacy/switches': switches(true, true),
      'GET /privacy/own-network': list([wiki])
    });
    await expect.element(page.getByRole('switch', { name: IMPORT })).toBeChecked();
    privacy.forget();
    expect(privacy.loaded).toBe(false);
    expect(privacy.switches).toEqual({
      recipe_import: false,
      recipe_photos: false,
      single_sign_on: false,
      update_check: false
    });
    expect(privacy.entries).toEqual([]);
    expect(privacy.canChange).toBe(false);
  });
});
