import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { TodayData } from '#lib/client/today.js';
import type { UseSoonLot, UseSoonTub } from '#lib/client/types.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { lot } from '#lib/testing/fakePantry.js';
import PlanStart from '#lib/components/plan/PlanStart.svelte';
import { startAsk } from '#lib/startAsk.svelte.js';
import Today from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const fridge = { id: 1, name: 'Fridge', kind: 'fridge' as const };

/** Two Use soon tubs of one batch in the Fridge, as the server now sends them: one row. */
const lemonRice: UseSoonTub = {
  batch_id: 4,
  tub_id: 11,
  recipe_name: 'Lemon rice',
  colour: null,
  tubs: 2,
  words: '2 tubs',
  use_by: '2026-10-18',
  days_left: 1,
  use_soon: true,
  place: fridge
};

const spinach = {
  ...lot('200 g', '2026-10-17', 0),
  food: { id: 20, name: 'Spinach', counted_as: 'weight' as const },
  place: fridge,
  lots_count: 1,
  lot_ids: [1]
} as unknown as UseSoonLot;

const data = (): TodayData => ({
  today: '2026-10-17',
  first_day: false,
  slots: [],
  plan: { start: '2026-10-10', end: '2026-10-23', meals: [], batch_cooks: [], tubs: [] },
  people: [],
  waiting: [],
  tubs_left: [],
  tubs_left_more: false,
  use_soon_lots: [spinach],
  use_soon_tubs: [lemonRice],
  next_cook: null
});

describe('Today’s Use soon (F203)', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(() => {
    session.me = { ...ME };
    fakeApi({ 'GET /today': [200, data()] });
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  it('shows the tubs of one batch in one place as one row, and counts it once', async () => {
    await page.viewport(1300, 900);
    component = mount(Today, { target: document.body });
    flushSync();
    const soon = page.getByTestId('today-use-soon');
    await expect.element(soon.getByText('Lemon rice')).toBeVisible();
    await expect.element(soon.getByText('Fridge · 2 tubs')).toBeVisible();
    expect(soon.getByText('Lemon rice').elements()).toHaveLength(1);
    expect(document.body.textContent).not.toMatch(/tub \d of \d/);
    // One tub row and one packet: 2, the number the Pantry's Use soon gives for the same stock.
    await expect.element(page.getByTestId('today-stats').getByText('use soon')).toBeVisible();
    expect(page.getByTestId('today-stats').element().querySelector('.soon b')?.textContent).toBe(
      '2'
    );
  });
});

describe('Move it asks when to start a recipe with a long wait (FX5)', () => {
  const components: ReturnType<typeof mount>[] = [];
  const dosa = {
    id: 9,
    position: 0,
    kind: 'recipe',
    recipe: { id: 4, name: 'Masala dosa', removed: false },
    tub_id: null,
    ingredient: null,
    kept_name: null,
    servings: 2,
    note: null,
    eating: 2,
    cooked: false,
    ahead: {
      step_id: 1,
      step_text: 'Soak and grind the batter',
      wait: { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false },
      active_minutes: 30,
      eats_at: '19:00',
      start_day: '2026-10-15',
      start_time: '21:00',
      started_day: null,
      started_time: null,
      waited_minutes: null
    }
  };
  const withDosa = (): TodayData => ({
    ...data(),
    slots: [
      { id: 1, name: 'Breakfast', position: 0, enabled: true },
      { id: 2, name: 'Dinner', position: 1, enabled: true }
    ] as unknown as TodayData['slots'],
    plan: {
      start: '2026-10-10',
      end: '2026-10-23',
      meals: [
        { id: 5, date: '2026-10-16', slot_id: 2, status: 'planned', items: [dosa], kcal: null }
      ],
      batch_cooks: [],
      tubs: []
    } as unknown as TodayData['plan'],
    waiting: [
      {
        meal_id: 5,
        date: '2026-10-16',
        slot_id: 2,
        leftover_item_id: 9,
        use_by_fridge: '2026-10-20',
        use_by_freezer: '2027-01-17'
      }
    ]
  });
  const OPTIONS = {
    wait: { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false },
    eats_at: '19:00',
    options: [{ day: '2026-10-17', time: '08:00', ready_by: '19:00', ready_by_day: '2026-10-17' }]
  };

  function open(requests: Record<string, Parameters<typeof fakeApi>[0][string]>) {
    session.me = { ...ME };
    const sent = fakeApi({
      'GET /today': [200, withDosa()],
      'GET /plan/start-options': [200, OPTIONS],
      ...requests
    });
    for (const component of [Today, PlanStart]) {
      components.push(mount(component, { target: document.body }));
    }
    flushSync();
    return sent;
  }

  afterEach(() => {
    startAsk.dismiss();
    for (const component of components.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  async function moveToToday() {
    await page.viewport(390, 900);
    await page.getByRole('button', { name: 'Move it' }).click();
    await page.getByRole('button', { name: /^Move to / }).click();
  }

  it('asks "When will you start it?" and sends the time with the move', async () => {
    const sent = open({ 'POST /plan/meals/5/mark-moved': [200, { change: null, meal_id: 6 }] });
    await moveToToday();
    await expect.element(page.getByText('When will you start it?')).toBeVisible();
    await page.getByRole('button', { name: 'Move', exact: true }).click();
    await vi.waitFor(() =>
      expect(sent.some((r) => r.path === '/plan/meals/5/mark-moved')).toBe(true)
    );
    expect(sent.find((r) => r.path === '/plan/meals/5/mark-moved')!.body).toMatchObject({
      date: '2026-10-17',
      slot_id: 2,
      starts: [{ item_id: 9, day: '2026-10-17', time: '08:00' }]
    });
  });

  it('No time yet moves it with no start, and Cancel moves nothing', async () => {
    const sent = open({ 'POST /plan/meals/5/mark-moved': [200, { change: null, meal_id: 6 }] });
    await moveToToday();
    await page.getByRole('button', { name: 'Cancel' }).last().click();
    await vi.waitFor(() => expect(startAsk.current).toBeNull());
    expect(sent.some((r) => r.path === '/plan/meals/5/mark-moved')).toBe(false);
    await page.getByRole('button', { name: 'Move it' }).click();
    await page.getByRole('button', { name: /^Move to / }).click();
    await page.getByRole('button', { name: 'No time yet' }).click();
    await vi.waitFor(() =>
      expect(sent.some((r) => r.path === '/plan/meals/5/mark-moved')).toBe(true)
    );
    expect(sent.find((r) => r.path === '/plan/meals/5/mark-moved')!.body).toEqual({
      date: '2026-10-17',
      slot_id: 2
    });
  });
});
