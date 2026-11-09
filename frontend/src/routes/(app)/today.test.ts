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
