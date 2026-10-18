import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import NewIngredient from '$lib/components/NewIngredient.svelte';
import Toast from '$lib/components/Toast.svelte';
import { ME, fakeShopping, sampleCopy, tick } from '$lib/testing/fakeShopping';
import { changeOf } from '$lib/testing/fakeApi';
import { session } from '$lib/session.svelte';
import { newIngredient } from '$lib/newIngredient.svelte';
import { forgetServerKind } from '$lib/shopping/load';
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

  async function render(width: number, extra: Parameters<typeof fakeShopping>[1] = {}) {
    server = fakeShopping(copy, extra);
    await page.viewport(width, 1000);
    for (const component of [Shopping, Toast, NewIngredient]) {
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(component, { target }));
    }
    flushSync();
    await expect.element(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
  }

  beforeEach(() => {
    copy = sampleCopy();
    forgetServerKind();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
    newIngredient.cancel();
  });

  afterEach(() => {
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
    const call = server.requests.find((r) => r.path === '/shopping/lists/main/clear-ticked')!;
    expect((call.body as { item_ids: string[] }).item_ids.sort()).toEqual([
      'i-coriander',
      'i-paneer'
    ]);
    await expect.element(page.getByRole('button', { name: 'Undo' })).toBeVisible();
  });

  it('phone: ticking sends a tick and the toast says where it went, with Change and Undo', async () => {
    await render(390);
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    const sent = server.requests.find((r) => r.path === '/shopping/actions')!;
    const body = sent.body as { protocol: number; actions: { kind: string; item_id: string }[] };
    expect(body.protocol).toBe(1);
    expect(body.actions[0]).toMatchObject({ kind: 'tick', item_id: 'i-onions' });
    const toast = page.getByRole('status').filter({ hasText: 'Onions → Fridge' });
    await expect.element(toast).toBeVisible();
    await expect.element(toast.getByRole('button', { name: 'Change' })).toBeVisible();
    await toast.getByRole('button', { name: 'Undo' }).click();
    await vi.waitFor(() => expect(server.actions.map((a) => a.kind)).toEqual(['tick', 'undo']));
    expect(server.actions[1]!.undoes).toBe(server.actions[0]!.id);
  });

  it('phone: Change in the toast lets you pick another place', async () => {
    await render(390);
    await page.getByRole('checkbox', { name: 'Tick Onions' }).click();
    await page.getByRole('button', { name: 'Change' }).click();
    await page.getByRole('button', { name: 'In the trolley · 3' }).click();
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
        const call = server.requests.find(
          (r) => r.method === 'POST' && r.path === '/shopping/lists'
        )!;
        expect(call.body).toMatchObject({ name: 'Camping' });
        expect((call.body as { id: string }).id).toMatch(/^[0-9a-f-]{36}$/);
      });
    });

    it('Rename works on any list; Remove only on extra lists, with Undo', async () => {
      await render(390, {
        'PATCH /shopping/lists/main': [
          200,
          { shopping_list: { id: 'main' }, change: changeOf(810, 'Renamed') }
        ]
      });
      await page.getByRole('button', { name: 'This week main list' }).click();
      await page.getByRole('button', { name: 'This week options' }).click();
      await expect.element(page.getByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
      await page.getByRole('button', { name: 'Rename' }).click();
      const box = page.getByRole('textbox', { name: 'List name' });
      await box.fill('Weekly shop');
      await page.getByRole('button', { name: 'Save' }).click();
      await vi.waitFor(() =>
        expect(
          server.requests.some((r) => r.method === 'PATCH' && r.path === '/shopping/lists/main')
        ).toBe(true)
      );
    });

    it('Remove on an extra list sends a delete and the toast has Undo', async () => {
      await render(390);
      await page.getByRole('button', { name: 'This week main list' }).click();
      await page.getByRole('button', { name: 'Party on Saturday options' }).click();
      await page.getByRole('button', { name: 'Remove' }).click();
      await vi.waitFor(() =>
        expect(
          server.requests.some((r) => r.method === 'DELETE' && r.path === '/shopping/lists/party')
        ).toBe(true)
      );
      await expect
        .element(page.getByRole('status').getByText('Removed Party on Saturday'))
        .toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Undo' })).toBeVisible();
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
        ],
        'POST /shopping/lists/main/items': [
          201,
          { item: { id: 'x' }, merged: false, change: changeOf(820, 'Added') }
        ]
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('tahini');
      await page.getByRole('button', { name: 'Tahini', exact: true }).click();
      await vi.waitFor(() => {
        const call = server.requests.find(
          (r) => r.method === 'POST' && r.path === '/shopping/lists/main/items'
        )!;
        expect(call.body).toMatchObject({ food_id: 7 });
        expect((call.body as { id: string }).id).toMatch(/^[0-9a-f-]{36}$/);
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
      expect(server.requests.some((r) => r.path === '/shopping/lists/main/items')).toBe(false);
    });

    it('a new name offers + New ingredient, then How do you count it? with the guess first, and packet sizes', async () => {
      await render(390, {
        'GET /foods?q=flaxseed&limit=8': [200, { foods: [], total: 0, counts: {}, next: null }],
        'GET /foods/guess?name=flaxseed': [200, { counted_as: 'volume', from_table: true }],
        'POST /foods': [
          201,
          {
            food: { id: 90, name: 'flaxseed', counted_as: 'volume', staple: false },
            change: changeOf(830, 'Added flaxseed')
          }
        ],
        'POST /foods/90/sizes': [201, { food: { id: 90 }, change: changeOf(831, 'Added a size') }],
        'POST /shopping/lists/main/items': [
          201,
          { item: { id: 'x' }, merged: false, change: changeOf(832, 'Added') }
        ]
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
        const made = server.requests.find((r) => r.method === 'POST' && r.path === '/foods')!;
        expect(made.body).toEqual({ name: 'flaxseed', staple: false, counted_as: 'volume' });
        const size = server.requests.find((r) => r.path === '/foods/90/sizes')!;
        expect(size.body).toEqual({ name: 'bottle', amount: { amount: 250, unit: 'ml' } });
        const added = server.requests.find((r) => r.path === '/shopping/lists/main/items')!;
        expect(added.body).toMatchObject({ food_id: 90 });
      });
    });

    it('Don’t count it makes a staple with no sizes', async () => {
      await render(390, {
        'GET /foods?q=salt&limit=8': [200, { foods: [], total: 0, counts: {}, next: null }],
        'GET /foods/guess?name=salt': [200, { counted_as: 'weight', from_table: true }],
        'POST /foods': [
          201,
          {
            food: { id: 91, name: 'salt', counted_as: 'weight', staple: true },
            change: changeOf(840, 'Added')
          }
        ],
        'POST /shopping/lists/main/items': [
          201,
          { item: { id: 'x' }, merged: false, change: changeOf(841, 'Added') }
        ]
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('salt');
      await page.getByRole('button', { name: '+ New ingredient: “salt”' }).click();
      await page.getByRole('radio', { name: /Don’t count it/ }).click();
      await expect
        .element(page.getByRole('button', { name: '+ Add a size' }))
        .not.toBeInTheDocument();
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await vi.waitFor(() => {
        const made = server.requests.find((r) => r.method === 'POST' && r.path === '/foods')!;
        expect(made.body).toEqual({ name: 'salt', staple: true, counted_as: 'weight' });
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

  it('works against a server with only the one-at-a-time requests (no changes feed yet)', async () => {
    const view = {
      shopping_list: { id: 'main', name: 'This week', main: true, to_buy: 1, ticked: 0 },
      shops: [
        {
          shop: { id: 1, name: 'Supermarket' },
          name: 'Supermarket',
          aisles: [
            {
              aisle: 'veg_fruit',
              name: 'Veg & fruit',
              items: [
                {
                  id: 'i1',
                  list_id: 'main',
                  food: { id: 1, name: 'Onions' },
                  amount: { amount: 5, unit: 'count', short: '5', display: '5', as_sold: null },
                  shop: { id: 1, name: 'Supermarket' },
                  aisle: 'veg_fruit',
                  ticked_at: null,
                  ticked_by: null,
                  put_away_place: null,
                  hand_edited: false,
                  source: 'typed',
                  added_by: 'Tess'
                }
              ]
            }
          ],
          in_trolley: []
        }
      ]
    };
    await render(390, {
      'GET /shopping/changes': [404, { detail: 'Not found' }],
      'GET /shopping/lists': [
        200,
        { lists: [{ id: 'main', name: 'This week', main: true, to_buy: 1, ticked: 0 }] }
      ],
      'GET /shopping/lists/main': [200, view],
      'GET /shops': [200, [{ id: 1, name: 'Supermarket' }]],
      'GET /places': [200, [{ id: 1, name: 'Fridge', kind: 'fridge' }]]
    });
    await expect.element(page.getByText('Onions')).toBeVisible();
    await expect.element(page.getByText('1 to buy', { exact: true })).toBeVisible();
  });
});
