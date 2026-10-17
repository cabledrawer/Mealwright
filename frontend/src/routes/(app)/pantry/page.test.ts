import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { addToPantry } from '$lib/addToPantry.svelte';
import { PLACES, changeOf, fakeApi, toorDal, type FakeRequest } from '$lib/testing/fakeApi';
import { samplePantry } from '$lib/testing/fakePantry';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
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
    // Not until later milestones.
    expect(page.getByText(/\+ List|Recipes for these/).elements()).toHaveLength(0);
    expect(page.getByText('Tubs', { exact: true }).elements()).toHaveLength(0);
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
    await expect.element(page.getByRole('button', { name: /Spinach · today/ })).toBeVisible();
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
