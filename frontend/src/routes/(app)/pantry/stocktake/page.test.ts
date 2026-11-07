import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { Stocktake, StocktakePlace, StocktakeRow } from '#lib/client/stocktake.js';
import { changeOf, fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { toasts } from '#lib/toast.svelte.js';
import Stocktake_ from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const cupboard = { id: 3, name: 'Cupboard', kind: 'cupboard' as const };
const spices = { id: 4, name: 'Spice rack', kind: 'cupboard' as const };

function row(id: number, name: string, extra: Partial<StocktakeRow> = {}): StocktakeRow {
  return {
    food: { id, name, counted_as: 'weight' },
    staple: false,
    restocked_on: null,
    restocked_days_ago: null,
    added: false,
    answered: false,
    stock: { amount: 3000, display: '3 bags' },
    pack: {
      id: 1,
      name: 'bag',
      plural: 'bags',
      amount: 1000,
      display: 'Bag = 1 kg',
      usual: true,
      added_when_shopping: false
    },
    pack_suggestions: [],
    answer: null,
    fraction_now: '1',
    more_now: 2,
    counted: false,
    count_now: null,
    count_word: null,
    count_word_plural: null,
    ...extra
  };
}

const overview: Stocktake = {
  places: [
    { ...cupboard, finished: false, answered: 0, total: 2 },
    { ...spices, finished: false, answered: 0, total: 0 }
  ],
  current_place_id: 3,
  started: false,
  complete: false
};

function placeOf(rows: StocktakeRow[]): StocktakePlace {
  return {
    place: cupboard,
    number: 1,
    of: 2,
    finished: false,
    answered: 0,
    total: rows.length,
    previous: null,
    next: spices,
    rows
  };
}

describe('the Stocktake page', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];

  async function render(rows: StocktakeRow[], extra: Parameters<typeof fakeApi>[0] = {}) {
    requests = fakeApi({
      'GET /stocktake': [200, overview],
      'GET /stocktake/places/3': [200, placeOf(rows)],
      'POST /stocktake/places/3/foods/7/answer': () => [
        200,
        {
          change: changeOf(900, 'Stocktake: Toor dal in the Cupboard'),
          row: row(7, 'Toor dal', { answered: true }),
          answered: 1,
          total: rows.length
        }
      ],
      ...extra
    });
    await page.viewport(390, 900);
    component = mount(Stocktake_, { target: document.body });
    flushSync();
    await expect
      .element(page.getByRole('heading', { name: 'Stocktake · Cupboard', level: 1 }))
      .toBeVisible();
  }

  const answers = () => requests.filter((r) => r.method === 'POST' && r.path.endsWith('/answer'));

  beforeEach(() => toasts.dismiss());
  afterEach(() => {
    if (component) void unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('shows the packets there now before any pick, and a pick keeps them', async () => {
    await render([row(7, 'Toor dal')]);
    const group = page.getByRole('group', { name: 'Toor dal: more packets' });
    await expect.element(group).toBeVisible();
    await expect.element(group.getByText('2', { exact: true })).toBeVisible();
    await page.getByRole('radio', { name: '¾ left' }).click();
    await vi.waitFor(() => expect(answers()).toHaveLength(1));
    expect(answers()[0]!.body).toEqual({ fraction: 0.75, more: 2 });
  });

  it('None asks for nothing, with no packets besides', async () => {
    await render([row(7, 'Toor dal')]);
    await page.getByRole('radio', { name: 'None' }).click();
    await vi.waitFor(() => expect(answers()).toHaveLength(1));
    expect(answers()[0]!.body).toEqual({ fraction: 0, more: 0 });
  });

  it('a counted row says 2 tins, not a bare 2', async () => {
    const tins = row(7, 'Tinned tomatoes', {
      food: { id: 7, name: 'Tinned tomatoes', counted_as: 'count' },
      pack: null,
      stock: { amount: 2, display: '2 tins' },
      counted: true,
      count_now: '2',
      count_word: 'tin',
      count_word_plural: 'tins',
      fraction_now: null,
      more_now: 0
    });
    await render([tins]);
    const group = page.getByRole('group', { name: 'Tinned tomatoes: how many' });
    await expect.element(group.getByText(/^2\s+tins$/)).toBeVisible();
  });

  it('a row whose pack is a tin is counted whole: minus 2 tins plus, no fractions', async () => {
    const tin = {
      id: 2,
      name: 'tin',
      plural: 'tins',
      amount: 400,
      display: 'Tin = 400 g',
      usual: true,
      added_when_shopping: false
    };
    const tins = row(7, 'Chickpeas', {
      pack: tin,
      stock: { amount: 800, display: '2 tins' },
      counted: true,
      count_now: '2',
      count_word: 'tin',
      count_word_plural: 'tins',
      fraction_now: null,
      more_now: 0
    });
    await render([tins, row(8, 'Jam', { food: { id: 8, name: 'Jam', counted_as: 'weight' } })], {
      'POST /stocktake/places/3/foods/7/answer': () => [
        200,
        {
          change: changeOf(901, 'Stocktake: Chickpeas 1 tin in the Cupboard'),
          row: { ...tins, answered: true, count_now: '1' },
          answered: 1,
          total: 2
        }
      ]
    });
    const group = page.getByRole('group', { name: 'Chickpeas: how many' });
    await expect.element(group.getByText(/^2\s+tins$/)).toBeVisible();
    await expect
      .element(page.getByRole('radiogroup', { name: 'Chickpeas' }))
      .not.toBeInTheDocument();
    // The jar-like row keeps its picks.
    await expect.element(page.getByRole('radiogroup', { name: 'Jam' })).toBeVisible();
    await group.getByRole('button', { name: 'One fewer' }).click();
    await vi.waitFor(() => expect(answers()).toHaveLength(1));
    expect(answers()[0]!.body).toEqual({ count: 1 });
  });

  it('says so when Next cannot be saved', async () => {
    await render([row(7, 'Toor dal')], {
      'POST /stocktake/places/3/finish': [500, { detail: 'x' }]
    });
    await page.getByRole('button', { name: 'Next: Spice rack →' }).click();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Couldn’t save. Try again.'));
  });
});
