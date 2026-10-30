import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import NewIngredient from '#lib/components/NewIngredient.svelte';
import Toast from '#lib/components/Toast.svelte';
import { ME, fakeShopping, sampleCopy, tick } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { loadDeviceId } from '#lib/offline/device.js';
import { addToQueue, readQueue, saveCopy } from '#lib/offline/store.js';
import { applyChanges } from '#lib/shopping/load.js';
import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
import { session } from '#lib/session.svelte.js';
import { network, offlineText } from '#lib/network.svelte.js';
import { newIngredient } from '#lib/newIngredient.svelte.js';
import type { ShoppingCopy } from '#lib/shopping/types.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import { notHereText } from '#lib/shopping/store.svelte.js';
import Shopping from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

describe('the Shopping page', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let copy: ShoppingCopy;
  let server: ReturnType<typeof fakeShopping>;

  function mountShopping() {
    for (const component of [Shopping, Toast, NewIngredient]) {
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(component, { target }));
    }
    flushSync();
  }

  async function render(width: number, extra: Parameters<typeof fakeShopping>[1] = {}) {
    server = fakeShopping(copy, extra);
    await page.viewport(width, 1000);
    mountShopping();
    await expect.element(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
  }

  const row = (id: string) => copy.items.find((i) => i.id === id);

  /** A ticked row's "Change" opens the places and "Different pack?". */
  async function openChange(name: string) {
    await page.getByRole('button', { name: `Change where ${name} went` }).click();
  }

  beforeEach(() => {
    freshPhone();
    copy = sampleCopy();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
    newIngredient.cancel();
  });

  afterEach(async () => {
    ingredientEditor.close();
    network.reset();
    await dropPhone();
    newIngredient.cancel();
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('splits by shop and aisle with the spec’s names, Any shop last', async () => {
    await render(1300);
    const headings = page
      .getByRole('heading', { level: 2 })
      .elements()
      .map((h) => h.textContent);
    expect(headings.indexOf('Supermarket')).toBeLessThan(headings.indexOf('Indian grocer'));
    expect(headings.indexOf('Indian grocer')).toBeLessThan(headings.indexOf('Any shop'));
    const aisles = page
      .getByRole('heading', { level: 3 })
      .elements()
      .map((h) => h.textContent);
    expect(aisles).toEqual(['Veg & fruit', 'Dairy', 'Dry goods', 'Household']);
    expect(document.body.textContent).not.toContain('Fruit & veg');
    expect(document.body.textContent).not.toContain('Rice & grains');
  });

  it('says what it is synced with', async () => {
    await render(1300);
    await expect.element(page.getByText('4 to buy · synced with Wren')).toBeVisible();
  });

  it('folds ticked items into In the trolley, with Different pack? and the place', async () => {
    await render(1300);
    const fold = page.getByRole('button', { name: 'In the trolley · 2' });
    await expect.element(fold).toHaveAttribute('aria-expanded', 'false');
    await fold.click();
    await expect.element(page.getByText('In the Fridge · 2 packs')).toBeVisible();
    await expect.element(page.getByText('In the Fridge · 1 bunch')).toBeVisible();
    expect(document.body.textContent).not.toContain('→ Fridge');
    await openChange('Paneer');
    await expect.element(page.getByRole('button', { name: 'Different pack?' })).toBeVisible();
    await expect.element(page.getByRole('radio', { name: 'Fridge' })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Clear ticked' })).toBeVisible();
  });

  it('Clear ticked sends the items shown, and offers Undo', async () => {
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 2' }).click();
    await page.getByRole('button', { name: 'Clear ticked' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'clear_ticked', list_id: 'main' })
    );
    expect((server.actions.at(-1)!.item_ids as string[]).sort()).toEqual([
      'i-coriander',
      'i-paneer'
    ]);
    await expect.element(page.getByRole('button', { name: 'Undo' })).toBeVisible();
  });

  it('phone: ticking sends a tick and the toast says where it went, with Change and Undo', async () => {
    await render(390);
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    // Stored on the phone first, then sent.
    const sent = await vi.waitFor(() => {
      const found = server.requests.find((r) => r.path === '/shopping/actions');
      if (!found) throw new Error('not sent yet');
      return found;
    });
    const body = sent.body as { protocol: number; actions: { kind: string; item_id: string }[] };
    expect(body.protocol).toBe(1);
    expect(body.actions[0]).toMatchObject({ kind: 'tick', item_id: 'i-onions' });
    const toast = page.getByRole('status').filter({ hasText: 'Onions → Fridge' });
    await expect.element(toast).toBeVisible();
    await expect.element(toast.getByRole('button', { name: 'Change' })).toBeVisible();
    await toast.getByRole('button', { name: 'Undo' }).click();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'Undone: Onions → Fridge' }))
      .toBeVisible();
    await vi.waitFor(() => expect(server.actions.map((a) => a.kind)).toEqual(['tick', 'undo']));
    expect(server.actions[1]!.undoes).toBe(server.actions[0]!.id);
  });

  it('11.2: a tick shows at once and stays while the server can’t be reached', async () => {
    let tries = 0;
    await render(1300, {
      'POST /shopping/actions': () => {
        tries++;
        return [503, { detail: 'Down for a moment' }];
      }
    });
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    await expect.element(page.getByRole('button', { name: 'In the trolley · 3' })).toBeVisible();
    await vi.waitFor(() => expect(tries).toBe(1));
    // Not sent, so not gone: still ticked, and no "Couldn't save".
    await expect.element(page.getByRole('button', { name: 'In the trolley · 3' })).toBeVisible();
    expect(toasts.current?.tone).not.toBe('problem');
  });

  async function openOffline(width: number, change: (copy: ShoppingCopy) => void = () => {}) {
    const here = sampleCopy();
    change(here);
    await saveCopy(null, applyChanges(null, { ...here, people: [], reset: true }));
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await page.viewport(width, 1000);
    mountShopping();
    await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
  }

  it('offline: a tick shows its toast with Change and Undo at once, and Undo is queued after it', async () => {
    await openOffline(390);
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    // Onions has no usual place, so where it goes isn't known until the server says.
    const toast = page.getByRole('status').filter({ hasText: 'Onions ticked' });
    await expect.element(toast).toBeVisible();
    await expect.element(toast.getByRole('button', { name: 'Change' })).toBeVisible();
    await toast.getByRole('button', { name: 'Undo' }).click();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'Undone: Onions ticked' }))
      .toBeVisible();
    const queue = (await readQueue()).map((e) => e.action);
    expect(queue.map((a) => a.kind)).toEqual(['tick', 'undo']);
    expect(queue[1]).toMatchObject({ undoes: queue[0]!.id });
    // Taken back on the screen too.
    await expect.element(page.getByRole('checkbox', { name: 'Tick Onions' })).not.toBeChecked();
  });

  it('offline, desktop: the Put away panel shows the tick at once, at its usual place, and Undo last tick works', async () => {
    // Yoghurt lives in the Fridge.
    await openOffline(1300, (here) => (here.foods[2]!.place_id = 1));
    await page.getByRole('checkbox', { name: 'Tick Yoghurt' }).click();
    const where = page.getByRole('combobox', { name: 'Where' });
    await expect.element(where).toBeVisible();
    await expect.element(where).toHaveValue('1');
    await page.getByRole('button', { name: 'Undo last tick' }).click();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'Undone: Yoghurt → Fridge' }))
      .toBeVisible();
    expect((await readQueue()).map((e) => e.action.kind)).toEqual(['tick', 'undo']);
  });

  it('offline: Remove asks, the row goes at once, and Undo brings it back with its amount, queued after the delete', async () => {
    await openOffline(390);
    await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
    await page.getByRole('button', { name: 'Remove from list' }).click();
    await page
      .getByRole('alertdialog', { name: 'Remove Yoghurt from the shopping list?' })
      .getByRole('button', { name: 'Remove', exact: true })
      .click();
    const toast = page.getByRole('status').filter({ hasText: 'Removed Yoghurt' });
    await expect.element(toast).toBeVisible();
    await expect
      .element(page.getByRole('checkbox', { name: 'Tick Yoghurt' }))
      .not.toBeInTheDocument();
    await toast.getByRole('button', { name: 'Undo' }).click();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'Undone: Removed Yoghurt' }))
      .toBeVisible();
    // Back on the list with its amount, from the phone's own copy.
    await expect.element(page.getByRole('checkbox', { name: 'Tick Yoghurt' })).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: 'Change amount: Yoghurt, 500 g' }))
      .toBeVisible();
    // The queue holds the delete, then the undo that matches it.
    const queue = (await readQueue()).map((e) => e.action);
    expect(queue.map((a) => a.kind)).toEqual(['delete', 'undo']);
    expect(queue[0]).toMatchObject({ item_id: 'i-yoghurt' });
    expect(queue[1]).toMatchObject({ undoes: queue[0]!.id });
  });

  it('Undo: when the server answers in its own words, the toast says those', async () => {
    await render(390, {
      'POST /shopping/actions': (request) => {
        const batch = request.body as { actions: { id: string; kind: string }[] };
        return [
          200,
          {
            results: batch.actions.map((a) => ({
              id: a.id,
              status: a.kind === 'undo' ? 'ignored' : 'applied',
              reason: a.kind === 'undo' ? 'too_old' : null,
              message: a.kind === 'undo' ? 'That’s too old to undo now.' : null
            })),
            changes: { ...structuredClone(copy), reset: false }
          }
        ];
      }
    });
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    await page.getByRole('status').getByRole('button', { name: 'Undo' }).click();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'That’s too old to undo now.' }))
      .toBeVisible();
  });

  it('11.2: only a refusal takes a change off the screen, saying why', async () => {
    await render(1300, {
      'POST /shopping/actions': (request) => {
        const batch = request.body as { actions: { id: string }[] };
        return [
          200,
          {
            results: batch.actions.map((a) => ({
              id: a.id,
              status: 'refused',
              reason: 'gone',
              message: 'Onions isn’t on the list any more.'
            }))
          }
        ];
      }
    });
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'Onions isn’t on the list any more.' }))
      .toBeVisible();
    await expect.element(page.getByRole('button', { name: 'In the trolley · 2' })).toBeVisible();
    await expect.element(page.getByRole('checkbox', { name: 'Tick Onions' })).not.toBeChecked();
  });

  it('desktop: a tick the server ignores (another phone ticked it first) leaves the Put away panel', async () => {
    await render(1300, {
      'POST /shopping/actions': (request) => {
        const batch = request.body as { actions: { id: string }[] };
        // Ticked on another phone meanwhile: this tick is ignored, and the copy comes again.
        copy.items.find((i) => i.id === 'i-onions')!.ticks.push(tick('other-phone'));
        return [
          200,
          {
            results: batch.actions.map((a) => ({
              id: a.id,
              status: 'ignored',
              reason: 'already_ticked',
              message: null
            }))
          }
        ];
      }
    });
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    // The copy came again, with Onions ticked (by the other phone), and this tick isn't kept.
    await vi.waitFor(() =>
      expect(
        server.requests.filter((r) => r.path === '/shopping/changes').length
      ).toBeGreaterThanOrEqual(2)
    );
    await expect.element(page.getByRole('button', { name: 'In the trolley · 3' })).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: 'Undo last tick' }))
      .not.toBeInTheDocument();
    expect(page.getByRole('combobox', { name: 'Where' }).elements()).toEqual([]);
  });

  it('FE-4 (part 2): sends what an earlier version left waiting, as protocol 1, before showing the list', async () => {
    const device = await loadDeviceId();
    const waiting = { id: 'w1', made_at: '2026-10-18T09:00:00Z', seen: 0, kind: 'tick' as const };
    await addToQueue({ ...waiting, item_id: 'i-onions' }, ME.id, device);
    await render(1300);
    const asked = server.requests.map((r) => `${r.method} ${r.path}`);
    const sent = asked.indexOf('POST /shopping/actions');
    expect(sent).toBeGreaterThanOrEqual(0);
    expect(sent).toBeLessThan(asked.indexOf('GET /shopping/changes'));
    expect(server.requests[sent]!.body).toMatchObject({
      protocol: 1,
      device_id: device,
      login_id: ME.id,
      actions: [{ id: 'w1', kind: 'tick', item_id: 'i-onions' }]
    });
    await expect.element(page.getByRole('button', { name: 'In the trolley · 3' })).toBeVisible();
  });

  it('opened offline with the list on this phone: shows it, waiting changes on top', async () => {
    await saveCopy(null, applyChanges(null, { ...sampleCopy(), people: [], reset: true }));
    const device = await loadDeviceId();
    const waiting = { id: 'w1', made_at: '2026-10-18T09:00:00Z', seen: 0, kind: 'tick' as const };
    await addToQueue({ ...waiting, item_id: 'i-onions' }, ME.id, device);
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    mountShopping();
    await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'In the trolley · 3' })).toBeVisible();
    expect(page.getByRole('alert').elements()).toEqual([]);
  });

  /** Every request hangs until the returned release() (a weak signal); then `server` answers. */
  function weakSignal(): () => void {
    const answer = globalThis.fetch;
    let release!: () => void;
    const released = new Promise<void>((done) => (release = done));
    vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
      await released;
      return answer(...args);
    });
    return release;
  }

  it('a weak signal: the list on this phone shows at once, and the server’s answer updates it (cabledrawer 20 Oct, hand test)', async () => {
    await saveCopy(null, applyChanges(null, { ...sampleCopy(), people: [], reset: true }));
    const device = await loadDeviceId();
    const waiting = { id: 'w1', made_at: '2026-10-18T09:00:00Z', seen: 0, kind: 'tick' as const };
    await addToQueue({ ...waiting, item_id: 'i-onions' }, ME.id, device);
    // Someone else added Tahini meanwhile.
    copy.items.push({ ...structuredClone(copy.items[1]!), id: 'i-tahini', food_id: 7 });
    server = fakeShopping(copy);
    const release = weakSignal();
    await page.viewport(390, 1000);
    mountShopping();
    // At once: the copy, with the waiting tick on top, and no "Loading…".
    const soon = { timeout: 1000 };
    await expect
      .element(page.getByRole('button', { name: 'In the trolley · 3' }), soon)
      .toBeVisible();
    await expect.element(page.getByText('Loading…')).not.toBeInTheDocument();
    expect(page.getByRole('checkbox', { name: 'Tick Tahini' }).elements()).toEqual([]);

    release();
    await expect.element(page.getByRole('checkbox', { name: 'Tick Tahini' })).toBeVisible();
    // The waiting tick was sent first, once, and is still there (now in the server's copy). The
    // tick's own answer can bring Tahini down before the list is asked for, so wait for the ask.
    await vi.waitFor(() =>
      expect(server.requests.map((r) => `${r.method} ${r.path}`)).toContain('GET /shopping/changes')
    );
    const asked = server.requests.map((r) => `${r.method} ${r.path}`);
    expect(asked.indexOf('POST /shopping/actions')).toBeLessThan(
      asked.indexOf('GET /shopping/changes')
    );
    expect(server.actions).toMatchObject([{ id: 'w1', kind: 'tick' }]);
    await expect.element(page.getByRole('button', { name: 'In the trolley · 3' })).toBeVisible();
  });

  it('the browser offline, on a phone that has never had the list: says so at once', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    server = fakeShopping(copy);
    weakSignal();
    await page.viewport(390, 1000);
    mountShopping();
    await expect
      .element(page.getByRole('alert'), { timeout: 1000 })
      .toHaveTextContent(notHereText('phone'));
    vi.restoreAllMocks();
  });

  it('offline, the add box finds ingredients on this phone and adds one (11.1)', async () => {
    await saveCopy(null, applyChanges(null, { ...sampleCopy(), people: [], reset: true }));
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    mountShopping();
    await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
    await page.getByRole('textbox', { name: 'Add an item' }).fill('tah');
    const matches = page.getByRole('list', { name: 'Matching ingredients' });
    await matches.getByRole('button', { name: 'Tahini' }).click();
    await expect.element(page.getByRole('button', { name: 'Tahini', exact: true })).toBeVisible();
    await vi.waitFor(async () =>
      expect((await readQueue()).map((e) => e.action)).toMatchObject([{ kind: 'add', food_id: 7 }])
    );
  });

  it('opened offline on a computer that has never had the list: says “this computer”', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await page.viewport(1280, 1000);
    mountShopping();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(
        'Your shopping list isn’t on this computer yet. It’ll be here after you’ve opened it once while connected.'
      );
  });

  it('opened offline on a phone that has never had the list: says so', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    await page.viewport(390, 1000);
    mountShopping();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(
        'Your shopping list isn’t on this phone yet. It’ll be here after you’ve opened it once while connected.'
      );
  });

  it('phone: Change in the toast lets you pick another place', async () => {
    await render(390);
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    await page.getByRole('button', { name: 'Change' }).click();
    // Change opens the trolley by itself.
    await page.getByRole('radio', { name: 'Freezer' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'put_away', place_id: 2 })
    );
  });

  it('desktop: the Put away panel shows the last tick and where it went', async () => {
    await render(1300);
    await expect.element(page.getByRole('heading', { name: 'Put away' })).toBeVisible();
    await expect
      .element(
        page.getByText(
          'Ticked items with an amount go straight into the pantry. Each ticked row says where it went.'
        )
      )
      .toBeVisible();
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    const where = page.getByRole('combobox', { name: 'Where' });
    await expect.element(where).toBeVisible();
    await where.selectOptions('Freezer');
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'put_away', place_id: 2 })
    );
    await page.getByRole('button', { name: 'Undo last tick' }).click();
    await vi.waitFor(() => expect(server.actions.at(-1)).toMatchObject({ kind: 'undo' }));
  });

  it('Different pack? offers the planned pack and sends the one picked', async () => {
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 2' }).click();
    await openChange('Paneer');
    await page.getByRole('button', { name: 'Different pack?' }).click();
    await expect.element(page.getByText('What did you buy?')).toBeVisible();
    await expect
      .element(page.getByRole('radio', { name: '2 × 200 g' }))
      .toHaveAttribute('aria-checked', 'true');
    await page.getByRole('radio', { name: '1 × 400 g' }).click();
    await expect.element(page.getByText('Pantry gets 1 pack · 400 g.')).toBeVisible();
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({
        kind: 'different_pack',
        item_id: 'i-paneer',
        tick_id: 't-pan',
        count: 1,
        pack: 400
      })
    );
  });

  it('Different pack? → Other… takes a whole number of packs and an amount', async () => {
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 2' }).click();
    await openChange('Paneer');
    await page.getByRole('button', { name: 'Different pack?' }).click();
    await page.getByRole('radio', { name: 'Other…' }).click();
    await page.getByRole('textbox', { name: 'How many packs' }).fill('3');
    await page.getByRole('textbox', { name: 'Size of one' }).fill('1');
    await page.getByRole('combobox', { name: 'Unit' }).selectOptions('kg');
    await expect.element(page.getByText('Pantry gets 3 packs · 3 kg.')).toBeVisible();
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'different_pack', count: 3, pack: 1000 })
    );
  });

  it('Different pack? → Other… sends 1005 for 1.005 kg, not 1004.9999999999999', async () => {
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 2' }).click();
    await openChange('Paneer');
    await page.getByRole('button', { name: 'Different pack?' }).click();
    await page.getByRole('radio', { name: 'Other…' }).click();
    await page.getByRole('textbox', { name: 'How many packs' }).fill('1');
    await page.getByRole('textbox', { name: 'Size of one' }).fill('1.005');
    await page.getByRole('combobox', { name: 'Unit' }).selectOptions('kg');
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'different_pack', count: 1, pack: 1005 })
    );
  });

  it('an item with no amount says so once ticked, and Add amount opens How much?', async () => {
    copy.items.find((i) => i.id === 'i-roll')!.ticks.push(tick('t-roll'));
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 1' }).click();
    await expect.element(page.getByText('Not in the pantry yet. No amount.')).toBeVisible();
    expect(document.body.textContent).not.toContain('→ Cupboard');
    await page.getByRole('button', { name: 'Add amount for Kitchen roll' }).click();
    await expect.element(page.getByText('How much?')).toBeVisible();
  });

  it('ticking an item with no amount asks How much? at once (F62), and the answer follows the tick', async () => {
    await render(1300);
    await page.getByRole('checkbox', { name: 'Tick Kitchen roll' }).click();
    await expect.element(page.getByText('How much?')).toBeVisible();
    await expect.element(page.getByRole('radio', { name: '1 × 500 g' })).toBeVisible();
    await page.getByRole('radio', { name: '1 × 500 g' }).click();
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'different_pack', count: 1, pack: 500 })
    );
    // Both changes were sent in order: the tick, then the answer.
    expect(server.actions.map((a) => a.kind)).toEqual(['tick', 'different_pack']);
  });

  it('How much? for a new ingredient offers ready-made sizes, and picking one sends it', async () => {
    copy.items.find((i) => i.id === 'i-roll')!.ticks.push(tick('t-roll'));
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 1' }).click();
    await page.getByRole('button', { name: 'Add amount for Kitchen roll' }).click();
    await expect.element(page.getByText('How much?')).toBeVisible();
    await expect.element(page.getByRole('radio', { name: '1 × 250 g' })).toBeVisible();
    await expect.element(page.getByRole('radio', { name: '1 × 500 g' })).toBeVisible();
    await expect.element(page.getByRole('radio', { name: '1 × 1 kg' })).toBeVisible();
    await page.getByRole('radio', { name: '1 × 500 g' }).click();
    await expect.element(page.getByText('Pantry gets 1 pack · 500 g.')).toBeVisible();
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'different_pack', count: 1, pack: 500 })
    );
  });

  it('“Did you buy 2?” is a card with Yes, 2 and Just 1', async () => {
    copy.questions.push({
      id: 5,
      list_id: 'main',
      item_id: 'i-dal',
      title: 'Did you buy 2?',
      text: 'You and Wren both ticked toor dal while offline, so 2 packets went into the pantry.',
      yes: 'Yes, 2',
      no: 'Just 1',
      open: true
    });
    await render(1300);
    await expect.element(page.getByText('Did you buy 2?')).toBeVisible();
    await page.getByRole('button', { name: 'Just 1' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({
        kind: 'answer_double_tick',
        question_id: 5,
        answer: 'one'
      })
    );
  });

  it('shows a quiet note with Undo and ×', async () => {
    copy.notes.push({
      id: 31,
      list_id: 'main',
      item_id: 'i-yoghurt',
      food_id: 3,
      text: 'Wren added Yoghurt too',
      undo: 'abc',
      gone: false
    });
    await render(1300);
    await expect.element(page.getByText('Wren added Yoghurt too')).toBeVisible();
    await page.getByRole('button', { name: 'Dismiss: Wren added Yoghurt too' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'dismiss_note', note_id: 31 })
    );
  });

  describe('lists', () => {
    it('the picker shows This week, extra lists and + New list, and switches', async () => {
      await render(390);
      await page.getByRole('button', { name: 'This week main list' }).click();
      const lists = page.getByRole('group', { name: 'Lists' });
      await expect
        .element(lists.getByRole('button', { name: /^This week Main list/ }))
        .toHaveAttribute('aria-current', 'true');
      await expect.element(lists.getByRole('button', { name: '+ New list' })).toBeVisible();
      await lists.getByRole('button', { name: /^Party on Saturday Extra list/ }).click();
      await expect
        .element(page.getByText('Extra list · 1 · ticked items still go to the pantry').first())
        .toBeVisible();
      await expect.element(page.getByText('Tahini')).toBeVisible();
    });

    it('+ New list makes a list with a phone-made ID', async () => {
      await render(390);
      await page.getByRole('button', { name: 'This week main list' }).click();
      await page.getByRole('button', { name: '+ New list' }).click();
      await page.getByRole('textbox', { name: 'New list name' }).fill('Camping');
      await page.getByRole('button', { name: 'Make list' }).click();
      await vi.waitFor(() => {
        const call = server.actions.find((x) => x.kind === 'create_list')!;
        expect(call).toMatchObject({ name: 'Camping' });
        expect(call.list_id).toMatch(/^[0-9a-f-]{36}$/);
      });
    });

    it('Rename works on any list; Remove only on extra lists, with Undo', async () => {
      await render(390);
      await page.getByRole('button', { name: 'This week main list' }).click();
      await page.getByRole('button', { name: 'This week options' }).click();
      await expect.element(page.getByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
      await page.getByRole('button', { name: 'Rename' }).click();
      const box = page.getByRole('textbox', { name: 'List name' });
      await box.fill('Weekly shop');
      await page.getByRole('button', { name: 'Save' }).click();
      await vi.waitFor(() =>
        expect(server.actions.at(-1)).toMatchObject({
          kind: 'rename_list',
          list_id: 'main',
          name: 'Weekly shop'
        })
      );
    });

    it('Remove on an extra list sends a delete and the toast has Undo', async () => {
      await render(390);
      await page.getByRole('button', { name: 'This week main list' }).click();
      await page.getByRole('button', { name: 'Party on Saturday options' }).click();
      await page.getByRole('button', { name: 'Remove' }).click();
      await vi.waitFor(() =>
        expect(server.actions.at(-1)).toMatchObject({ kind: 'remove_list', list_id: 'party' })
      );
      await expect
        .element(page.getByRole('status').getByText('Removed Party on Saturday'))
        .toBeVisible();
      await page.getByRole('button', { name: 'Undo' }).click();
      await vi.waitFor(() => expect(server.actions.at(-1)).toMatchObject({ kind: 'undo' }));
      await page.getByRole('button', { name: /^This week/ }).click();
      await expect
        .element(page.getByRole('button', { name: /^Party on Saturday Extra list/ }))
        .toBeVisible();
    });
  });

  describe('adding', () => {
    it('adds a matching ingredient with a phone-made item ID', async () => {
      await render(390, {
        'GET /foods?q=tahini&limit=8': [
          200,
          {
            foods: [{ id: 7, name: 'Tahini', matched_name: null }],
            total: 1,
            counts: {},
            next: null
          }
        ]
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('tahini');
      await page.getByRole('button', { name: 'Tahini', exact: true }).click();
      await vi.waitFor(() => {
        const call = server.actions.find((x) => x.kind === 'add')!;
        expect(call).toMatchObject({ list_id: 'main', food_id: 7 });
        expect(call.item_id).toMatch(/^[0-9a-f-]{36}$/);
      });
    });

    it('a second tap while the sizes are on their way adds once, not twice', async () => {
      await render(390, {
        'GET /foods?q=2+l+sesame+paste&limit=8': [
          200,
          { foods: [], total: 0, counts: {}, next: null }
        ],
        'GET /foods?q=sesame+paste&limit=8': [
          200,
          {
            foods: [{ id: 70, name: 'Sesame paste', matched_name: null, counted_as: 'volume' }],
            total: 1,
            counts: {},
            next: null
          }
        ],
        'GET /foods/70': [200, { id: 70, name: 'Sesame paste', counted_as: 'volume', sizes: [] }]
      });
      // The sizes answer hangs until released, as on a slow connection.
      const answer = globalThis.fetch;
      let release!: () => void;
      const released = new Promise<void>((done) => (release = done));
      vi.stubGlobal('fetch', async (...args: Parameters<typeof fetch>) => {
        if (String(args[0]).endsWith('/foods/70')) await released;
        return answer(...args);
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('2 l sesame paste');
      const paste = page.getByRole('button', { name: /^Sesame paste/ });
      await paste.click();
      await paste.click();
      release();
      await expect.element(page.getByRole('status').getByText('Sesame paste added')).toBeVisible();
      await vi.waitFor(() =>
        expect(server.actions.filter((x) => x.kind === 'add').length).toBeGreaterThan(0)
      );
      expect(server.actions.filter((x) => x.kind === 'add')).toHaveLength(1);
    });

    it('“0 g butter” finds Butter and asks for an amount above 0; nothing new is made (cabledrawer 29 Oct)', async () => {
      const none = { foods: [], total: 0, counts: {}, next: null };
      await render(390, {
        'GET /foods?q=0+g+butter&limit=8': [200, none],
        'GET /foods?q=butter&limit=8': [
          200,
          {
            foods: [{ id: 71, name: 'Butter', matched_name: null, counted_as: 'weight' }],
            total: 1,
            counts: {},
            next: null
          }
        ],
        'GET /foods?q=0+g+quark&limit=8': [200, none],
        'GET /foods?q=quark&limit=8': [200, none]
      });
      const box = page.getByRole('textbox', { name: 'Add an item' });
      await box.fill('0 g butter');
      const butter = page.getByRole('button', { name: 'Butter', exact: true });
      await expect.element(butter).toBeVisible();
      await butter.click();
      await expect
        .element(page.getByRole('status').getByText('Type an amount above 0'))
        .toBeVisible();
      await expect.element(box).toHaveValue('0 g butter');
      // No match at all: still no new ingredient called "0 g quark", and no sizes sheet.
      await box.fill('0 g quark');
      await expect
        .element(page.getByRole('button', { name: '+ New ingredient: “quark”' }))
        .toBeVisible();
      await box.click();
      await userEvent.keyboard('{Enter}');
      await expect.element(box).toHaveValue('0 g quark');
      await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
      expect(server.actions.filter((x) => x.kind === 'add' || x.kind === 'add_new')).toHaveLength(
        0
      );
    });

    it('says when it is already on the list, instead of adding twice', async () => {
      await render(390, {
        'GET /foods?q=yoghurt&limit=8': [
          200,
          {
            foods: [{ id: 3, name: 'Yoghurt', matched_name: null }],
            total: 1,
            counts: {},
            next: null
          }
        ]
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('yoghurt');
      await page
        .getByRole('list', { name: 'Matching ingredients' })
        .getByRole('button', { name: 'Yoghurt' })
        .click();
      await expect.element(page.getByText('Yoghurt is already on the list · 500 g')).toBeVisible();
      expect(server.actions.some((x) => x.kind === 'add')).toBe(false);
    });

    it('a new name offers + New ingredient, then How do you count it? with the guess first, and packet sizes', async () => {
      await render(390, {
        'GET /foods?q=flaxseed&limit=8': [200, { foods: [], total: 0, counts: {}, next: null }],
        'GET /foods/guess?name=flaxseed': [200, { counted_as: 'volume', from_table: true }]
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('flaxseed');
      await page.getByRole('button', { name: '+ New ingredient: “flaxseed”' }).click();
      await expect
        .element(page.getByRole('heading', { name: 'How do you count it?' }))
        .toBeVisible();
      await vi.waitFor(() => {
        const radios = page
          .getByRole('radio')
          .elements()
          .map((r) => r.textContent ?? '');
        expect(radios[0]).toContain('By volume');
        expect(radios[0]).toContain('Our guess');
      });
      expect(
        page
          .getByRole('radio')
          .elements()
          .map((r) => (r.textContent ?? '').slice(0, 9))
      ).toEqual(['By volume', 'By weight', 'One by on', 'Don’t cou']);
      await expect
        .element(page.getByRole('radio', { name: /By volume/ }))
        .toHaveAttribute('aria-checked', 'true');
      await page.getByRole('button', { name: '+ Add a size' }).click();
      await page.getByRole('textbox', { name: 'Name' }).fill('bottle');
      await page.getByRole('textbox', { name: 'Amount' }).fill('250');
      await expect.element(page.getByRole('combobox', { name: 'Unit' })).toHaveValue('ml');
      await page.getByRole('button', { name: 'Add size' }).click();
      await expect.element(page.getByText('bottle = 250 ml')).toBeVisible();
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await vi.waitFor(() => {
        const added = server.actions.find((x) => x.kind === 'add')!;
        expect(added.new_food).toEqual({
          name: 'flaxseed',
          counted_as: 'volume',
          staple: false,
          sizes: [{ name: 'bottle', amount: 250 }]
        });
        expect(added.food_id).toBeUndefined();
      });
      // One request: no separate ingredient or size calls.
      expect(
        server.requests.some(
          (r) =>
            r.method === 'POST' && !['/shopping/actions', '/shopping/from-plan'].includes(r.path)
        )
      ).toBe(false);
    });

    it('Don’t count it makes a staple with no sizes', async () => {
      await render(390, {
        'GET /foods?q=salt&limit=8': [200, { foods: [], total: 0, counts: {}, next: null }],
        'GET /foods/guess?name=salt': [200, { counted_as: 'weight', from_table: true }]
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('salt');
      await page.getByRole('button', { name: '+ New ingredient: “salt”' }).click();
      await page.getByRole('radio', { name: /Don’t count it/ }).click();
      await expect
        .element(page.getByRole('button', { name: '+ Add a size' }))
        .not.toBeInTheDocument();
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await vi.waitFor(() => {
        const added = server.actions.find((x) => x.kind === 'add')!;
        expect(added.new_food).toEqual({ name: 'salt', counted_as: 'weight', staple: true });
      });
    });
  });

  it('a note for an item that has gone is a faint row in its shop', async () => {
    copy.items.find((i) => i.id === 'i-yoghurt')!.deleted = true;
    copy.notes.push({
      id: 40,
      list_id: 'main',
      item_id: 'i-yoghurt',
      food_id: 3,
      text: 'Wren had removed this. Your tick still went into the pantry.',
      undo: null,
      gone: false
    });
    await render(1300);
    const shop = page.getByRole('region', { name: 'Supermarket' });
    await expect
      .element(
        shop.getByText('Yoghurt · Wren had removed this. Your tick still went into the pantry.')
      )
      .toBeVisible();
    expect(page.getByRole('list', { name: 'Notes' }).elements()).toHaveLength(0);
  });

  it('after ticking, keyboard focus goes to the next row, not the page', async () => {
    await render(390);
    const onions = page.getByRole('checkbox', { name: 'Tick Onions' });
    (onions.element() as HTMLElement).focus();
    await userEvent.keyboard(' ');
    await vi.waitFor(() => {
      const active = document.activeElement as HTMLElement | null;
      expect(active?.getAttribute('aria-label')).toBe('Tick Yoghurt');
    });
  });

  it('the list picker is a disclosure; Escape closes it and returns focus to its button', async () => {
    await render(390);
    const button = page.getByRole('button', { name: 'This week main list' });
    await button.click();
    await expect.element(button).toHaveAttribute('aria-expanded', 'true');
    expect(page.getByRole('menu').elements()).toHaveLength(0);
    await userEvent.keyboard('{Escape}');
    await expect.element(button).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(button.element());
  });

  it('Different pack?: Escape closes the panel and returns focus; a bad Other… says why', async () => {
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 2' }).click();
    await openChange('Paneer');
    const opener = page.getByRole('button', { name: 'Different pack?' });
    await opener.click();
    await page.getByRole('radio', { name: 'Other…' }).click();
    await page.getByRole('button', { name: 'Done' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Type how many packs (1 to 99) and the size of one, like 1 kg.');
    expect(server.actions.some((a) => a.kind === 'different_pack')).toBe(false);
    await userEvent.keyboard('{Escape}');
    await expect.element(page.getByText('What did you buy?')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener.element());
  });

  it('Different pack? after a double tick asks which purchase', async () => {
    copy.items
      .find((i) => i.id === 'i-paneer')!
      .ticks.push(
        tick('t-pan2', {
          by: { login_id: 2, name: 'Wren' },
          bought: { amount: 400, display: '2 packs' }
        })
      );
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 2' }).click();
    await openChange('Paneer');
    await page.getByRole('button', { name: 'Different pack?' }).click();
    await expect.element(page.getByText('Which purchase?')).toBeVisible();
    await page.getByRole('radio', { name: /^Wren/ }).click();
    await page.getByRole('radio', { name: '1 × 400 g' }).click();
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() =>
      expect(server.actions.at(-1)).toMatchObject({ kind: 'different_pack', tick_id: 't-pan2' })
    );
  });

  it('Our guess shows only when the table knew the name, and a late guess keeps your choice', async () => {
    await render(390, {
      'GET /foods?q=zork&limit=8': [200, { foods: [], total: 0, counts: {}, next: null }],
      'GET /foods/guess?name=zork': () => [200, { counted_as: 'weight', from_table: false }]
    });
    await page.getByRole('textbox', { name: 'Add an item' }).fill('zork');
    await page.getByRole('button', { name: '+ New ingredient: “zork”' }).click();
    await page.getByRole('radio', { name: /One by one/ }).click();
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(document.body.textContent).not.toContain('Our guess');
    await expect
      .element(page.getByRole('radio', { name: /One by one/ }))
      .toHaveAttribute('aria-checked', 'true');
  });

  it('a removed item shows “Paneer · removed by Wren” once the server sends the tombstone', async () => {
    copy.items.find((i) => i.id === 'i-yoghurt')!.deleted = true;
    copy.removed['i-yoghurt'] = { food_id: 3, shop_id: 1, removed_by: 'Wren' };
    copy.notes.push({
      id: 41,
      list_id: 'main',
      item_id: 'i-yoghurt',
      food_id: 3,
      text: 'Wren had removed this. Your tick still went into the pantry.',
      undo: 'abc',
      gone: false
    });
    await render(1300);
    // The first copy has no tombstones: the note's own words.
    await expect.element(page.getByText(/^Yoghurt · Wren had removed this/)).toBeVisible();
    // Any later answer carries the tombstone.
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    await expect.element(page.getByText('Yoghurt · removed by Wren')).toBeVisible();
  });

  it('shows the quiet notes N8 and N9 under their item', async () => {
    for (const [id, text] of [
      [50, 'Toor dal is counted differently now, so nothing went into the pantry.'],
      [51, 'Toor dal was already in Ingredients, counted another way, so check the amount.']
    ] as const) {
      copy.notes.push({
        id,
        list_id: 'main',
        item_id: 'i-dal',
        food_id: 5,
        text,
        undo: 'x',
        gone: false
      });
    }
    await render(1300);
    await expect.element(page.getByText(/counted differently now/)).toBeVisible();
    await expect.element(page.getByText(/counted another way, so check the amount/)).toBeVisible();
  });

  it('shows the server’s wording of an amount, such as 2 boxes', async () => {
    copy.items.find((i) => i.id === 'i-onions')!.display = '2 boxes';
    await render(1300);
    await expect
      .element(page.getByRole('button', { name: 'Change amount: Onions, 2 boxes' }))
      .toBeVisible();
  });

  describe('rows (cabledrawer 20 Oct, hand test)', () => {
    /** A finger sliding sideways over a row: down, two moves, up. */
    function swipe(row: HTMLElement, dx: number, dy = 0) {
      const base = { pointerId: 7, pointerType: 'touch', isPrimary: true, bubbles: true };
      const at = (x: number, y: number) => ({ ...base, clientX: x, clientY: y });
      row.dispatchEvent(new PointerEvent('pointerdown', at(300, 300)));
      row.dispatchEvent(new PointerEvent('pointermove', at(300 + dx / 2, 300 + dy / 2)));
      row.dispatchEvent(new PointerEvent('pointermove', at(300 + dx, 300 + dy)));
      row.dispatchEvent(new PointerEvent('pointerup', at(300 + dx, 300 + dy)));
    }
    const slideOf = (name: string) =>
      page
        .getByRole('checkbox', { name: `Tick ${name}` })
        .element()
        .closest('.slide') as HTMLElement;

    it('only the square ticks: the name opens the amount box, which holds the real amount', async () => {
      await render(390);
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      await expect.element(page.getByRole('form', { name: 'Change Yoghurt' })).toBeVisible();
      await expect.element(page.getByRole('textbox', { name: 'Amount' })).toHaveValue('500');
      await expect.element(page.getByRole('combobox', { name: 'Unit' })).toHaveValue('g');
      expect(server.actions).toEqual([]);
    });

    it('the amount pill opens it too; − / + and Done send one set_amount; focus comes back', async () => {
      await render(390);
      await page.getByRole('button', { name: 'Change amount: Yoghurt, 500 g' }).click();
      await page.getByRole('button', { name: 'More' }).click();
      await expect.element(page.getByRole('textbox', { name: 'Amount' })).toHaveValue('550');
      expect(server.actions).toEqual([]); // nothing is sent while you press +
      await page.getByRole('button', { name: 'Done' }).click();
      await vi.waitFor(() =>
        expect(server.actions).toMatchObject([
          { kind: 'set_amount', item_id: 'i-yoghurt', amount: 550 }
        ])
      );
      await vi.waitFor(() => expect(document.activeElement?.textContent?.trim()).toBe('Yoghurt'));
    });

    it('a changed unit keeps the amount, and Escape leaves the line as it was', async () => {
      await render(390);
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      await page.getByRole('combobox', { name: 'Unit' }).selectOptions('kg');
      await expect.element(page.getByRole('textbox', { name: 'Amount' })).toHaveValue('0.5');
      await userEvent.keyboard('{Escape}');
      await expect
        .element(page.getByRole('form', { name: 'Change Yoghurt' }))
        .not.toBeInTheDocument();
      expect(server.actions).toEqual([]);
    });

    it('a box that can’t be read says why and stays open', async () => {
      await render(390);
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      await page.getByRole('textbox', { name: 'Amount' }).fill('lots');
      await page.getByRole('button', { name: 'Done' }).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('Type an amount, like 500 g or 2 packets.');
      expect(server.actions).toEqual([]);
    });

    for (const width of [390, 1300]) {
      it(`${width === 390 ? 'phone' : 'computer'}: Edit ingredient saves the box, then opens the ingredient editor`, async () => {
        await render(width);
        await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
        const box = page.getByRole('form', { name: 'Change Yoghurt' });
        await box.getByRole('button', { name: 'More' }).click();
        await box.getByRole('button', { name: 'Edit ingredient' }).click();
        await expect.element(box).not.toBeInTheDocument();
        expect(ingredientEditor.foodId).toBe(3);
        await vi.waitFor(() =>
          expect(server.actions).toMatchObject([
            { kind: 'set_amount', item_id: 'i-yoghurt', amount: 550 }
          ])
        );
      });
    }

    it('Edit ingredient with a box that can’t be read says why, and opens nothing', async () => {
      await render(390);
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      await page.getByRole('textbox', { name: 'Amount' }).fill('lots');
      await page.getByRole('button', { name: 'Edit ingredient' }).click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('Type an amount, like 500 g or 2 packets.');
      expect(ingredientEditor.foodId).toBeNull();
      expect(server.actions).toEqual([]);
    });

    it('offline: no Edit ingredient (the editor needs the server); Remove from list stays', async () => {
      await openOffline(390);
      network.offline = true; // as the bar shows after a few seconds without the server
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      const box = page.getByRole('form', { name: 'Change Yoghurt' });
      await expect.element(box.getByRole('button', { name: 'Remove from list' })).toBeVisible();
      expect(box.getByRole('button', { name: 'Edit ingredient' }).elements()).toHaveLength(0);
    });

    it('Remove from list asks first; Keep it removes nothing; Remove sends delete, with Undo', async () => {
      await render(390);
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      await page.getByRole('button', { name: 'Remove from list' }).click();
      const ask = page.getByRole('alertdialog', { name: 'Remove Yoghurt from the shopping list?' });
      await expect.element(ask).toBeVisible();
      await expect.element(ask.getByText('Nothing goes into the pantry.')).toBeVisible();
      expect(server.actions).toEqual([]); // asking removes nothing
      // The safe choice has the focus.
      expect(document.activeElement?.textContent?.trim()).toBe('Keep it');
      await ask.getByRole('button', { name: 'Keep it' }).click();
      await expect.element(ask).not.toBeInTheDocument();
      expect(server.actions).toEqual([]);
      await page.getByRole('button', { name: 'Remove from list' }).click();
      await page
        .getByRole('alertdialog')
        .getByRole('button', { name: 'Remove', exact: true })
        .click();
      await vi.waitFor(() =>
        expect(server.actions.at(-1)).toMatchObject({ kind: 'delete', item_id: 'i-yoghurt' })
      );
      const toast = page.getByRole('status').filter({ hasText: 'Removed Yoghurt' });
      await expect.element(toast.getByRole('button', { name: 'Undo' })).toBeVisible();
    });

    it('Escape on the question keeps the line', async () => {
      await render(390);
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      await page.getByRole('button', { name: 'Remove from list' }).click();
      await expect.element(page.getByRole('alertdialog')).toBeVisible();
      await userEvent.keyboard('{Escape}');
      await expect.element(page.getByRole('alertdialog')).not.toBeInTheDocument();
      expect(server.actions).toEqual([]);
    });

    it('phone: swiping left shows a red Remove; a swipe alone removes nothing, and Remove goes at once with Undo (F77)', async () => {
      await render(390);
      swipe(slideOf('Yoghurt'), -100);
      const red = page.getByRole('button', { name: 'Remove Yoghurt from the list' });
      await expect.element(red).toBeVisible();
      expect(server.actions).toEqual([]);
      await red.click();
      // No question first (cabledrawer 28 Oct): the delete is sent, and the toast offers Undo.
      expect(page.getByRole('alertdialog').elements()).toEqual([]);
      await vi.waitFor(() =>
        expect(server.actions.at(-1)).toMatchObject({ kind: 'delete', item_id: 'i-yoghurt' })
      );
      const toast = page.getByRole('status').filter({ hasText: 'Removed Yoghurt' });
      await expect.element(toast.getByRole('button', { name: 'Undo' })).toBeVisible();
    });

    it('phone: an up-and-down drag scrolls and shows no Remove', async () => {
      await render(390);
      swipe(slideOf('Yoghurt'), -20, 80);
      expect(page.getByRole('button', { name: 'Remove Yoghurt from the list' }).elements()).toEqual(
        []
      );
    });

    it('phone: a tap on a swiped row closes it instead of opening or ticking it', async () => {
      await render(390);
      swipe(slideOf('Yoghurt'), -100);
      await expect
        .element(page.getByRole('button', { name: 'Remove Yoghurt from the list' }))
        .toBeVisible();
      await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
      expect(page.getByRole('form', { name: 'Change Yoghurt' }).elements()).toEqual([]);
      expect(server.actions).toEqual([]);
    });

    it('computer: the ⋯ menu has Change amount, Move to… and Remove from list…, which asks', async () => {
      await render(1300);
      await page.getByRole('button', { name: 'More for Yoghurt' }).click();
      const items = page
        .getByRole('menuitem')
        .elements()
        .map((e) => e.textContent);
      expect(items).toEqual(['Change amount', 'Move to…', 'Remove from list…']);
      await page.getByRole('menuitem', { name: 'Remove from list…' }).click();
      await expect
        .element(page.getByRole('alertdialog', { name: 'Remove Yoghurt from the shopping list?' }))
        .toBeVisible();
    });

    it('computer: Escape closes the ⋯ menu and gives the focus back to its button', async () => {
      await render(1300);
      const more = page.getByRole('button', { name: 'More for Yoghurt' });
      await more.click();
      await expect.element(page.getByRole('menuitem', { name: 'Change amount' })).toHaveFocus();
      await userEvent.keyboard('{ArrowDown}{ArrowDown}');
      await expect.element(page.getByRole('menuitem', { name: 'Remove from list…' })).toHaveFocus();
      await userEvent.keyboard('{Escape}');
      expect(page.getByRole('menu').elements()).toEqual([]);
      await expect.element(more).toHaveFocus();
    });

    describe('moving a line (cabledrawer 22 Oct, question 3)', () => {
      const moves = () => server.actions.filter((a) => a.kind === 'move');

      it('phone: swipe right shows a blue Move…, which opens the picker; a swipe alone moves nothing', async () => {
        await render(390);
        swipe(slideOf('Yoghurt'), 110);
        const blue = page.getByRole('button', { name: /^Move… Yoghurt/ });
        await expect.element(blue).toBeVisible();
        expect(server.actions).toEqual([]);
        await blue.click();
        const sheet = page.getByRole('dialog', { name: 'Move Yoghurt to…' });
        await expect.element(sheet).toBeVisible();
        // Where it is now is marked; the other shops and Any shop are the choices.
        await expect
          .element(sheet.getByRole('radio', { name: /Supermarket/ }))
          .toHaveAttribute('aria-checked', 'true');
        expect(
          sheet
            .getByRole('radio')
            .elements()
            .map((e) => e.textContent?.trim())
        ).toEqual(['Supermarketnow', 'Indian grocer', 'Any shop']);
        await expect
          .element(sheet.getByRole('button', { name: /Party on Saturday/ }))
          .toBeVisible();
        expect(server.actions).toEqual([]);
      });

      it('choosing a shop moves the line there, never ticks it, and the toast says so with Undo', async () => {
        await render(390);
        swipe(slideOf('Yoghurt'), 110);
        await page.getByRole('button', { name: /^Move… Yoghurt/ }).click();
        await page.getByRole('radio', { name: 'Indian grocer' }).click();
        await vi.waitFor(() => expect(moves()).toHaveLength(1));
        expect(moves()[0]).toMatchObject({
          kind: 'move',
          item_id: 'i-yoghurt',
          list_id: 'main',
          shop_id: 2
        });
        expect(server.actions.some((a) => a.kind === 'tick')).toBe(false);
        expect(row('i-yoghurt')).toMatchObject({ shop_id: 2 });
        const toast = page
          .getByRole('status')
          .filter({ hasText: 'Moved Yoghurt to Indian grocer' });
        await expect.element(toast).toBeVisible();
        await toast.getByRole('button', { name: 'Undo' }).click();
        await vi.waitFor(() =>
          expect(server.actions.some((a) => a.kind === 'undo' && a.undoes === moves()[0]!.id)).toBe(
            true
          )
        );
      });

      it('choosing another list keeps the shop', async () => {
        await render(390);
        swipe(slideOf('Yoghurt'), 110);
        await page.getByRole('button', { name: /^Move… Yoghurt/ }).click();
        await page.getByRole('button', { name: /Party on Saturday/ }).click();
        await vi.waitFor(() => expect(moves()).toHaveLength(1));
        expect(moves()[0]).toMatchObject({ list_id: 'party', shop_id: 1 });
        await expect
          .element(
            page.getByRole('status').filter({ hasText: 'Moved Yoghurt to Party on Saturday' })
          )
          .toBeVisible();
      });

      it('phone: a keyboard or screen reader reaches Move to… in the amount box', async () => {
        await render(390);
        await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
        await page.getByRole('button', { name: 'Move to…' }).click();
        await expect.element(page.getByRole('dialog', { name: 'Move Yoghurt to…' })).toBeVisible();
        await page.getByRole('radio', { name: 'Any shop' }).click();
        await vi.waitFor(() => expect(moves()).toHaveLength(1));
        expect(moves()[0]).toMatchObject({ shop_id: null });
      });

      it('computer: Move to… in the ⋯ menu opens the same choices; Esc leaves it as it was', async () => {
        await render(1300);
        await page.getByRole('button', { name: 'More for Yoghurt' }).click();
        await page.getByRole('menuitem', { name: 'Move to…' }).click();
        const sheet = page.getByRole('dialog', { name: 'Move Yoghurt to…' });
        await expect.element(sheet).toBeVisible();
        await userEvent.keyboard('{Escape}');
        expect(page.getByRole('dialog').elements()).toEqual([]);
        expect(server.actions).toEqual([]);
      });

      it('phone: Cancel and Esc give the focus back to the Move to… button, not the page', async () => {
        await render(390);
        await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
        const open = page.getByRole('button', { name: 'Move to…' });
        await open.click();
        await page.getByRole('button', { name: 'Cancel' }).click();
        await expect.element(open).toHaveFocus();
        await open.click();
        await userEvent.keyboard('{Escape}');
        expect(page.getByRole('dialog').elements()).toEqual([]);
        await expect.element(open).toHaveFocus();
      });

      it('phone: Esc after a swipe puts the focus back on the row’s Move…', async () => {
        await render(390);
        swipe(slideOf('Yoghurt'), 110);
        const blue = page.getByRole('button', { name: /^Move… Yoghurt/ });
        await blue.click();
        await userEvent.keyboard('{Escape}');
        await vi.waitFor(() => expect(document.activeElement).not.toBe(document.body));
        expect(document.activeElement?.closest('li')?.textContent).toContain('Yoghurt');
      });

      it('after a pick the row has gone, so the focus goes to a neighbour in the shop or its heading', async () => {
        await render(1300);
        await page.getByRole('button', { name: 'More for Yoghurt' }).click();
        await page.getByRole('menuitem', { name: 'Move to…' }).click();
        await page.getByRole('radio', { name: 'Indian grocer' }).click();
        await vi.waitFor(() => expect(moves()).toHaveLength(1));
        await vi.waitFor(() => {
          const here = document.activeElement;
          expect(here).not.toBe(document.body);
          const ok = here?.matches('.tick input') || here?.matches('h2');
          expect(ok).toBe(true);
          expect(here?.isConnected).toBe(true);
        });
      });

      it('phone: after a pick from the amount box the focus is not lost either', async () => {
        await render(390);
        await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
        await page.getByRole('button', { name: 'Move to…' }).click();
        await page.getByRole('radio', { name: 'Any shop' }).click();
        await vi.waitFor(() => expect(moves()).toHaveLength(1));
        await vi.waitFor(() => {
          expect(document.activeElement).not.toBe(document.body);
          expect(document.activeElement?.isConnected).toBe(true);
        });
      });

      it('computer: Esc gives the focus back to the row’s ⋯ button', async () => {
        await render(1300);
        const more = page.getByRole('button', { name: 'More for Yoghurt' });
        await more.click();
        await page.getByRole('menuitem', { name: 'Move to…' }).click();
        await userEvent.keyboard('{Escape}');
        await expect.element(more).toHaveFocus();
      });

      it('offline: the move shows at once, is queued, and is counted in the offline bar', async () => {
        await openOffline(390);
        await page.getByRole('button', { name: 'Yoghurt', exact: true }).click();
        await page.getByRole('button', { name: 'Move to…' }).click();
        await page.getByRole('radio', { name: 'Indian grocer' }).click();
        await expect
          .element(page.getByRole('status').filter({ hasText: 'Moved Yoghurt to Indian grocer' }))
          .toBeVisible();
        await vi.waitFor(async () =>
          expect((await readQueue()).map((e) => e.action.kind)).toEqual(['move'])
        );
        expect((await readQueue())[0]!.action).toMatchObject({ item_id: 'i-yoghurt', shop_id: 2 });
        await vi.waitFor(() => expect(network.waiting).toBe(1));
        expect(offlineText('phone', network.waiting, true).title).toBe('Offline — 1 change waiting');
        // The row itself moved on this phone, not only the toast (0.5 PR 7 review R1): the last
        // shop heading above Yoghurt is now Indian grocer.
        await vi.waitFor(() => {
          const row = page.getByRole('button', { name: 'Yoghurt', exact: true }).element();
          const above = page
            .getByRole('heading', { level: 2 })
            .elements()
            .filter((h) => h.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING);
          expect(above.at(-1)?.textContent).toContain('Indian grocer');
        });
      });

      it('a ticked line has no Move…', async () => {
        await render(390);
        await page.getByRole('button', { name: 'In the trolley · 2' }).click();
        expect(page.getByRole('button', { name: /Move…/ }).elements()).toEqual([]);
      });
    });

    it('a staple says “restocked” in the toast and on its row, and has no Change', async () => {
      copy.foods.find((f) => f.id === 3)!.staple = true;
      await render(390);
      await page.getByRole('checkbox', { name: 'Tick Yoghurt' }).click();
      const toast = page.getByRole('status').filter({ hasText: 'Yoghurt restocked' });
      await expect.element(toast).toBeVisible();
      expect(toast.getByRole('button', { name: 'Change' }).elements()).toEqual([]);
      await page.getByRole('button', { name: 'In the trolley · 3' }).click();
      await expect.element(page.getByText('Restocked · staples aren’t counted')).toBeVisible();
      expect(document.body.textContent).not.toContain('→ Cupboard');
    });

    it('a line with no amount says “ticked” in the toast, with nothing to change', async () => {
      await render(390);
      await page.getByRole('checkbox', { name: 'Tick Kitchen roll' }).click();
      const toast = page.getByRole('status').filter({ hasText: 'Kitchen roll ticked' });
      await expect.element(toast).toBeVisible();
      expect(toast.getByRole('button', { name: 'Change' }).elements()).toEqual([]);
    });

    it('the Undo on a ticked row takes that tick back', async () => {
      await render(1300);
      await page.getByRole('button', { name: 'In the trolley · 2' }).click();
      await page.getByRole('button', { name: 'Undo ticking Paneer' }).click();
      await vi.waitFor(() =>
        expect(server.actions.at(-1)).toMatchObject({ kind: 'undo', undoes: 't-pan' })
      );
    });
  });
});
