// Shopping on the phone, "in the shop" (0.8 S4): Add as bought, Already have it, How many?,
// the trolley most recent first, and the amount box's quick picks.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import Toast from '#lib/components/Toast.svelte';
import { ME, fakeShopping, item, sampleCopy, tick } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { applyChanges } from '#lib/shopping/load.js';
import { readQueue, saveCopy } from '#lib/offline/store.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import type { ShoppingCopy } from '#lib/shopping/types.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import Shopping from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const found = (rows: { id: number; name: string; counted_as?: string }[]) =>
  [
    200,
    {
      foods: rows.map((r) => ({
        matched_name: null,
        counted_as: 'weight',
        staple: false,
        place: null,
        ...r
      })),
      total: rows.length,
      counts: {},
      next: null
    }
  ] as [number, unknown];

describe('Shopping on the phone', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let copy: ShoppingCopy;
  let server: ReturnType<typeof fakeShopping>;

  function mountShopping() {
    for (const component of [Shopping, Toast]) {
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(component, { target }));
    }
    flushSync();
  }

  async function render(extra: Parameters<typeof fakeShopping>[1] = {}) {
    server = fakeShopping(copy, extra);
    await page.viewport(390, 1000);
    mountShopping();
    await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
  }

  const kinds = () => server.actions.map((a) => a.kind);

  beforeEach(() => {
    freshPhone();
    copy = sampleCopy();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
  });

  afterEach(async () => {
    network.reset();
    await dropPhone();
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  describe('Add as bought (F117)', () => {
    it('adds the ingredient and ticks it at once: an add, then a tick of the same line', async () => {
      await render({ 'GET /foods?q=tahini&limit=8': found([{ id: 7, name: 'Tahini' }]) });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('tahini');
      await page.getByRole('button', { name: 'Add as bought' }).click();
      await vi.waitFor(() => expect(kinds()).toEqual(['add', 'tick']));
      expect(server.actions[1]!.item_id).toBe(server.actions[0]!.item_id);
      // The add says it is "as bought", so the server never joins it into a line still to buy.
      expect(server.actions[0]).toMatchObject({ kind: 'add', as_bought: true });
      // One toast, with where it went and Undo.
      await expect.element(page.getByRole('status').filter({ hasText: 'Tahini' })).toBeVisible();
    });

    it('says where it will go, under the button', async () => {
      await render({
        'GET /foods?q=tahini&limit=8': found([
          { id: 7, name: 'Tahini', place: { id: 3, name: 'Cupboard' } } as never
        ])
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('tahini');
      const bought = page.getByRole('button', { name: 'Add as bought' });
      await vi.waitFor(() =>
        expect(bought.element().textContent).toMatch(/Straight into the pantry/)
      );
      await vi.waitFor(() => expect(bought.element().textContent).toMatch(/→ Cupboard/));
    });

    it('with no usual place, names the household\'s first cupboard place, not "Cupboard"', async () => {
      copy.places = [
        { id: 1, name: 'Chiller', kind: 'fridge', position: 0 },
        { id: 9, name: 'Larder', kind: 'cupboard', position: 1 },
        { id: 8, name: 'Dry shelf', kind: 'cupboard', position: 2 }
      ];
      await render({ 'GET /foods?q=tahini&limit=8': found([{ id: 7, name: 'Tahini' }]) });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('tahini');
      const bought = page.getByRole('button', { name: 'Add as bought' });
      await vi.waitFor(() => expect(bought.element().textContent).toMatch(/→ Larder/));
      expect(bought.element().textContent).not.toMatch(/Cupboard/);
    });

    it('one Undo takes back the tick and the add', async () => {
      await render({ 'GET /foods?q=tahini&limit=8': found([{ id: 7, name: 'Tahini' }]) });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('tahini');
      await page.getByRole('button', { name: 'Add as bought' }).click();
      await vi.waitFor(() => expect(kinds()).toEqual(['add', 'tick']));
      await page.getByRole('status').getByRole('button', { name: 'Undo' }).click();
      await vi.waitFor(() => expect(kinds()).toEqual(['add', 'tick', 'undo', 'undo']));
      expect(server.actions[2]!.undoes).toBe(server.actions[1]!.id);
      expect(server.actions[3]!.undoes).toBe(server.actions[0]!.id);
    });

    it('is not offered for an ingredient already on the list (its own line has a tick)', async () => {
      await render({ 'GET /foods?q=yoghurt&limit=8': found([{ id: 3, name: 'Yoghurt' }]) });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('yoghurt');
      await expect
        .element(page.getByRole('button', { name: 'Yoghurt', exact: true }))
        .toBeVisible();
      expect(page.getByRole('button', { name: 'Add as bought' }).elements()).toEqual([]);
    });

    it('works offline: an add and a tick wait in the queue, and the line is in the trolley', async () => {
      await saveCopy(null, applyChanges(null, { ...sampleCopy(), people: [], reset: true }));
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      mountShopping();
      await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
      await page.getByRole('textbox', { name: 'Add an item' }).fill('tah');
      await page.getByRole('button', { name: 'Add as bought' }).click();
      await vi.waitFor(async () => {
        const queue = (await readQueue()).map((e) => e.action);
        expect(queue.map((a) => a.kind)).toEqual(['add', 'tick']);
        expect(queue[0]).toMatchObject({ as_bought: true });
        expect((queue[1] as { item_id: string }).item_id).toBe(
          (queue[0] as { item_id: string }).item_id
        );
      });
      await expect.element(page.getByRole('button', { name: /^In the trolley · 3/ })).toBeVisible();
    });

    it('offline, a just-added line shows the place it will go, not "→ Pantry" (F199)', async () => {
      await saveCopy(null, applyChanges(null, { ...sampleCopy(), people: [], reset: true }));
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      mountShopping();
      await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
      await page.getByRole('textbox', { name: 'Add an item' }).fill('200 g tahini');
      await page.getByRole('button', { name: 'Add as bought' }).click();
      await page.getByRole('button', { name: /^In the trolley · 3/ }).click();
      const place = page.getByRole('button', { name: 'Change where Tahini went' });
      await expect.element(place).toBeVisible();
      await expect.element(place).toHaveTextContent('→ Cupboard');
    });
  });

  describe('How many? (F134)', () => {
    it('asks for a counted ingredient with no usual size, and adds what was picked', async () => {
      await render({
        'GET /foods?q=mango&limit=8': found([{ id: 8, name: 'Mango', counted_as: 'count' }])
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('mango');
      await page.getByRole('button', { name: 'Mango', exact: true }).click();
      const ask = page.getByRole('group', { name: 'How many mangos?' });
      await expect.element(ask).toBeVisible();
      for (const n of ['1', '2', '6', '12']) {
        await expect.element(ask.getByRole('button', { name: n, exact: true })).toBeVisible();
      }
      expect(kinds()).toEqual([]);
      await ask.getByRole('button', { name: '6', exact: true }).click();
      await vi.waitFor(() =>
        expect(server.actions[0]).toMatchObject({ kind: 'add', food_id: 8, amount: 6 })
      );
    });

    it('also asks before Add as bought, and ticks what was picked', async () => {
      await render({
        'GET /foods?q=mango&limit=8': found([{ id: 8, name: 'Mango', counted_as: 'count' }])
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('mango');
      await page.getByRole('button', { name: 'Add as bought' }).click();
      await page
        .getByRole('group', { name: 'How many mangos?' })
        .getByRole('button', { name: '2', exact: true })
        .click();
      await vi.waitFor(() => expect(kinds()).toEqual(['add', 'tick']));
      expect(server.actions[0]).toMatchObject({ amount: 2 });
    });

    it('does not ask when the amount was typed', async () => {
      await render({
        'GET /foods?q=3+mango&limit=8': found([]),
        'GET /foods?q=mango&limit=8': found([{ id: 8, name: 'Mango', counted_as: 'count' }])
      });
      await page.getByRole('textbox', { name: 'Add an item' }).fill('3 mango');
      await page.getByRole('button', { name: /^Mango/ }).click();
      await vi.waitFor(() =>
        expect(server.actions[0]).toMatchObject({ kind: 'add', food_id: 8, amount: 3 })
      );
      expect(page.getByRole('group', { name: /How many/ }).elements()).toEqual([]);
    });
  });

  describe('Already have it (F117)', () => {
    async function openHave(name: string) {
      await page.getByRole('button', { name: new RegExp(`^${name}$`) }).click();
      await page.getByRole('button', { name: 'Already have it' }).click();
    }

    it('is not offered on a staple (it has Got it / Restocked, and nothing would go in)', async () => {
      copy.foods.find((f) => f.name === 'Toor dal')!.staple = true;
      await render();
      await page.getByRole('button', { name: /^Toor dal$/ }).click();
      await expect.element(page.getByRole('button', { name: 'Move to…' })).toBeVisible();
      expect(page.getByRole('button', { name: 'Already have it' }).elements()).toEqual([]);
      expect(page.getByText('Already have it').elements()).toEqual([]);
    });

    it('asks how much is at home, starting from the list amount, and where', async () => {
      await render();
      await openHave('Toor dal');
      const sheet = page.getByRole('dialog', { name: 'Already have Toor dal' });
      await expect.element(sheet).toBeVisible();
      await vi.waitFor(() =>
        expect(sheet.element().textContent).toMatch(/How much Toor dal is at home\?/)
      );
      await vi.waitFor(() =>
        expect(sheet.element().textContent).toMatch(/found at home, not bought/)
      );
      const choices = sheet.getByRole('radiogroup', { name: 'Amount at home' });
      await vi.waitFor(() =>
        expect(choices.getByRole('radio', { checked: true }).element().textContent).toMatch(/500/)
      );
      await expect.element(choices.getByRole('radio', { name: 'Other…' })).toBeVisible();
      await expect.element(sheet.getByRole('combobox', { name: 'Where' })).toBeVisible();
    });

    it('sends one found_at_home with the amount and place, and the line goes to the trolley', async () => {
      await render();
      await openHave('Toor dal');
      const sheet = page.getByRole('dialog', { name: 'Already have Toor dal' });
      await sheet.getByRole('radio', { name: /^250/ }).click();
      await sheet.getByRole('combobox', { name: 'Where' }).selectOptions('Fridge');
      await sheet.getByRole('button', { name: /^Put .* in the pantry$/ }).click();
      await vi.waitFor(() =>
        expect(server.actions[0]).toMatchObject({
          kind: 'found_at_home',
          item_id: 'i-dal',
          amount: 250,
          place_id: 1
        })
      );
      await expect
        .element(page.getByRole('status').filter({ hasText: 'Found Toor dal at home' }))
        .toBeVisible();
      expect(kinds()).toEqual(['found_at_home']);
    });

    it('Other… takes a typed amount', async () => {
      await render();
      await openHave('Toor dal');
      const sheet = page.getByRole('dialog', { name: 'Already have Toor dal' });
      await sheet.getByRole('radio', { name: 'Other…' }).click();
      await sheet.getByRole('textbox').fill('120 g');
      await sheet.getByRole('button', { name: /^Put .* in the pantry$/ }).click();
      await vi.waitFor(() =>
        expect(server.actions[0]).toMatchObject({ kind: 'found_at_home', amount: 120 })
      );
    });

    it('Other… with something unreadable says why and sends nothing', async () => {
      await render();
      await openHave('Toor dal');
      const sheet = page.getByRole('dialog', { name: 'Already have Toor dal' });
      await sheet.getByRole('radio', { name: 'Other…' }).click();
      await sheet.getByRole('textbox').fill('lots');
      await sheet.getByRole('button', { name: /^Put .* in the pantry$/ }).click();
      await expect.element(sheet.getByRole('alert')).toBeVisible();
      expect(kinds()).toEqual([]);
    });

    it('works offline: the answer waits in the queue and the line is shown as found', async () => {
      await saveCopy(null, applyChanges(null, { ...sampleCopy(), people: [], reset: true }));
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      mountShopping();
      await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
      await openHave('Toor dal');
      await page
        .getByRole('dialog', { name: 'Already have Toor dal' })
        .getByRole('button', { name: /^Put .* in the pantry$/ })
        .click();
      await vi.waitFor(async () => {
        const queue = (await readQueue()).map((e) => e.action);
        expect(queue).toMatchObject([{ kind: 'found_at_home', item_id: 'i-dal', amount: 500 }]);
      });
      await page.getByRole('button', { name: /^In the trolley · 1/ }).click();
      await expect.element(page.getByText(/found at home/)).toBeVisible();
    });
  });

  describe('In the trolley (F72, F173)', () => {
    beforeEach(() => {
      // Paneer ticked at 10:05, Coriander at 10:00, Yoghurt (bought) at 10:09.
      copy.items.find((i) => i.id === 'i-paneer')!.ticks[0]!.at = '2026-11-07T10:05:00Z';
      copy.items.find((i) => i.id === 'i-coriander')!.ticks[0]!.at = '2026-11-07T10:00:00Z';
      copy.items.find((i) => i.id === 'i-yoghurt')!.ticks = [
        tick('t-yog', { at: '2026-11-07T10:09:00Z', bought: { amount: 500, display: '500 g' } })
      ];
    });

    it('lists the most recently ticked first, one line each, with the place as a button', async () => {
      await render();
      await page.getByRole('button', { name: /^In the trolley · 3/ }).click();
      const names = page
        .getByRole('checkbox', { name: /^Untick / })
        .elements()
        .map((e) => e.getAttribute('aria-label'));
      expect(names).toEqual(['Untick Yoghurt', 'Untick Paneer', 'Untick Coriander']);
      await vi.waitFor(() =>
        expect(
          page.getByRole('button', { name: 'Change where Paneer went' }).element().textContent
        ).toMatch(/→ Fridge/)
      );
    });

    describe('a row for two lines of one ingredient (F198), offline', () => {
      const second = () =>
        item('i-paneer2', 4, {
          amount: 200,
          size_id: 5,
          display: '1 pack',
          ticks: [
            tick('t-pan2', {
              at: '2026-11-07T10:04:00Z',
              bought: { amount: 200, display: '1 pack' }
            })
          ]
        });

      async function openJoined() {
        copy.items.push(second());
        await saveCopy(null, applyChanges(null, { ...copy, people: [], reset: true }));
        vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
        mountShopping();
        await expect
          .element(page.getByRole('button', { name: 'This week main list' }))
          .toBeVisible();
        await page.getByRole('button', { name: /^In the trolley · 3/ }).click();
        expect(page.getByRole('checkbox', { name: 'Untick Paneer' }).elements()).toHaveLength(1);
      }

      it('unticking it is one toast and one Undo that ticks both lines again', async () => {
        await openJoined();
        await page.getByRole('checkbox', { name: 'Untick Paneer' }).click();
        const toast = page.getByRole('status').filter({ hasText: 'Paneer unticked' });
        await expect.element(toast).toBeVisible();
        expect(page.getByRole('status').elements()).toHaveLength(1);
        await vi.waitFor(async () =>
          expect((await readQueue()).map((e) => e.action.kind)).toEqual(['untick', 'untick'])
        );
        expect(page.getByRole('checkbox', { name: 'Tick Paneer' }).elements()).toHaveLength(2);
        await toast.getByRole('button', { name: 'Undo' }).click();
        await vi.waitFor(async () =>
          expect((await readQueue()).map((e) => e.action.kind)).toEqual([
            'untick',
            'untick',
            'undo',
            'undo'
          ])
        );
        await vi.waitFor(() =>
          expect(page.getByRole('checkbox', { name: 'Untick Paneer' }).elements()).toHaveLength(1)
        );
        expect(page.getByRole('checkbox', { name: 'Tick Paneer' }).elements()).toHaveLength(0);
      });

      it('clearing it says one item, and takes both lines out', async () => {
        await openJoined();
        await page.getByRole('button', { name: 'Clear Paneer', exact: true }).click();
        await expect
          .element(page.getByRole('status').filter({ hasText: 'Cleared 1 ticked item' }))
          .toBeVisible();
        await vi.waitFor(async () =>
          expect((await readQueue()).map((e) => e.action)).toMatchObject([
            { kind: 'clear_ticked', item_ids: ['i-paneer', 'i-paneer2'] }
          ])
        );
      });

      it('changing the place is one toast and one Undo for both lines', async () => {
        await openJoined();
        await page.getByRole('button', { name: 'Change where Paneer went' }).click();
        await page.getByRole('radio', { name: 'Freezer' }).click();
        const toast = page.getByRole('status').filter({ hasText: 'Paneer → Freezer' });
        await expect.element(toast).toBeVisible();
        expect(page.getByRole('status').elements()).toHaveLength(1);
        await vi.waitFor(async () =>
          expect((await readQueue()).map((e) => e.action.kind)).toEqual(['put_away', 'put_away'])
        );
        await toast.getByRole('button', { name: 'Undo' }).click();
        await vi.waitFor(async () =>
          expect((await readQueue()).map((e) => e.action.kind)).toEqual([
            'put_away',
            'put_away',
            'undo',
            'undo'
          ])
        );
      });
    });

    it('a line can be cleared with its own button, by keyboard (not only by swipe)', async () => {
      await render();
      await page.getByRole('button', { name: /^In the trolley · 3/ }).click();
      const clear = page.getByRole('button', { name: 'Clear Paneer', exact: true });
      await expect.element(clear).toBeVisible();
      (clear.element() as HTMLElement).focus();
      await userEvent.keyboard('{Enter}');
      await vi.waitFor(() =>
        expect(server.actions).toMatchObject([{ kind: 'clear_ticked', item_ids: ['i-paneer'] }])
      );
    });

    it('a found line says so under its name', async () => {
      copy.items.find((i) => i.id === 'i-dal')!.ticks = [
        tick('t-dal', { found: true, place_id: 3, bought: { amount: 250, display: '250 g' } })
      ];
      await render();
      await page.getByRole('button', { name: /^In the trolley · 1/ }).click();
      await expect.element(page.getByText('250 g · found at home')).toBeVisible();
      await page.getByRole('button', { name: 'Change where Toor dal went' }).click();
      expect(page.getByRole('button', { name: 'Different pack?' }).elements()).toHaveLength(0);
    });
  });

  describe('Different pack? (F153)', () => {
    it('can go back to the planned amount after a different one was bought', async () => {
      // Planned 6 spring onions, ticked and then changed to 1.
      const row = copy.items.find((i) => i.id === 'i-onions')!;
      row.amount = 6;
      row.display = '6';
      row.ticks = [tick('t-on', { place_id: 1, bought: { amount: 1, display: '1' } })];
      await render();
      await page.getByRole('button', { name: /^In the trolley · 3/ }).click();
      await page.getByRole('button', { name: 'Change where Onions went' }).click();
      await page.getByRole('button', { name: 'Different pack?' }).click();
      const sheet = page.getByRole('group', { name: 'What did you buy?' });
      // What was bought is the one picked; the planned amount is another choice.
      await vi.waitFor(() =>
        expect(sheet.getByRole('radio', { checked: true }).element().textContent).toMatch(/1\s×\s1/)
      );
      await sheet.getByRole('radio', { name: /^1\s×\s6$/ }).click();
      await sheet.getByRole('button', { name: 'Done' }).click();
      await vi.waitFor(() =>
        expect(server.actions.at(-1)).toMatchObject({
          kind: 'different_pack',
          tick_id: 't-on',
          count: 1,
          pack: 6
        })
      );
    });

    it('Done with what was bought still picked sends nothing', async () => {
      const row = copy.items.find((i) => i.id === 'i-onions')!;
      row.amount = 6;
      row.display = '6';
      row.ticks = [tick('t-on', { place_id: 1, bought: { amount: 1, display: '1' } })];
      await render();
      await page.getByRole('button', { name: /^In the trolley · 3/ }).click();
      await page.getByRole('button', { name: 'Change where Onions went' }).click();
      await page.getByRole('button', { name: 'Different pack?' }).click();
      await page
        .getByRole('group', { name: 'What did you buy?' })
        .getByRole('button', { name: 'Done' })
        .click();
      expect(kinds()).toEqual([]);
    });
  });

  describe('the amount box (F60)', () => {
    it('a line with no amount offers quick amounts, which fill the box', async () => {
      await render();
      await page.getByRole('button', { name: 'Add amount for Kitchen roll' }).click();
      const quick = page.getByRole('group', { name: 'Quick amounts for Kitchen roll' });
      await expect.element(quick.getByRole('button', { name: /^250/ })).toBeVisible();
      await expect.element(quick.getByRole('button', { name: /^500/ })).toBeVisible();
      await expect.element(quick.getByRole('button', { name: /^1.kg/ })).toBeVisible();
      await quick.getByRole('button', { name: /^500/ }).click();
      await expect.element(page.getByRole('textbox', { name: 'Amount' })).toHaveValue('500 g');
    });

    it('a line with an amount has none', async () => {
      await render();
      await page.getByRole('button', { name: /^Toor dal$/ }).click();
      expect(page.getByRole('group', { name: /^Quick amounts/ }).elements()).toEqual([]);
    });
  });

  describe('Usual pack? and Make it a staple? on the phone', () => {
    it('offers the usual packs on a line with no size, and a staple link when the server says so', async () => {
      const dal = copy.items.find((i) => i.id === 'i-dal')!;
      dal.pack = {
        suggestions: [
          { amount: 200, amount_text: '200 g' },
          { amount: 500, amount_text: '500 g' }
        ] as never
      };
      await render({
        'GET /shopping/lists/main': [
          200,
          {
            shops: [
              {
                aisles: [
                  {
                    items: [
                      { id: 'i-dal', why: '', staple_offer: false },
                      { id: 'i-yoghurt', why: '', staple_offer: true }
                    ]
                  }
                ],
                in_trolley: []
              }
            ]
          }
        ]
      });
      const picks = page.getByRole('group', { name: 'Usual pack for Toor dal?' });
      await expect.element(picks.getByRole('button', { name: '200 g' })).toBeVisible();
      await expect.element(page.getByText('500 g needed · no pack size yet')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Make it a staple?' })).toBeVisible();
    });
  });
});

void item;
