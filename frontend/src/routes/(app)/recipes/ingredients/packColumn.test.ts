import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { FoodRow, PackSuggestion, Size } from '#lib/client/types.js';
import { changeOf, fakeApi, rowOf, toorDal, type FakeRequest } from '#lib/testing/fakeApi.js';
import { network } from '#lib/network.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import Ingredients from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// The Pack column on Ingredients (F121): "jar · 500 g", "+1" with the other sizes, and
// "Add a pack" with the common sizes, a tap making one the Usual size. Phone: a line under the
// name. Computer: a column.

vi.mock('$app/state', () => ({
  page: { url: new URL('http://mealwright.test/recipes/ingredients') }
}));

const size = (id: number, name: string, amount: number, usual: boolean): Size => ({
  id,
  name,
  plural: `${name}s`,
  amount,
  display: `${name[0]!.toUpperCase()}${name.slice(1)} = ${amount >= 1000 ? amount / 1000 : amount} ${amount >= 1000 ? 'kg' : 'g'}`,
  usual,
  added_when_shopping: false
});

const suggestions: PackSuggestion[] = [
  { pack: null, name: 'pack', amount: 200, display: 'pack · 200 g', amount_text: '200 g' },
  { pack: null, name: 'pack', amount: 500, display: 'pack · 500 g', amount_text: '500 g' }
];

const ghee: FoodRow = {
  ...rowOf(toorDal({ id: 1, name: 'Ghee', other_names: [] })),
  pack: size(1, 'jar', 500, true),
  more_sizes: [size(2, 'tin', 1000, false)],
  pack_suggestions: []
};
const dal: FoodRow = {
  ...rowOf(toorDal({ id: 2, name: 'Plain dal', other_names: [] })),
  pack: size(3, 'bag', 1000, true),
  more_sizes: [],
  pack_suggestions: []
};
const tamarind: FoodRow = {
  ...rowOf(toorDal({ id: 3, name: 'Tamarind', other_names: [] })),
  pack: null,
  more_sizes: [],
  pack_suggestions: suggestions
};

function asDesktop(on: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: on && query.includes('min-width: 768px'),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {}
  }));
}

describe('the Pack column', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];

  function open(desktop: boolean) {
    asDesktop(desktop);
    undoHistory.clear();
    toasts.dismiss();
    requests = fakeApi({
      'GET /foods': [
        200,
        {
          total: 3,
          counts: { all: 3, staples: 0, unused: 0, maybe_same: 0, maybe_same_pairs: 0 },
          foods: [ghee, dal, tamarind],
          next: null
        }
      ],
      'GET /foods/3': [200, toorDal({ id: 3, name: 'Tamarind' })],
      'GET /places': [200, []],
      'GET /shops': [200, []],
      'GET /changes?limit=10&area=ingredients': [200, { changes: [], next: null }],
      'POST /foods/3/sizes': [
        201,
        {
          food: toorDal({ id: 3, name: 'Tamarind' }),
          change: changeOf(970, 'Tamarind: added Pack = 500 g')
        }
      ]
    });
    component = mount(Ingredients, { target: document.body });
    flushSync();
  }

  beforeEach(() => {
    network.reset();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
    network.reset();
  });

  // The computer's column is checked in the browser tests (the unit test's frame is phone-wide).
  for (const desktop of [false]) {
    const where = 'on a phone';

    it(`shows the Usual size, and +1 for another size ${where}`, async () => {
      open(desktop);
      await expect.element(page.getByText('jar · 500 g')).toBeVisible();
      await expect.element(page.getByText('bag · 1 kg')).toBeVisible();
      const plus = page.getByRole('button', { name: 'Also: tin · 1 kg' });
      await expect.element(plus).toHaveTextContent('+1');
      await expect.element(plus).toHaveAttribute('title', 'Also: tin · 1 kg');
      // A tap shows the other size on a touch screen.
      await plus.click();
      await expect
        .element(page.getByText('Also: tin · 1 kg', { exact: true }).first())
        .toBeVisible();
    });

    it(`offers Add a pack with the common sizes, and a tap makes one the Usual size ${where}`, async () => {
      open(desktop);
      await page.getByRole('button', { name: 'Add a pack for Tamarind' }).click();
      await expect.element(page.getByText('Common sizes:')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Other…' })).toBeVisible();
      await page.getByRole('button', { name: '500 g' }).click();
      await vi.waitFor(() =>
        expect(requests.find((r) => r.path === '/foods/3/sizes')?.body).toEqual({
          name: 'pack',
          amount: 500,
          usual: true
        })
      );
    });
  }

  it('a phone puts the pack on its own line under the name', async () => {
    open(false);
    const row = page.getByRole('button', { name: /^Ghee/ });
    await expect.element(row).toBeVisible();
    const name = (await row.element().getBoundingClientRect()).bottom;
    const pack = page.getByText('jar · 500 g').element().getBoundingClientRect();
    expect(pack.top).toBeGreaterThanOrEqual(name - 1);
  });
});
