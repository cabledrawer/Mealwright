import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import Toast from '#lib/components/Toast.svelte';
import type { Recipe, RecipeLine, RecipeStock } from '#lib/client/recipes.js';
import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { fakeShopping, ME, sampleCopy } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import RecipeScreen from './RecipeScreen.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const navigation = vi.hoisted(() => ({ go: vi.fn(async () => {}) }));
vi.mock('#lib/recipes/paths.js', async (original) => ({
  ...(await original<typeof import('#lib/recipes/paths.js')>()),
  go: navigation.go
}));

const NB = ' ';

const line = (id: number, extra: Partial<RecipeLine> = {}): RecipeLine => ({
  id,
  kind: 'ingredient',
  words: 'x',
  amount: null,
  amount_text: null,
  unit: null,
  size: null,
  food: null,
  recipe: null,
  link: 'none',
  note: null,
  ...extra
});

// Tahini (7), Coriander (2) and Paneer (4) are not on the sample shopping list's main list.
const lines: RecipeLine[] = [
  { ...line(1), kind: 'heading', words: 'For the dal', link: null },
  line(2, {
    words: 'thuvaram paruppu',
    amount: 200,
    amount_text: '200',
    unit: 'g',
    food: { id: 5, name: 'Toor dal', other_names: [] },
    link: 'ingredient',
    note: 'rinsed'
  }),
  line(3, {
    words: 'Tahini',
    amount: 2,
    amount_text: '2',
    unit: 'tbsp',
    food: { id: 7, name: 'Tahini', other_names: [] },
    link: 'ingredient'
  }),
  line(4, {
    words: 'shallots',
    amount: 10,
    amount_text: '10',
    food: { id: 2, name: 'Coriander', other_names: [] },
    link: 'ingredient'
  }),
  line(5, {
    words: 'sambar powder',
    amount: 2,
    amount_text: '2',
    unit: 'tbsp',
    recipe: { id: 9, name: 'Sambar powder' },
    link: 'recipe'
  }),
  line(6, { words: 'salt to taste' }),
  line(7, { words: 'old stuff', link: 'recipe_removed', recipe: { id: 8, name: 'Gone' } })
];

const SAMBAR: Recipe = {
  id: 1,
  name: 'Sambar',
  description: 'Lentil & vegetable stew',
  time_minutes: 50,
  serves: 4,
  makes: null,
  made_ahead: false,
  tags: ['Batch-friendly', 'Quick'],
  nutrition: { kcal: 320, protein: 16, carbs: 48, fat: 7, fibre: null },
  lines,
  steps: [
    { id: 1, kind: 'step', text: 'Rinse the dal.' },
    { id: 2, kind: 'heading', text: 'The tempering' },
    { id: 3, kind: 'step', text: 'Pop the seeds.' },
    { id: 4, kind: 'step', text: 'Stir it in.' }
  ],
  source_note: 'Amma’s',
  photo: null,
  version: 1
};

const STOCK: RecipeStock = {
  lines: [
    { line_id: 2, food: { id: 5, name: 'Toor dal' }, state: 'in_stock', place: 'Cupboard' },
    { line_id: 3, food: { id: 7, name: 'Tahini' }, state: 'missing', place: null },
    { line_id: 4, food: { id: 2, name: 'Coriander' }, state: 'short', place: null }
  ],
  counted: 3,
  missing: 2,
  stock_unchecked: false
};

describe('the recipe page', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let server: ReturnType<typeof fakeShopping>;

  /** Open the recipe with the server answering `routes`. */
  async function open(
    recipe: Partial<Recipe> = {},
    stock: RecipeStock | [number, unknown] = STOCK,
    routes: Parameters<typeof fakeShopping>[1] = {}
  ) {
    server = fakeShopping(sampleCopy(), {
      'GET /recipes/1': [200, { ...SAMBAR, ...recipe }],
      'GET /recipes/1/stock': Array.isArray(stock) ? stock : [200, stock],
      ...routes
    });
    mounted.push(
      mount(RecipeScreen, {
        target: document.body.appendChild(document.createElement('div')),
        props: { id: 1 }
      }),
      mount(Toast, { target: document.body.appendChild(document.createElement('div')) })
    );
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
    freshPhone();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
    network.reset();
    ingredientEditor.close();
    navigation.go.mockClear();
  });

  afterEach(async () => {
    await dropPhone();
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    delete (navigator as unknown as Record<string, unknown>).wakeLock;
    network.reset();
  });

  it('shows the name, the details, the nutrition and the method', async () => {
    await open();
    await expect.element(page.getByRole('heading', { name: 'Sambar', level: 1 })).toBeVisible();
    await expect.element(page.getByText(`Lentil & vegetable stew · 50${NB}min`)).toBeVisible();
    await expect.element(page.getByText('320', { exact: true })).toBeVisible();
    await expect.element(page.getByText(`16${NB}g`, { exact: true })).toBeVisible();
    // Fibre was never typed: unknown, never 0.
    await expect.element(page.getByText('unknown', { exact: true })).toBeVisible();
    await expect.element(page.getByText('Rinse the dal.')).toBeVisible();
    await expect.element(page.getByRole('heading', { name: 'The tempering' })).toBeVisible();
    await expect.element(page.getByText('Batch-friendly')).toBeVisible();
    await expect.element(page.getByText('Source: Amma’s')).toBeVisible();
    // Numbered through the headings: the tempering starts at 2.
    const lists = document.querySelectorAll('ol');
    expect([...lists].map((ol) => ol.getAttribute('start'))).toEqual(['1', '2']);
    // Edit opens the editor; Delete is in the ⋯ menu, shut here; Cook once is not built yet.
    await expect
      .element(page.getByRole('link', { name: 'Edit', exact: true }))
      .toHaveAttribute('href', '/recipes/1/edit');
    const text = document.body.textContent ?? '';
    for (const hidden of ['Start cooking', 'Cook once', 'Delete']) {
      expect(text).not.toContain(hidden);
    }
  });

  describe('the ⋯ menu: Delete recipe', () => {
    const change = { id: 31, summary: 'Deleted Sambar' };

    it('opens with Delete recipe in red and no choice for things not built yet', async () => {
      await open();
      const more = page.getByRole('button', { name: 'More for Sambar' });
      await expect.element(more).toHaveAttribute('aria-expanded', 'false');
      await more.click();
      const items = page.getByRole('menuitem');
      await expect.element(items).toHaveLength(1);
      await expect.element(items.first()).toHaveTextContent('Delete recipe');
      const menu = document.querySelector('[role="menu"]')!;
      expect(menu.textContent).not.toContain('Cook mode');
      // Red: the warning text colour.
      const probe = document.body.appendChild(document.createElement('span'));
      probe.style.color = 'var(--color-warning-text)';
      expect(getComputedStyle(menu.querySelector('[role="menuitem"]')!).color).toBe(
        getComputedStyle(probe).color
      );
    });

    it('deletes at once with no question, says "Deleted Sambar" with Undo, and lands on Recipes', async () => {
      await open({}, STOCK, { 'DELETE /recipes/1': [200, { change }] });
      await page.getByRole('button', { name: 'More for Sambar' }).click();
      await page.getByRole('menuitem', { name: 'Delete recipe' }).click();
      await vi.waitFor(() =>
        expect(server.requests.some((r) => r.method === 'DELETE' && r.path === '/recipes/1')).toBe(
          true
        )
      );
      await expect.element(page.getByText('Deleted Sambar')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Undo' })).toBeVisible();
      await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes'));
    });

    it('Undo asks the server to undo that change', async () => {
      await open({}, STOCK, {
        'DELETE /recipes/1': [200, { change }],
        'POST /changes/31/undo': [
          200,
          {
            result: 'done',
            message: 'Undone.',
            brought_back: [],
            undone: { kind: 'recipe_deleted' }
          }
        ]
      });
      await page.getByRole('button', { name: 'More for Sambar' }).click();
      await page.getByRole('menuitem', { name: 'Delete recipe' }).click();
      await page.getByRole('button', { name: 'Undo' }).click();
      await vi.waitFor(() =>
        expect(
          server.requests.some((r) => r.method === 'POST' && r.path === '/changes/31/undo')
        ).toBe(true)
      );
    });

    it('says so and stays when the server refuses', async () => {
      await open({}, STOCK, {
        'DELETE /recipes/1': [500, { detail: 'Something went wrong. Try again.' }]
      });
      await page.getByRole('button', { name: 'More for Sambar' }).click();
      await page.getByRole('menuitem', { name: 'Delete recipe' }).click();
      await expect.element(page.getByText('Something went wrong. Try again.')).toBeVisible();
      expect(navigation.go).not.toHaveBeenCalled();
    });
  });

  it('says where an imported recipe came from: the site as a link, and the author', async () => {
    await open({
      source_note: null,
      source: {
        url: 'https://www.kitchen.example/recipes/sambar',
        site: 'kitchen.example',
        imported_at: '2026-10-03T10:00:00Z',
        author: 'Meena Raman'
      }
    });
    await expect.element(page.getByText('From: kitchen.example · by Meena Raman')).toBeVisible();
    // Opening it is the person's own click: a plain link, nothing the page fetches.
    const link = page.getByRole('link', { name: 'kitchen.example' });
    await expect
      .element(link)
      .toHaveAttribute('href', 'https://www.kitchen.example/recipes/sambar');
    await expect.element(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('leaves the author out when the page named none, and says nothing for a typed-in recipe', async () => {
    await open({
      source: {
        url: 'https://kitchen.example/x',
        site: 'kitchen.example',
        imported_at: '2026-10-03T10:00:00Z',
        author: null
      }
    });
    await expect.element(page.getByText('From: kitchen.example', { exact: true })).toBeVisible();
    expect(document.body.textContent).not.toContain(' · by ');
  });

  it('shows a source note that is a web address as a link, and any other note as typed', async () => {
    await open({ source_note: 'https://wiki.example/sambar' });
    await expect
      .element(page.getByRole('link', { name: 'https://wiki.example/sambar' }))
      .toHaveAttribute('href', 'https://wiki.example/sambar');
    expect(document.body.textContent).not.toContain('From:');
  });

  it('says nutrition is unknown, in one line, when none was typed', async () => {
    await open({ nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null } });
    await expect.element(page.getByText('Nutrition unknown')).toBeVisible();
  });

  it('shows each line’s own words, and the ingredient’s name only when it differs', async () => {
    await open();
    await expect.element(page.getByText(/thuvaram paruppu/)).toBeVisible();
    await expect.element(page.getByText('Toor dal', { exact: true })).toBeVisible();
    // "Tahini" is both the words and the name, so it is said once; the small texts are only
    // the names that differ, and the notes about a link that has gone.
    const small = [...document.querySelectorAll('.small')].map((el) => el.textContent);
    expect(small).toEqual(['Toor dal', 'Coriander', 'not linked', 'recipe removed']);
    await expect.element(page.getByText('rinsed', { exact: false })).toBeVisible();
    await expect.element(page.getByText('not linked')).toBeVisible();
    await expect.element(page.getByText('recipe removed')).toBeVisible();
  });

  it('a line that is not linked, or whose recipe was deleted, is calm text that opens nothing', async () => {
    await open();
    // Whatever the words, neither is a button or a link (the deleted recipe's id is still sent,
    // so a save keeps the link, but the page must not follow it).
    for (const words of [/salt to taste/, /old stuff/]) {
      await expect.element(page.getByText(words)).toBeVisible();
      expect(page.getByRole('button', { name: words }).elements()).toHaveLength(0);
      expect(page.getByRole('link', { name: words }).elements()).toHaveLength(0);
    }
    // Each says why in small words, and the stock marks leave them out.
    const plain = [...document.querySelectorAll('.line.plain')].map((el) =>
      el.textContent?.replace(/\s+/g, ' ').trim()
    );
    expect(plain).toEqual(['salt to taste not linked', 'old stuff recipe removed']);
  });

  it('marks where each ingredient is', async () => {
    await open();
    await expect.element(page.getByText('Cupboard', { exact: true })).toBeVisible();
    await expect.element(page.getByText('Not enough')).toBeVisible();
    await expect.element(page.getByText('Missing')).toBeInTheDocument();
  });

  it('tapping an ingredient opens the ingredient editor; a recipe line opens that recipe', async () => {
    await open();
    await page.getByRole('button', { name: /thuvaram paruppu/ }).click();
    expect(ingredientEditor.foodId).toBe(5);
    await expect
      .element(page.getByRole('link', { name: /sambar powder/ }))
      .toHaveAttribute('href', '/recipes/9');
    // Lines linked to nothing are not buttons.
    expect(page.getByRole('button', { name: /salt to taste/ }).elements()).toHaveLength(0);
  });

  describe('servings (question 26)', () => {
    it('scale the amounts on screen only, between 1 and 99', async () => {
      await open();
      await expect.element(page.getByText(`200${NB}g`)).toBeVisible();
      await page.getByRole('button', { name: 'More servings' }).click();
      await expect.element(page.getByText('Serves 5')).toBeVisible();
      await expect.element(page.getByText(`250${NB}g`)).toBeVisible();
      // Spoons in quarters, counts in halves.
      await expect.element(page.getByText(`2½${NB}tbsp`).first()).toBeVisible();
      await expect.element(page.getByText('12½')).toBeVisible();
      // Nothing was saved.
      expect(server.requests.filter((r) => r.method !== 'GET' || r.path === '/recipes/1')).toEqual(
        server.requests.filter((r) => r.path === '/recipes/1')
      );
      expect(server.requests.some((r) => r.method === 'PUT')).toBe(false);
      await page.getByRole('button', { name: 'Fewer servings' }).click();
      await page.getByRole('button', { name: 'Fewer servings' }).click();
      await expect.element(page.getByText(`150${NB}g`)).toBeVisible();
    });

    it('stop at 1 and at 99', async () => {
      await open({ serves: 1 });
      await expect.element(page.getByRole('button', { name: 'Fewer servings' })).toBeDisabled();
      unmount(mounted.shift()!);
      document.body.innerHTML = '';
      await open({ serves: 99 });
      await expect.element(page.getByRole('button', { name: 'More servings' })).toBeDisabled();
    });

    it('start at the recipe’s own number every time the page opens', async () => {
      await open();
      await page.getByRole('button', { name: 'More servings' }).click();
      await expect.element(page.getByText('Serves 5')).toBeVisible();
      for (const component of mounted.splice(0)) unmount(component);
      document.body.innerHTML = '';
      await open();
      await expect.element(page.getByText('Serves 4')).toBeVisible();
    });

    it('are hidden when the recipe has neither Serves nor Makes', async () => {
      await open({ serves: null, makes: null });
      await expect.element(page.getByRole('heading', { name: 'Ingredients' })).toBeVisible();
      expect(page.getByRole('group').elements()).toHaveLength(0);
      expect(page.getByText(/^(Serves|Makes)/).elements()).toHaveLength(0);
    });

    it('Makes without Serves: − / + in whole multiples from 1×, on screen only', async () => {
      await open({ serves: null, makes: { amount: 200, amount_text: '200', unit: 'g' } });
      const group = page.getByRole('group', { name: 'How much it makes' });
      await expect.element(group.getByText(`Makes 200${NB}g`)).toBeVisible();
      // Not twice: the quiet line under the name leaves it to − / +.
      expect(page.getByText(/Makes/).elements()).toHaveLength(1);
      await expect.element(page.getByRole('button', { name: 'Make less' })).toBeDisabled();
      await expect.element(page.getByText(`200${NB}g`, { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Make more' }).click();
      await expect.element(group.getByText(`Makes 400${NB}g`)).toBeVisible();
      // The lines scale the same way: twice the toor dal.
      await expect.element(page.getByText(`400${NB}g`, { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Make more' }).click();
      await expect.element(group.getByText(`Makes 600${NB}g`)).toBeVisible();
      await page.getByRole('button', { name: 'Make less' }).click();
      await page.getByRole('button', { name: 'Make less' }).click();
      await expect.element(group.getByText(`Makes 200${NB}g`)).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Make less' })).toBeDisabled();
      // Nothing was saved, and no Serves appeared.
      expect(server.requests.some((r) => r.method !== 'GET')).toBe(false);
      expect(page.getByText(/^Serves/).elements()).toHaveLength(0);
    });

    it('Makes without Serves: the marks show at 1× only, as the server counts for 1×', async () => {
      await open({ serves: null, makes: { amount: 200, amount_text: '200', unit: 'g' } });
      await expect.element(page.getByText('Cupboard', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Make more' }).click();
      await expect.element(page.getByText('Cupboard', { exact: true })).not.toBeInTheDocument();
      await page.getByRole('button', { name: 'Make less' }).click();
      await expect.element(page.getByText('Cupboard', { exact: true })).toBeVisible();
      // The server ignores servings without Serves, so − / + never asks it again.
      await new Promise((done) => setTimeout(done, 400));
      expect(server.requests.filter((r) => r.path.startsWith('/recipes/1/stock'))).toHaveLength(1);
    });

    it('stop at 99×', async () => {
      await open({ serves: null, makes: { amount: 1, amount_text: '1', unit: 'dosa' } });
      for (let i = 0; i < 98; i++) await page.getByRole('button', { name: 'Make more' }).click();
      await expect.element(page.getByRole('button', { name: 'Make more' })).toBeDisabled();
      await expect.element(page.getByText(/^Makes 99/)).toBeVisible();
    });

    it('keep the quiet "Makes" line when there are no ingredient lines to scale', async () => {
      await open({
        serves: null,
        lines: [],
        makes: { amount: 200, amount_text: '200', unit: 'g' }
      });
      await expect.element(page.getByText(`Makes 200${NB}g`, { exact: false })).toBeVisible();
      expect(page.getByRole('group').elements()).toHaveLength(0);
    });

    it('scale what a recipe makes too', async () => {
      await open({ makes: { amount: 1.5, amount_text: '1½', unit: 'l' } });
      await page.getByRole('button', { name: 'More servings' }).click();
      await page.getByRole('button', { name: 'More servings' }).click();
      await page.getByRole('button', { name: 'More servings' }).click();
      await page.getByRole('button', { name: 'More servings' }).click();
      await expect.element(page.getByText(`3${NB}litres`, { exact: false })).toBeVisible();
    });
  });

  describe('the stock marks follow the chosen servings (cabledrawer 19 Oct, Q22)', () => {
    const everything: RecipeStock = {
      lines: [
        { line_id: 2, food: { id: 5, name: 'Toor dal' }, state: 'in_stock', place: 'Cupboard' },
        { line_id: 3, food: { id: 7, name: 'Tahini' }, state: 'in_stock', place: 'Fridge' },
        { line_id: 4, food: { id: 2, name: 'Coriander' }, state: 'in_stock', place: 'Fridge' }
      ],
      counted: 3,
      missing: 0,
      stock_unchecked: false
    };
    const servingsOf = (url: string) => new URL(url, 'http://x').searchParams.get('servings');

    it('change the marks and the missing count after − / +, with one request for a run of taps', async () => {
      await open({}, STOCK, {
        'GET /recipes/1/stock': (request) => [
          200,
          servingsOf(request.url) === '2' ? everything : STOCK
        ]
      });
      await expect.element(page.getByText('2 missing')).toBeVisible();
      await expect.element(page.getByText('Not enough')).toBeVisible();
      // Both taps in one go, with no wait between them: a slow machine can't stretch the gap
      // past STOCK_WAIT_MS and turn one request into two.
      const fewer = page.getByRole('button', { name: 'Fewer servings' }).element() as HTMLElement;
      fewer.click();
      fewer.click();
      await expect.element(page.getByText('Serves 2')).toBeVisible();
      await vi.waitFor(() => expect(page.getByText('2 missing').elements()).toHaveLength(0));
      expect(page.getByText('Not enough').elements()).toHaveLength(0);
      expect(page.getByRole('button', { name: 'Add to the list' }).elements()).toHaveLength(0);
      await expect.element(page.getByText('Fridge').first()).toBeVisible();
      const asked = server.requests.filter((r) => r.path === '/recipes/1/stock').map((r) => r.url);
      expect(asked).toEqual(['/recipes/1/stock', '/recipes/1/stock?servings=2']);
      // And back up: the marks come back.
      await page.getByRole('button', { name: 'More servings' }).click();
      await page.getByRole('button', { name: 'More servings' }).click();
      await expect.element(page.getByText('2 missing')).toBeVisible();
    });

    it('never let a slow old answer overwrite a newer one', async () => {
      const oneShort: RecipeStock = {
        lines: [
          everything.lines[0]!,
          { line_id: 3, food: { id: 7, name: 'Tahini' }, state: 'missing', place: null },
          everything.lines[2]!
        ],
        counted: 3,
        missing: 1,
        stock_unchecked: false
      };
      await open({}, STOCK, {
        'GET /recipes/1/stock': (request) => {
          const asked = servingsOf(request.url);
          return [200, asked === '5' ? everything : asked === '6' ? oneShort : STOCK];
        }
      });
      await expect.element(page.getByText('2 missing')).toBeVisible();
      let release!: () => void;
      const held = new Promise<void>((resolve) => (release = resolve));
      const working = fetch;
      vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
        if (String(input).endsWith('servings=5')) await held;
        return working(input, init);
      });
      await page.getByRole('button', { name: 'More servings' }).click();
      // The answer for 5 is on its way (held); now ask for 6 and let that one arrive first.
      await new Promise((resolve) => setTimeout(resolve, 600));
      await page.getByRole('button', { name: 'More servings' }).click();
      await expect.element(page.getByText('1 missing')).toBeVisible();
      release();
      await new Promise((resolve) => setTimeout(resolve, 200));
      expect(server.requests.some((r) => r.url.endsWith('servings=5'))).toBe(true);
      // The old answer (nothing missing) arrived last and was ignored.
      await expect.element(page.getByText('1 missing')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Add to the list' })).toBeVisible();
    });
  });

  describe('Serves changing elsewhere (L5)', () => {
    it('is followed until − / + is used, and then the chosen number stays', async () => {
      let serves = 4;
      await open({}, STOCK, {
        'GET /recipes/1': () => [200, { ...SAMBAR, serves }]
      });
      await expect.element(page.getByText('Serves 4')).toBeVisible();
      serves = 6;
      document.dispatchEvent(new Event('visibilitychange'));
      await expect.element(page.getByText('Serves 6')).toBeVisible();
      // The saved amounts are for the new Serves: shown as they are, not scaled.
      await expect.element(page.getByText(`200${NB}g`)).toBeVisible();
      await page.getByRole('button', { name: 'More servings' }).click();
      await expect.element(page.getByText('Serves 7')).toBeVisible();
      await expect.element(page.getByText(`233${NB}g`)).toBeVisible();
      serves = 8;
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.waitFor(() =>
        expect(server.requests.filter((r) => r.path === '/recipes/1').length).toBeGreaterThan(2)
      );
      await expect.element(page.getByText('Serves 7')).toBeVisible();
    });
  });

  describe('"N missing · Add to the list" (question 23)', () => {
    it('counts what is short or missing, and adds it with one Undo', async () => {
      await open();
      await expect.element(page.getByText('2 missing')).toBeVisible();
      await page.getByRole('button', { name: 'Add to the list' }).click();
      await vi.waitFor(() =>
        expect(server.actions.filter((a) => a.kind === 'add').map((a) => a.food_id)).toEqual([7, 2])
      );
      expect(toasts.current?.message).toBe('2 ingredients added to the shopping list');
      expect(toasts.current?.action?.label).toBe('Undo');
      // Both are On list now, and nothing is left to add: the line is gone.
      await expect.element(page.getByText('On list').first()).toBeVisible();
      expect(page.getByText('missing', { exact: false }).elements()).toHaveLength(0);
      expect(page.getByRole('button', { name: 'Add to the list' }).elements()).toHaveLength(0);
    });

    it('does not count what is already on the list', async () => {
      await open(
        {},
        {
          ...STOCK,
          lines: [
            STOCK.lines[0]!,
            // Onions (1) is on the sample main list already.
            { line_id: 3, food: { id: 1, name: 'Onions' }, state: 'missing', place: null },
            { line_id: 4, food: { id: 2, name: 'Coriander' }, state: 'missing', place: null }
          ]
        }
      );
      await expect.element(page.getByText('1 missing')).toBeVisible();
      await expect.element(page.getByText('On list')).toBeVisible();
    });

    it('is not there when everything is in stock, and never says "all in stock"', async () => {
      await open(
        {},
        {
          lines: [STOCK.lines[0]!],
          counted: 1,
          missing: 0,
          stock_unchecked: true
        }
      );
      await expect.element(page.getByText('Cupboard')).toBeVisible();
      expect(page.getByRole('button', { name: 'Add to the list' }).elements()).toHaveLength(0);
      expect(document.body.textContent).not.toMatch(/all in stock/i);
    });

    it('shows the page without marks when the stock can’t be read', async () => {
      await open({}, [500, { detail: 'Something broke.' }]);
      await expect.element(page.getByRole('heading', { name: 'Sambar' })).toBeVisible();
      expect(page.getByText('Cupboard').elements()).toHaveLength(0);
      expect(page.getByRole('button', { name: 'Add to the list' }).elements()).toHaveLength(0);
    });
  });

  describe('Cook now (K4)', () => {
    it('is the main button above the ingredients and opens Cook mode', async () => {
      await open();
      const cook = page.getByRole('link', { name: 'Cook now' });
      await expect.element(cook).toBeVisible();
      expect(cook.element().getAttribute('href')).toMatch(/\/recipes\/1\/cook$/);
      const ingredients = page.getByRole('heading', { name: 'Ingredients' }).element();
      expect(
        cook.element().compareDocumentPosition(ingredients) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy();
    });

    it('moved Keep screen awake into Cook mode: the recipe page has no such switch', async () => {
      await open();
      await expect.element(page.getByRole('heading', { name: 'Sambar' })).toBeVisible();
      expect(page.getByText('Keep screen awake').elements()).toHaveLength(0);
      expect(page.getByRole('switch').elements()).toHaveLength(0);
    });
  });

  describe('Plan it (0.7)', () => {
    const SLOTS = [
      { id: 1, name: 'Breakfast', position: 1, enabled: true },
      { id: 2, name: 'Dinner', position: 2, enabled: true }
    ];
    const change = {
      id: 61,
      kind: 'plan_add',
      at: '2026-10-17T10:00:00Z',
      who: { login_id: 1, name: 'Tess' },
      summary: 'Planned Sambar for Dinner',
      can_undo: true,
      undo_until: null,
      undone: null
    };
    const EMPTY_PLAN = {
      start: '2026-10-12',
      end: '2026-10-18',
      meals: [],
      batch_cooks: [],
      tubs: []
    };
    const planRoutes = (): Parameters<typeof fakeShopping>[1] => ({
      'GET /household': [200, { today: '2026-10-17', week_starts_on: 1 }],
      'GET /meal-slots': [200, SLOTS],
      'GET /plan': [200, EMPTY_PLAN],
      'GET /plan/tubs-left': [200, { tubs: [], more: false }],
      'GET /plan/people': [200, []],
      'POST /plan/items': [200, { change, meal_id: 9, item_id: 10 }],
      'POST /changes/61/undo': [200, { message: 'Undone', change: { ...change, undone: {} } }]
    });

    it('is a button beside Cook now', async () => {
      await open({}, STOCK, planRoutes());
      await expect
        .element(page.getByRole('button', { name: 'Plan it', exact: true }))
        .toBeVisible();
      await expect.element(page.getByRole('link', { name: 'Cook now' })).toBeVisible();
    });

    it('asks for the day and the meal, plans the recipe there, and offers Undo', async () => {
      await open({}, STOCK, planRoutes());
      await page.getByRole('button', { name: 'Plan it', exact: true }).click();
      const sheet = page.getByRole('dialog', { name: 'Sambar' });
      await expect.element(sheet.getByRole('heading', { name: 'Plan it on…' })).toBeVisible();
      await sheet.getByRole('button', { name: 'Saturday 17 October' }).click();
      await sheet.getByRole('button', { name: 'Dinner' }).click();
      await sheet.getByRole('button', { name: 'Plan it here' }).click();
      await expect.element(page.getByText('Planned Sambar for Dinner')).toBeVisible();
      const posts = server.requests.filter((r) => r.method === 'POST' && r.path === '/plan/items');
      expect(posts).toHaveLength(1);
      expect(posts[0]!.body).toEqual({ date: '2026-10-17', slot_id: 2, recipe_id: 1 });
      await page.getByRole('button', { name: 'Undo' }).click();
      await vi.waitFor(() =>
        expect(server.requests.some((r) => r.path === '/changes/61/undo')).toBe(true)
      );
    });

    it('says so, and opens nothing, when the plan can’t be read', async () => {
      await open({}, STOCK, { ...planRoutes(), 'GET /plan': [500, { detail: 'no' }] });
      await page.getByRole('button', { name: 'Plan it', exact: true }).click();
      await expect.element(page.getByText('Couldn’t load the plan. Try again.')).toBeVisible();
      expect(page.getByRole('dialog').elements()).toHaveLength(0);
    });
  });

  describe('states', () => {
    it('says Loading… until the server answers', async () => {
      let release!: () => void;
      const held = new Promise<void>((resolve) => (release = resolve));
      await open({}, STOCK, {
        'GET /recipes/1': () => {
          throw new Error('replaced below');
        }
      });
      for (const component of mounted.splice(0)) unmount(component);
      document.body.innerHTML = '';
      const working = fetch;
      vi.stubGlobal('fetch', async (input: string, init?: RequestInit) => {
        if (String(input).endsWith('/recipes/1')) await held;
        return working(input, init);
      });
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(RecipeScreen, { target, props: { id: 1 } }));
      await expect.element(page.getByText('Loading…')).toBeVisible();
      release();
    });

    it('says what happened when it fails, and Try again loads it', async () => {
      await open({}, STOCK, { 'GET /recipes/1': [500, { detail: 'Something broke.' }] });
      await expect.element(page.getByText('Couldn’t load this recipe. Try again.')).toBeVisible();
      server = fakeShopping(sampleCopy(), {
        'GET /recipes/1': [200, SAMBAR],
        'GET /recipes/1/stock': [200, STOCK]
      });
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByRole('heading', { name: 'Sambar' })).toBeVisible();
    });

    it('says the recipe isn’t there when it was deleted', async () => {
      await open({}, STOCK, {
        'GET /recipes/1': [404, { detail: 'That recipe isn’t here.', code: 'not_found' }],
        'GET /recipes/1/stock': [404, { detail: 'That recipe isn’t here.', code: 'not_found' }]
      });
      await expect.element(page.getByRole('heading', { name: 'Recipe not found' })).toBeVisible();
      await expect
        .element(page.getByText('This recipe isn’t here any more. It may have been deleted.'))
        .toBeVisible();
      await expect.element(page.getByRole('link', { name: 'Recipes' }).first()).toBeVisible();
    });

    it('the recipe already showing stays when the bar comes, without Edit (F80)', async () => {
      await open();
      await expect.element(page.getByRole('heading', { name: 'Sambar' })).toBeVisible();
      network.offline = true;
      network.deviceOffline = true;
      flushSync();
      await expect.element(page.getByRole('heading', { name: 'Sambar' })).toBeVisible();
      expect(document.body.textContent).not.toMatch(/You’re offline/);
      await expect
        .element(page.getByRole('link', { name: 'Edit', exact: true }))
        .not.toBeInTheDocument();
    });

    it('offline with no recipe yet says it needs the server and points to Shopping', async () => {
      network.offline = true;
      network.deviceOffline = true;
      await open({}, STOCK, {
        'GET /recipes/1': [502, ''],
        'GET /recipes/1/stock': [502, '']
      });
      await expect.element(page.getByText('You’re offline.')).toBeVisible();
      await expect
        .element(
          page.getByText('Recipes needs your Mealwright server. Your shopping list works offline.')
        )
        .toBeVisible();
    });

    it('a recipe with only a name says nothing is written down yet', async () => {
      await open({ lines: [], steps: [], tags: [], source_note: null, description: null });
      await expect.element(page.getByText('Nothing written down yet.')).toBeVisible();
    });

    it('one line, and a very long name and line, still read', async () => {
      const long = 'பச்சைப் பயறு (பாசிப்பயறு) '.repeat(6);
      await open({
        name: long,
        lines: [line(2, { words: long, amount: 1, amount_text: '1', link: 'none' })],
        steps: []
      });
      await expect.element(page.getByRole('heading', { level: 1 })).toBeVisible();
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
    });
  });

  describe('the photo', () => {
    // A 2 × 2 pixel PNG, so the photo really loads.
    const DISH =
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGN4VqcERAwQCgAtxgYZHCtf2QAAAABJRU5ErkJggg==';
    const photo = (url: string) => ({
      id: 5,
      width: 1600,
      height: 1200,
      url,
      list_width: 208,
      list_height: 156,
      list_url: '/api/v1/recipes/photos/5/list'
    });

    it('sits between the top row and the name, 170 px tall, with the large copy', async () => {
      await open({ photo: photo(DISH) });
      const img = page.getByRole('img', { name: 'Photo of Sambar' });
      await expect.element(img).toBeVisible();
      await expect.element(img).toHaveAttribute('src', DISH);
      const box = document.querySelector('.frame')!.getBoundingClientRect();
      expect(box.height).toBe(170);
      const top = document.querySelector('.top')!.getBoundingClientRect();
      const name = document.querySelector('h1')!.getBoundingClientRect();
      expect(box.top).toBeGreaterThanOrEqual(top.bottom);
      expect(box.bottom).toBeLessThanOrEqual(name.top);
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
    });

    it('is not drawn at all when the recipe has none', async () => {
      await open({ photo: null });
      await expect.element(page.getByRole('heading', { name: 'Sambar', level: 1 })).toBeVisible();
      expect(document.querySelector('img')).toBeNull();
      expect(document.querySelector('.frame')).toBeNull();
    });

    it('is gone, with no broken-image icon, when it can’t be fetched', async () => {
      await open({ photo: photo('/api/v1/recipes/photos/404/large') });
      await expect.element(page.getByRole('heading', { name: 'Sambar', level: 1 })).toBeVisible();
      await expect.poll(() => document.querySelector('img')).toBeNull();
      expect(document.querySelector('.frame')).toBeNull();
    });
  });
});
