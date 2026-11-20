// Plan this batch: the later recipes' "Where the tubs land" shows the tubs the earlier recipes
// already placed (F229, cabledrawer 12 Nov).
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { BatchPreview, PreviewTub } from '#lib/client/plan.js';
import type { Ahead } from '#lib/cookOnce.svelte.js';
import type { PlanActions } from '#lib/planActions.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import CookOnce from './CookOnce.svelte';
import '../../styles/tokens.css';
import '../../styles/base.css';

/** What is on show in an element, whitespace squeezed (a string match is a "contains"). */
const text = (locator: { element: () => Element }) =>
  (locator.element().textContent ?? '').replace(/\s+/g, ' ');

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

const COOK_DAY = '2026-11-14';
const THU = '2026-11-15';

function tub(number: number, date: string | null, slot: number | null): PreviewTub {
  return {
    number,
    date,
    slot_id: slot,
    place_kind: 'fridge',
    member_id: null,
    use_by: '2026-11-20',
    meal_has_food: false
  };
}

function preview(tubs: PreviewTub[]): BatchPreview {
  return {
    recipe_id: 2,
    recipe_name: 'Khichdi',
    recipe_serves: 4,
    cook_day: COOK_DAY,
    cook_meal_id: 1,
    cook_slot_id: 2,
    colour: 'sage',
    tubs,
    placed: tubs.filter((t) => t.date !== null).length,
    per_tub: { kcal: null, protein_g: null, fibre_g: null }
  };
}

function open(before: Ahead['before'], tubs: PreviewTub[]) {
  fakeApi({ 'GET /plan': [200, { start: '', end: '', meals: [], batch_cooks: [], tubs: [] }] });
  const model = {
    slotsOn: [
      { id: 2, name: 'Lunch' },
      { id: 3, name: 'Dinner' }
    ],
    slotName: (id: number) => (id === 2 ? 'Lunch' : 'Dinner'),
    people: [],
    plan: null
  };
  const ahead: Ahead = {
    name: 'Khichdi',
    day: COOK_DAY,
    slotId: 2,
    position: '2 of 3',
    last: false,
    before,
    preview: () => Promise.resolve(preview(tubs)),
    save: () => {}
  };
  const actions = { model, readonly: false } as unknown as PlanActions;
  component = mount(CookOnce, {
    target: document.body,
    props: { actions, target: null, ahead, onclose: () => {} }
  });
  flushSync();
}

describe('Plan this batch: the tubs the earlier recipes placed (F229)', () => {
  it('shows a meal an earlier recipe’s tub is in as taken, not free', async () => {
    open(
      [{ name: 'Paneer Butter Masala', tubs: [tub(1, THU, 3)] }],
      [tub(1, THU, 2), tub(2, null, null)]
    );
    const cell = page.getByTestId(`cook-cell-${THU}-3`);
    await expect.poll(() => text(cell)).toContain('Paneer Butter Masala · Tub 1 · already placed');
    // It reads as a meal with something in it: the add button says "too", as for a planned meal.
    await expect
      .element(cell.getByRole('button', { name: /Add a tub too to Dinner/ }))
      .toBeVisible();
    // A meal nobody put a tub in is still free.
    await expect.poll(() => text(page.getByTestId(`cook-cell-${THU}-2`))).not.toContain('already');
  });

  it('says where the rest go and how many are placed, from this recipe’s own tubs', async () => {
    open([{ name: 'Paneer Butter Masala', tubs: [tub(1, THU, 3)] }], [tub(1, null, null)]);
    await expect.poll(() => text(page.getByTestId('cook-summary'))).toContain('Tub 1 → Fridge');
    await expect.poll(() => text(page.getByTestId('cook-summary'))).toContain('0 of 4 placed');
  });

  it('a meal holding tubs of two earlier recipes lists both', async () => {
    open(
      [
        { name: 'Paneer Butter Masala', tubs: [tub(1, THU, 3)] },
        { name: 'Dal Tadka', tubs: [tub(2, THU, 3), tub(3, THU, 3)] }
      ],
      [tub(1, null, null)]
    );
    const cell = page.getByTestId(`cook-cell-${THU}-3`);
    await expect.poll(() => text(cell)).toContain('Paneer Butter Masala · Tub 1 · already placed');
    await expect.poll(() => text(cell)).toContain('Dal Tadka · Tubs 2–3 · already placed');
  });
});
