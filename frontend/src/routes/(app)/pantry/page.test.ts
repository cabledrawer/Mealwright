import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { addToPantry } from '$lib/addToPantry.svelte';
import { PLACES, changeOf, fakeApi, toorDal, type FakeRequest } from '$lib/testing/fakeApi';
import { samplePantry } from '$lib/testing/fakePantry';
import { toasts } from '$lib/toast.svelte';
import { handleUndoKey, undoHistory } from '$lib/undo.svelte';
import Pantry from './+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const UUID = /^[0-9a-f-]{36}$/;
const written = (summary: string) =>
  [200, { change: changeOf(700, summary), groups: [], short_by: null }] as [number, unknown];

describe('the Pantry page', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];
  let sample: ReturnType<typeof samplePantry>;

  const gone = new Set<number>();

  function routes(extra: Record<string, [number, unknown]> = {}) {
    requests = fakeApi({
      'GET /pantry': [200, sample.pantry],
      // Like the server: what was used is gone from Use soon.
      'GET /pantry/use-soon': () => [
        200,
        { lots: sample.useSoon.filter((lot) => !gone.has(lot.id)) }
      ],
      'GET /changes?limit=8&area=pantry': [
        200,
        {
          changes: [
            changeOf(31, 'Used 200 g Toor dal'),
            {
              ...changeOf(30, 'Undid: Binned 1 pack paneer'),
              can_undo: false,
              totals: [
                {
                  food_id: 21,
                  name: 'Paneer',
                  place_before: { id: 1, name: 'Fridge' },
                  place_after: { id: 1, name: 'Fridge' },
                  before: { amount: 0, display: '0 g' },
                  after: { amount: 200, display: '1 pack · 200 g' }
                }
              ]
            }
          ],
          next: null
        }
      ],
      'POST /changes/700/undo': [
        200,
        { result: 'done', message: '', change: changeOf(702, 'Undid'), food: null }
      ],
      'POST /changes/31/undo': [
        200,
        { result: 'done', message: '', change: changeOf(32, 'Undid'), food: null }
      ],
      [`POST /stock/${sample.spinach.id}/used`]: () => {
        gone.add(sample.spinach.id);
        return written('Used 200 g spinach');
      },
      [`POST /stock/${sample.paneer[0]!.id}/move`]: written('Moved Paneer → Freezer'),
      [`POST /stock/${sample.yoghurt.id}/left`]: written('Yoghurt: ½ tub → about ¼ tub'),
      'GET /foods/7': [200, toorDal()],
      'POST /foods/7/used': written('Used 200 g Toor dal'),
      'GET /places': [200, PLACES],
      'POST /stock': [
        201,
        { change: changeOf(701, 'Added 2 packets Toor dal → Cupboard'), groups: [], short_by: null }
      ],
      'GET /foods?q=toor&limit=8': [
        200,
        {
          foods: [{ id: 7, name: 'Toor dal', other_names: [], matched_name: null, maybe_same: [] }],
          counts: {},
          total: 1,
          next: null
        }
      ],
      ...extra
    });
  }

  async function render(width: number) {
    await page.viewport(width, 900);
    component = mount(Pantry, { target: document.body });
    flushSync();
    await expect.element(page.getByRole('heading', { name: 'Pantry', level: 1 })).toBeVisible();
  }

  beforeEach(() => {
    sample = samplePantry();
    gone.clear();
    undoHistory.clear();
    toasts.dismiss();
    routes();
  });

  afterEach(() => {
    addToPantry.close();
    flushSync();
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  it('desktop: every place as a column, with Use soon, Staples and Recent changes beside', async () => {
    await render(1300);
    for (const name of ['Fridge', 'Freezer', 'Cupboard', 'Spice rack']) {
      await expect.element(page.getByRole('heading', { name, level: 2 })).toBeVisible();
    }
    await expect.element(page.getByText('6 items · 2 use soon')).toBeVisible();
    await expect.element(page.getByText(/300 g · running low/)).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: 'Undo: Used 200 g Toor dal' }))
      .toBeVisible();
    // "+ List" works in 0.3 (on running-low rows). Not until later milestones: the rest.
    await expect
      .element(page.getByRole('button', { name: 'Add Basmati rice to the shopping list' }))
      .toBeVisible();
    expect(page.getByText(/Recipes for these/).elements()).toHaveLength(0);
    expect(page.getByText('Tubs', { exact: true }).elements()).toHaveLength(0);
  });

  it('phone: + Staple makes a brand-new staple and records no stock', async () => {
    routes({
      'POST /foods': [
        201,
        {
          food: toorDal({ id: 99, name: 'Salt', staple: true }),
          change: changeOf(710, 'Added Salt')
        }
      ]
    });
    await render(390);
    await page.getByRole('button', { name: '+ Staple' }).click();
    await page.getByRole('searchbox', { name: 'Make an ingredient a staple' }).fill('Salt');
    await page.getByRole('button', { name: '+ New ingredient: “Salt”' }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'POST' && r.path === '/foods')?.body).toEqual({
        name: 'Salt',
        staple: true
      })
    );
    expect(requests.some((r) => r.path === '/stock' || r.path.startsWith('/stock/'))).toBe(false);
  });

  it('phone: tabs All · Fridge · Freezer · Cupboard · More, with Use soon under More', async () => {
    await render(390);
    const tabs = page.getByRole('tablist', { name: 'Where' });
    await expect
      .element(tabs.getByRole('tab', { name: 'All' }))
      .toHaveAttribute('aria-selected', 'true');
    const names = (await tabs.getByRole('tab').all()).map((t) => t.element().textContent?.trim());
    expect(names).toEqual(['All', 'Fridge', 'Freezer', 'Cupboard', 'More']);
    const box = (tabs.element() as HTMLElement).getBoundingClientRect();
    expect(box.right).toBeLessThanOrEqual(390);
    // More holds Spice rack and Use soon.
    await tabs.getByRole('tab', { name: /More/ }).click();
    const more = page.getByRole('list', { name: 'More' });
    await expect.element(more.getByRole('button', { name: 'Spice rack' })).toBeVisible();
    await more.getByRole('button', { name: 'Use soon' }).click();
    await expect
      .element(tabs.getByRole('tab', { name: /Use soon/ }))
      .toHaveAttribute('aria-selected', 'true');
    await expect.element(page.getByRole('button', { name: /Spinach · Today/ })).toBeVisible();
  });

  describe('searching the pantry', () => {
    /** The pantry as the server answers a search: only what matched. */
    function searchRoutes(query: string, keep: number[], matched: Record<number, string> = {}) {
      const pantry = structuredClone(sample.pantry);
      for (const place of pantry.places) {
        place.groups = place.groups.filter((g) => keep.includes(g.food.id));
        place.items = place.groups.length;
      }
      routes({
        [`GET /pantry?q=${query}`]: [200, pantry],
        [`GET /foods?q=${query}&limit=500`]: [
          200,
          {
            foods: keep.map((id) => ({
              id,
              name: pantry.places.flatMap((p) => p.groups).find((g) => g.food.id === id)!.food.name,
              other_names: [],
              matched_name: matched[id] ?? null,
              maybe_same: []
            })),
            counts: {},
            total: keep.length,
            next: null
          }
        ]
      });
    }

    const search = () => page.getByRole('searchbox', { name: 'Find in pantry' });

    it('desktop: one list with each place, "also called", and no per-place lines', async () => {
      searchRoutes('thuvaram', [7], { 7: 'thuvaram paruppu' });
      await render(1300);
      await expect.element(page.getByRole('heading', { name: 'Fridge', level: 2 })).toBeVisible();
      await search().fill('thuvaram');
      const list = page.getByRole('list', { name: 'Found in the pantry' });
      await expect.element(list).toBeVisible();
      await expect.element(list.getByRole('button', { name: /Toor dal · Cupboard/ })).toBeVisible();
      await expect.element(list.getByText('also called thuvaram paruppu')).toBeVisible();
      // The columns, and their "Nothing in the Fridge" lines, are gone.
      expect(page.getByRole('heading', { name: 'Fridge', level: 2 }).elements()).toHaveLength(0);
      expect(page.getByText(/Nothing in the/).elements()).toHaveLength(0);
      expect(page.getByText(/Nothing called/).elements()).toHaveLength(0);
      // Clearing the search puts the columns back.
      await search().fill('');
      await expect.element(page.getByRole('heading', { name: 'Fridge', level: 2 })).toBeVisible();
      expect(page.getByRole('list', { name: 'Found in the pantry' }).elements()).toHaveLength(0);
    });

    it('a match on the food’s own name has no "also called"', async () => {
      searchRoutes('toor', [7]);
      await render(1300);
      await search().fill('toor');
      await expect.element(page.getByRole('button', { name: /Toor dal · Cupboard/ })).toBeVisible();
      expect(page.getByText(/also called/).elements()).toHaveLength(0);
    });

    it('says "Nothing called …" once when nothing matches anywhere', async () => {
      searchRoutes('zzz', []);
      await render(1300);
      await search().fill('zzz');
      await expect.element(page.getByText('Nothing called “zzz”.')).toBeVisible();
      expect(page.getByText(/Nothing called/).elements()).toHaveLength(1);
      expect(page.getByText(/Nothing in the/).elements()).toHaveLength(0);
    });

    it('phone: the same one list, instead of the tabs, and nothing sideways', async () => {
      searchRoutes('thuvaram', [7, 20], { 7: 'thuvaram paruppu' });
      await render(1300);
      await search().fill('thuvaram');
      await expect.element(page.getByRole('list', { name: 'Found in the pantry' })).toBeVisible();
      // The page is now narrow: a phone, with the search still showing.
      await page.viewport(390, 900);
      const list = page.getByRole('list', { name: 'Found in the pantry' });
      await expect.element(list.getByRole('button', { name: /Toor dal · Cupboard/ })).toBeVisible();
      await expect.element(list.getByRole('button', { name: /Spinach · Fridge/ })).toBeVisible();
      await expect.element(list.getByText('also called thuvaram paruppu')).toBeVisible();
      expect(page.getByRole('tablist').elements()).toHaveLength(0);
      expect(page.getByText(/Nothing in the/).elements()).toHaveLength(0);
      const box = (list.element() as HTMLElement).getBoundingClientRect();
      expect(box.right).toBeLessThanOrEqual(390);
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390);
    });

    describe('phone: the search field above the tabs', () => {
      const phoneSearch = () => page.getByRole('searchbox', { name: 'Search pantry' });

      it('is above the place tabs and has the accessible name "Search pantry"', async () => {
        routes();
        await render(390);
        await expect.element(phoneSearch()).toBeVisible();
        await expect.element(page.getByRole('tablist')).toBeVisible();
        const field = phoneSearch().element().getBoundingClientRect();
        const tabs = page.getByRole('tablist').element().getBoundingClientRect();
        expect(field.bottom).toBeLessThanOrEqual(tabs.top);
        // One search field, not two.
        expect(page.getByRole('searchbox').elements()).toHaveLength(1);
        expect(page.getByRole('searchbox', { name: 'Find in pantry' }).elements()).toHaveLength(0);
        expect(field.right).toBeLessThanOrEqual(390);
        // A touch target of at least 44 px.
        expect(field.height).toBeGreaterThanOrEqual(44);
      });

      it('typing shows the one list, with each place and "also called"', async () => {
        searchRoutes('thuvaram', [7, 20], { 7: 'thuvaram paruppu' });
        await render(390);
        await phoneSearch().fill('thuvaram');
        const list = page.getByRole('list', { name: 'Found in the pantry' });
        await expect.element(list).toBeVisible();
        await expect
          .element(list.getByRole('button', { name: /Toor dal · Cupboard/ }))
          .toBeVisible();
        await expect.element(list.getByRole('button', { name: /Spinach · Fridge/ })).toBeVisible();
        // Only the match by another name says "also called".
        await expect.element(list.getByText('also called thuvaram paruppu')).toBeVisible();
        expect(page.getByText(/also called/).elements()).toHaveLength(1);
        expect(page.getByRole('tablist').elements()).toHaveLength(0);
        // The field stays, so the search can be changed or cleared.
        await expect.element(phoneSearch()).toHaveValue('thuvaram');
        await phoneSearch().fill('');
        await expect.element(page.getByRole('tablist')).toBeVisible();
        expect(page.getByRole('list', { name: 'Found in the pantry' }).elements()).toHaveLength(0);
      });

      it('a match on the ingredient’s own name has no "also called"', async () => {
        searchRoutes('toor', [7]);
        await render(390);
        await phoneSearch().fill('toor');
        await expect
          .element(page.getByRole('button', { name: /Toor dal · Cupboard/ }))
          .toBeVisible();
        expect(page.getByText(/also called/).elements()).toHaveLength(0);
      });
    });

    it('phone: with nothing found, it says so once', async () => {
      searchRoutes('zzz', []);
      await render(1300);
      await search().fill('zzz');
      await expect.element(page.getByText('Nothing called “zzz”.')).toBeVisible();
      await page.viewport(390, 900);
      await expect.element(page.getByText('Nothing called “zzz”.')).toBeVisible();
      expect(page.getByText(/Nothing called/).elements()).toHaveLength(1);
      expect(page.getByText(/Nothing in the/).elements()).toHaveLength(0);
    });
  });

  it('Used takes it off at once, saves with a change ID, and offers Undo', async () => {
    await render(1300);
    const side = page.getByRole('complementary', { name: /Use soon/ });
    await expect.element(side.getByRole('button', { name: /^Spinach/ })).toBeVisible();
    await side.getByRole('button', { name: 'Used' }).first().click();
    await expect.element(side.getByRole('button', { name: /^Spinach/ })).not.toBeInTheDocument();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === `/stock/${sample.spinach.id}/used`)).toBeDefined()
    );
    expect(
      requests.find((r) => r.path === `/stock/${sample.spinach.id}/used`)!.headers[
        'idempotency-key'
      ]
    ).toMatch(UUID);
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Used 200 g spinach'));
    expect(toasts.current?.action?.label).toBe('Undo');
  });

  it('Ctrl+Z after a pantry change says what was undone', async () => {
    await render(1300);
    const side = page.getByRole('complementary', { name: /Use soon/ });
    await side.getByRole('button', { name: 'Used' }).first().click();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Used 200 g spinach'));
    document.body.addEventListener('keydown', handleUndoKey, { once: true });
    document.body.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true, cancelable: true })
    );
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Undone: Used 200 g spinach'));
    expect(requests.some((r) => r.path === '/changes/700/undo')).toBe(true);
  });

  it('a failed change puts it back and says so calmly', async () => {
    routes({ [`POST /stock/${sample.spinach.id}/used`]: [503, { detail: 'Busy' }] });
    await render(1300);
    const side = page.getByRole('complementary', { name: /Use soon/ });
    await side.getByRole('button', { name: 'Used' }).first().click();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Couldn’t save — try again'));
    await expect.element(side.getByRole('button', { name: /^Spinach/ })).toBeVisible();
  });

  it('an open pack, tapped, has the ¼ · ½ · ¾ · Full picks', async () => {
    await render(1300);
    // Not until it's tapped.
    expect(page.getByRole('radiogroup').elements()).toHaveLength(0);
    await page.getByRole('button', { name: /^Yoghurt/ }).click();
    await page.getByRole('list', { name: 'Packets of Yoghurt' }).getByRole('button').click();
    const menu = page.getByRole('dialog', { name: /Yoghurt/ });
    const picks = menu.getByRole('radiogroup', { name: 'How much is left? Best guess is fine.' });
    await expect
      .element(picks.getByRole('radio', { name: '½ left' }))
      .toHaveAttribute('aria-checked', 'true');
    await picks.getByRole('radio', { name: '¼ left' }).click();
    await expect
      .element(picks.getByRole('radio', { name: '¼ left' }))
      .toHaveAttribute('aria-checked', 'true');
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === `/stock/${sample.yoghurt.id}/left`)?.body).toEqual({
        fraction: 0.25
      })
    );
  });

  it('a full, unopened pack has the picks too, with Full chosen', async () => {
    await render(1300);
    await page.getByRole('button', { name: /^Paneer 2 packs/ }).click();
    await page.getByRole('list', { name: 'Packets of Paneer' }).getByRole('button').first().click();
    const menu = page.getByRole('dialog', { name: /Paneer/ });
    const picks = menu.getByRole('radiogroup', { name: 'How much is left? Best guess is fine.' });
    await expect
      .element(picks.getByRole('radio', { name: 'Full' }))
      .toHaveAttribute('aria-checked', 'true');
    await expect.element(picks.getByRole('radio', { name: '½ left' })).toBeVisible();
    await picks.getByRole('radio', { name: '½ left' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.path.startsWith('/stock/') && r.path.endsWith('/left'))).toBe(
        true
      )
    );
  });

  it('Undo in Recent changes undoes that change', async () => {
    await render(1300);
    await page.getByRole('button', { name: 'Undo: Used 200 g Toor dal' }).click();
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/changes/31/undo')).toBe(true));
    // An Undo row has no Undo of its own, and shows what it did, before → after.
    expect(
      page.getByRole('button', { name: 'Undo: Undid: Binned 1 pack paneer' }).elements()
    ).toHaveLength(0);
    await expect.element(page.getByText('Paneer: 0 g → 1 pack · 200 g')).toBeVisible();
  });

  it('phone: the round + button opens the Add to pantry sheet when online', async () => {
    await render(390);
    await page.getByRole('button', { name: 'Add to pantry', exact: true }).click();
    await expect.element(page.getByRole('dialog', { name: 'Add to pantry' })).toBeVisible();
    expect(addToPantry.open).toBe(true);
    // Online, nothing says it needs the server.
    expect(toasts.current).toBeNull();
  });

  it('+ Add to pantry: food, 2 packets, +3 days, where it lives', async () => {
    await render(1300);
    await page.getByRole('button', { name: '+ Add to pantry' }).click();
    const sheet = page.getByRole('dialog', { name: 'Add to pantry' });
    // It starts in the "What" box.
    await expect
      .element(sheet.getByRole('searchbox', { name: 'Find an ingredient' }))
      .toHaveFocus();
    await sheet.getByRole('searchbox', { name: 'Find an ingredient' }).fill('toor');
    await sheet.getByRole('button', { name: 'Toor dal' }).click();
    await sheet.getByRole('radio', { name: '2 packets' }).click();
    await sheet.getByRole('radio', { name: '+3 days' }).click();
    await expect.element(sheet.getByLabelText(/^Where/)).toHaveDisplayValue('Cupboard');
    await userEvent.click(sheet.getByRole('button', { name: 'Add to pantry' }));
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'POST' && r.path === '/stock')).toBeDefined()
    );
    expect(requests.find((r) => r.path === '/stock')!.body).toEqual({
      food_id: 7,
      amount: { amount: 2, size_id: 12 },
      place_id: 3,
      use_by: '2026-10-20'
    });
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Added 2 packets Toor dal → Cupboard')
    );
  });

  describe('+ Add to pantry: the "Pick a date" chip', () => {
    async function openSheet() {
      await render(1300);
      await page.getByRole('button', { name: '+ Add to pantry' }).click();
      const sheet = page.getByRole('dialog', { name: 'Add to pantry' });
      await sheet.getByRole('searchbox', { name: 'Find an ingredient' }).fill('toor');
      await sheet.getByRole('button', { name: 'Toor dal' }).click();
      await sheet.getByRole('radio', { name: '2 packets' }).click();
      return sheet;
    }

    /** Add it, and say what use_by was sent (undefined when none). */
    async function addAndRead(sheet: ReturnType<typeof page.getByRole>) {
      await userEvent.click(sheet.getByRole('button', { name: 'Add to pantry' }));
      await vi.waitFor(() =>
        expect(requests.find((r) => r.method === 'POST' && r.path === '/stock')).toBeDefined()
      );
      return (requests.find((r) => r.path === '/stock')!.body as { use_by?: string }).use_by;
    }

    const input = (sheet: ReturnType<typeof page.getByRole>) =>
      sheet.element().querySelector<HTMLInputElement>('[data-use-by-input]')!;

    /** What the device's picker does when a date is chosen. */
    function choosePicked(sheet: ReturnType<typeof page.getByRole>, value: string) {
      const field = input(sheet);
      field.value = value;
      field.dispatchEvent(new Event('change', { bubbles: true }));
    }

    it('opens the date picker at once, with no separate Date field', async () => {
      const shown = vi.spyOn(HTMLInputElement.prototype, 'showPicker').mockImplementation(() => {});
      try {
        const sheet = await openSheet();
        expect(sheet.getByLabelText('Date', { exact: true }).elements()).toHaveLength(0);
        await sheet.getByRole('radio', { name: 'Pick a date' }).click();
        expect(shown).toHaveBeenCalledOnce();
        // The picker is the chip's own; its earliest date is today.
        expect(input(sheet).min).toBe('2026-10-17');
      } finally {
        shown.mockRestore();
      }
    });

    it('once a date is chosen, the chip shows it with a calendar icon, and it is sent', async () => {
      const sheet = await openSheet();
      choosePicked(sheet, '2026-10-24');
      const chip = sheet.getByRole('radio', { name: 'Sat 24 Oct' });
      await expect.element(chip).toHaveAttribute('aria-checked', 'true');
      expect(chip.element().querySelector('svg')).not.toBeNull();
      expect(sheet.getByRole('radio', { name: 'No date' }).element()).toHaveAttribute(
        'aria-checked',
        'false'
      );
      // Same height as the other chips.
      const high = (name: string) =>
        sheet.getByRole('radio', { name }).element().getBoundingClientRect().height;
      expect(high('Sat 24 Oct')).toBe(high('Today'));
      expect(await addAndRead(sheet)).toBe('2026-10-24');
    });

    it('tapping it again changes the date', async () => {
      const shown = vi.spyOn(HTMLInputElement.prototype, 'showPicker').mockImplementation(() => {});
      try {
        const sheet = await openSheet();
        choosePicked(sheet, '2026-10-24');
        await sheet.getByRole('radio', { name: 'Sat 24 Oct' }).click();
        expect(shown).toHaveBeenCalledOnce();
        choosePicked(sheet, '2026-11-02');
        await expect
          .element(sheet.getByRole('radio', { name: 'Mon 2 Nov' }))
          .toHaveAttribute('aria-checked', 'true');
        expect(sheet.getByRole('radio', { name: 'Sat 24 Oct' }).elements()).toHaveLength(0);
        expect(await addAndRead(sheet)).toBe('2026-11-02');
      } finally {
        shown.mockRestore();
      }
    });

    for (const [chip, expected] of [
      ['No date', undefined],
      ['Today', '2026-10-17'],
      ['+3 days', '2026-10-20'],
      ['+1 week', '2026-10-24']
    ] as const) {
      it(`choosing "${chip}" clears the picked date`, async () => {
        const sheet = await openSheet();
        choosePicked(sheet, '2026-12-01');
        await expect
          .element(sheet.getByRole('radio', { name: 'Tue 1 Dec' }))
          .toHaveAttribute('aria-checked', 'true');
        await sheet.getByRole('radio', { name: chip }).click();
        await expect.element(sheet.getByRole('radio', { name: 'Pick a date' })).toBeVisible();
        expect(input(sheet).value).toBe('');
        expect(await addAndRead(sheet)).toBe(expected);
      });
    }

    it('cancelling the picker leaves everything as it was', async () => {
      const shown = vi.spyOn(HTMLInputElement.prototype, 'showPicker').mockImplementation(() => {});
      try {
        const sheet = await openSheet();
        await sheet.getByRole('radio', { name: '+3 days' }).click();
        // Open the picker and cancel: no change comes back.
        await sheet.getByRole('radio', { name: 'Pick a date' }).click();
        expect(shown).toHaveBeenCalledOnce();
        await expect
          .element(sheet.getByRole('radio', { name: '+3 days' }))
          .toHaveAttribute('aria-checked', 'true');
        await expect.element(sheet.getByRole('radio', { name: 'Pick a date' })).toBeVisible();
        expect(sheet.getByRole('radio', { name: 'Pick a date' }).element()).toHaveAttribute(
          'aria-checked',
          'false'
        );
        expect(input(sheet).value).toBe('');
        expect(await addAndRead(sheet)).toBe('2026-10-20');
      } finally {
        shown.mockRestore();
      }
    });

    it('cancelling with no date chosen saves no date', async () => {
      const shown = vi.spyOn(HTMLInputElement.prototype, 'showPicker').mockImplementation(() => {});
      try {
        const sheet = await openSheet();
        await sheet.getByRole('radio', { name: 'Pick a date' }).click(); // cancelled
        expect(await addAndRead(sheet)).toBeUndefined();
      } finally {
        shown.mockRestore();
      }
    });

    it('cancelling after a date was chosen keeps that date', async () => {
      const shown = vi.spyOn(HTMLInputElement.prototype, 'showPicker').mockImplementation(() => {});
      try {
        const sheet = await openSheet();
        choosePicked(sheet, '2026-10-24');
        await sheet.getByRole('radio', { name: 'Sat 24 Oct' }).click(); // cancelled
        await expect
          .element(sheet.getByRole('radio', { name: 'Sat 24 Oct' }))
          .toHaveAttribute('aria-checked', 'true');
        expect(await addAndRead(sheet)).toBe('2026-10-24');
      } finally {
        shown.mockRestore();
      }
    });

    it('a date before today, or one cleared in the picker, is not kept', async () => {
      const sheet = await openSheet();
      choosePicked(sheet, '2026-10-01');
      await expect
        .element(sheet.getByRole('radio', { name: 'Pick a date' }))
        .toHaveAttribute('aria-checked', 'false');
      choosePicked(sheet, '2026-10-24');
      choosePicked(sheet, '');
      await expect
        .element(sheet.getByRole('radio', { name: 'No date' }))
        .toHaveAttribute('aria-checked', 'true');
      expect(await addAndRead(sheet)).toBeUndefined();
    });

    it('arrow keys choose each chip as they move, like the other chip groups', async () => {
      const sheet = await openSheet();
      const chip = (name: string) => sheet.getByRole('radio', { name });
      (chip('No date').element() as HTMLElement).focus();
      for (const name of ['Today', '+3 days', '+1 week']) {
        await userEvent.keyboard('{ArrowRight}');
        await expect.element(chip(name)).toHaveFocus();
        await expect.element(chip(name)).toHaveAttribute('aria-checked', 'true');
      }
      await userEvent.keyboard('{ArrowLeft}');
      await expect.element(chip('+3 days')).toHaveAttribute('aria-checked', 'true');
      expect(await addAndRead(sheet)).toBe('2026-10-20');
    });

    it('arrowing onto "Pick a date" does not open the picker or change the chosen chip', async () => {
      const shown = vi.spyOn(HTMLInputElement.prototype, 'showPicker').mockImplementation(() => {});
      const clicked = vi.fn();
      try {
        const sheet = await openSheet();
        sheet.element().addEventListener('click', clicked, true);
        await sheet.getByRole('radio', { name: '+1 week' }).click();
        shown.mockClear();
        clicked.mockClear();
        await userEvent.keyboard('{ArrowRight}');
        await expect.element(sheet.getByRole('radio', { name: 'Pick a date' })).toHaveFocus();
        expect(shown).not.toHaveBeenCalled();
        expect(clicked).not.toHaveBeenCalled();
        // +1 week is still the chosen one.
        await expect
          .element(sheet.getByRole('radio', { name: '+1 week' }))
          .toHaveAttribute('aria-checked', 'true');
        expect(sheet.getByRole('radio', { name: 'Pick a date' }).element()).toHaveAttribute(
          'aria-checked',
          'false'
        );
        expect(input(sheet).value).toBe('');
      } finally {
        shown.mockRestore();
      }
    });

    for (const key of [' ', '{Enter}']) {
      it(`${key === ' ' ? 'Space' : 'Enter'} on "Pick a date" opens the picker`, async () => {
        const shown = vi
          .spyOn(HTMLInputElement.prototype, 'showPicker')
          .mockImplementation(() => {});
        try {
          const sheet = await openSheet();
          (sheet.getByRole('radio', { name: '+1 week' }).element() as HTMLElement).focus();
          await userEvent.keyboard('{ArrowRight}');
          expect(shown).not.toHaveBeenCalled();
          await userEvent.keyboard(key);
          expect(shown).toHaveBeenCalledOnce();
        } finally {
          shown.mockRestore();
        }
      });
    }

    it('the see-through date field is hidden from assistive tech: only the chip is announced', async () => {
      const sheet = await openSheet();
      const field = input(sheet);
      expect(field.getAttribute('aria-hidden')).toBe('true');
      expect(field.tabIndex).toBe(-1);
      expect(field.hasAttribute('aria-label')).toBe(false);
      // Nothing about a date field is in the accessibility tree; the chip is.
      expect(sheet.getByLabelText('Use-by date').elements()).toHaveLength(0);
      await expect.element(sheet.getByRole('radio', { name: 'Pick a date' })).toBeVisible();
      choosePicked(sheet, '2026-10-24');
      await expect.element(sheet.getByRole('radio', { name: 'Sat 24 Oct' })).toBeVisible();
      expect(field.getAttribute('aria-hidden')).toBe('true');
    });
  });

  it('+ Add to pantry: a "Today" use-by, and an example that suits the unit', async () => {
    await render(1300);
    await page.getByRole('button', { name: '+ Add to pantry' }).click();
    const sheet = page.getByRole('dialog', { name: 'Add to pantry' });
    await sheet.getByRole('searchbox', { name: 'Find an ingredient' }).fill('toor');
    await sheet.getByRole('button', { name: 'Toor dal' }).click();
    await sheet.getByRole('radio', { name: 'Other amount' }).click();
    const amount = sheet.getByRole('textbox', { name: 'Amount' });
    const unit = sheet.getByRole('combobox', { name: 'Unit' });
    await userEvent.selectOptions(unit, 'g');
    await expect.element(amount).toHaveAttribute('placeholder', '200');
    await userEvent.selectOptions(unit, 'kg');
    await expect.element(amount).toHaveAttribute('placeholder', '1');
    await userEvent.selectOptions(unit, 'packet');
    await expect.element(amount).toHaveAttribute('placeholder', '1');
    await userEvent.selectOptions(unit, 'g');
    await amount.fill('300');
    await sheet.getByRole('radio', { name: 'Today' }).click();
    await userEvent.click(sheet.getByRole('button', { name: 'Add to pantry' }));
    await vi.waitFor(() => expect(requests.find((r) => r.path === '/stock')).toBeDefined());
    expect(requests.find((r) => r.path === '/stock')!.body).toMatchObject({
      amount: { amount: 300, unit: 'g' },
      use_by: '2026-10-17'
    });
  });

  it('"Used" waits until an amount is typed, and the packet lines look tappable', async () => {
    await render(1300);
    await page.getByRole('button', { name: /^Toor dal/ }).click();
    const item = page.getByRole('listitem').filter({ hasText: 'Toor dal' });
    const used = item.getByRole('button', { name: 'Used', exact: true }).last();
    await expect.element(used).toBeDisabled();
    await page.getByLabelText('Used some (g)').fill('0');
    await expect.element(used).toBeDisabled();
    await page.getByLabelText('Used some (g)').fill('200');
    await expect.element(used).toBeEnabled();
    // The packet lines open a menu, so they carry an arrow and are at least 44 px tall.
    const packet = page
      .getByRole('list', { name: 'Packets of Toor dal' })
      .getByRole('button')
      .first();
    const box = packet.element().getBoundingClientRect();
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(packet.element().querySelector('.lot-go svg')).not.toBeNull();
  });

  it('"Used some" on a food takes from its packets, oldest first', async () => {
    await render(1300);
    await page.getByRole('button', { name: /^Toor dal/ }).click();
    await page.getByLabelText('Used some (g)').fill('200');
    await page
      .getByRole('listitem')
      .filter({ hasText: 'Toor dal' })
      .getByRole('button', { name: 'Used', exact: true })
      .last()
      .click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === '/foods/7/used')?.body).toEqual({
        amount: { amount: 200, unit: 'g' },
        place_id: 3
      })
    );
  });

  it("shows the server's sentence when there's nothing left to use", async () => {
    routes({
      'POST /foods/7/used': [
        409,
        { detail: 'There’s no Toor dal in the Cupboard to use.', code: 'nothing_left' }
      ]
    });
    await render(1300);
    await page.getByRole('button', { name: /^Toor dal/ }).click();
    await page.getByLabelText('Used some (g)').fill('200');
    await page
      .getByRole('listitem')
      .filter({ hasText: 'Toor dal' })
      .getByRole('button', { name: 'Used', exact: true })
      .last()
      .click();
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('There’s no Toor dal in the Cupboard to use.')
    );
  });

  it('phone: Recent changes shows the last 3, with Undo, and Show more', async () => {
    routes({
      'GET /changes?limit=8&area=pantry': [
        200,
        {
          changes: [1, 2, 3, 4].map((n) => changeOf(40 + n, `Used ${n}00 g Toor dal`)),
          next: null
        }
      ]
    });
    await render(390);
    const recent = page.getByRole('region', { name: 'Recent changes' });
    await expect
      .element(recent.getByRole('button', { name: 'Undo: Used 100 g Toor dal' }))
      .toBeVisible();
    await expect
      .element(recent.getByRole('button', { name: 'Undo: Used 300 g Toor dal' }))
      .toBeVisible();
    expect(
      recent.getByRole('button', { name: 'Undo: Used 400 g Toor dal' }).elements()
    ).toHaveLength(0);
    await recent.getByRole('button', { name: 'Show more' }).click();
    await expect
      .element(recent.getByRole('button', { name: 'Undo: Used 400 g Toor dal' }))
      .toBeVisible();
  });

  it('a packet’s menu: by keyboard, with Esc back to the packet, and Used', async () => {
    await render(1300);
    await page
      .getByRole('region', { name: "What's in the pantry" })
      .getByRole('button', { name: /^Paneer/ })
      .click();
    const packets = page.getByRole('list', { name: 'Packets of Paneer' }).getByRole('button');
    await expect.element(packets.first()).toMatchTextContent(/1 pack · 200 g/);
    await expect.element(page.getByText('Oldest gets used first.')).toBeVisible();
    (packets.first().element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    const menu = page.getByRole('dialog', { name: /Paneer/ });
    for (const action of ['Used', 'Binned', 'To freezer', 'Move to…', 'Change use-by date…']) {
      const button = menu.getByRole('button', { name: action });
      await expect.element(button).toBeVisible();
      expect(button.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
    await expect.element(menu.getByRole('button', { name: 'Used' })).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    await expect.element(menu).not.toBeInTheDocument();
    await expect.element(packets.first()).toHaveFocus();

    await packets.first().click();
    await page
      .getByRole('dialog', { name: /Paneer/ })
      .getByRole('button', { name: 'Move to…' })
      .click();
    await page
      .getByRole('dialog', { name: /Paneer/ })
      .getByRole('button', { name: 'Freezer' })
      .click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === `/stock/${sample.paneer[0]!.id}/move`)?.body).toEqual({
        place_id: 2
      })
    );
  });
});
