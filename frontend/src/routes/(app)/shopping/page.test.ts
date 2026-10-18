import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import NewIngredient from '$lib/components/NewIngredient.svelte';
import Toast from '$lib/components/Toast.svelte';
import { ME, fakeShopping, sampleCopy, tick } from '$lib/testing/fakeShopping';
import { dropPhone, freshPhone } from '$lib/testing/phone';
import { loadDeviceId } from '$lib/offline/device';
import { addToQueue, readQueue, saveCopy } from '$lib/offline/store';
import { applyChanges } from '$lib/shopping/load';
import { session } from '$lib/session.svelte';
import { newIngredient } from '$lib/newIngredient.svelte';
import type { ShoppingCopy } from '$lib/shopping/types';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
import Shopping from './+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

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

  beforeEach(() => {
    freshPhone();
    copy = sampleCopy();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
    newIngredient.cancel();
  });

  afterEach(async () => {
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
    await expect.element(page.getByRole('button', { name: '→ Fridge' }).first()).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: 'Different pack?' }).first())
      .toBeVisible();
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

  it('opened offline on a phone that has never had the list: says so', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    mountShopping();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(
        "Your shopping list isn't on this phone yet. It'll be here after you've opened it once while connected."
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
    await expect.element(page.getByText('Ticked items go straight into the pantry.')).toBeVisible();
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
    await page.getByRole('button', { name: 'Different pack?' }).last().click();
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
    await page.getByRole('button', { name: 'Different pack?' }).last().click();
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

  it('an item with no amount offers How much? once ticked', async () => {
    copy.items.find((i) => i.id === 'i-roll')!.ticks.push(tick('t-roll'));
    await render(1300);
    await page.getByRole('button', { name: 'In the trolley · 1' }).click();
    await expect.element(page.getByRole('button', { name: 'How much?' })).toBeVisible();
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
        server.requests.some((r) => r.method === 'POST' && r.path !== '/shopping/actions')
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
    const opener = page.getByRole('button', { name: 'Different pack?' }).last();
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
    await page.getByRole('button', { name: 'Different pack?' }).last().click();
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
      .element(page.getByRole('button', { name: 'Onions: 2 boxes. Change' }))
      .toBeVisible();
  });
});
