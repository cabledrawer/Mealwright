import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import Toast from '$lib/components/Toast.svelte';
import type { Recipe, RecipeLine, RecipeStock } from '$lib/client/recipes';
import { ingredientEditor } from '$lib/ingredientEditor.svelte';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { fakeShopping, ME, sampleCopy } from '$lib/testing/fakeShopping';
import { dropPhone, freshPhone } from '$lib/testing/phone';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
import RecipeScreen from './RecipeScreen.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

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
    food: { id: 5, name: 'Toor dal' },
    link: 'ingredient',
    note: 'rinsed'
  }),
  line(3, {
    words: 'Tahini',
    amount: 2,
    amount_text: '2',
    unit: 'tbsp',
    food: { id: 7, name: 'Tahini' },
    link: 'ingredient'
  }),
  line(4, {
    words: 'shallots',
    amount: 10,
    amount_text: '10',
    food: { id: 2, name: 'Coriander' },
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
    // Edit opens the editor (Delete is in there); the rest is not built yet, so not there.
    await expect
      .element(page.getByRole('link', { name: 'Edit', exact: true }))
      .toHaveAttribute('href', '/recipes/1/edit');
    const text = document.body.textContent ?? '';
    for (const hidden of ['Plan it', 'Start cooking', 'Cook once', 'Delete']) {
      expect(text).not.toContain(hidden);
    }
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

    it('are hidden when the recipe has none, and "Makes" is then plain text', async () => {
      await open({ serves: null, makes: { amount: 1.5, amount_text: '1½', unit: 'l' } });
      await expect.element(page.getByText(`Makes 1½${NB}litres`, { exact: false })).toBeVisible();
      expect(page.getByRole('group', { name: 'Servings' }).elements()).toHaveLength(0);
      expect(page.getByText(/^Serves/).elements()).toHaveLength(0);
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
      await page.getByRole('button', { name: 'Fewer servings' }).click();
      await page.getByRole('button', { name: 'Fewer servings' }).click();
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

  describe('Keep screen awake (question 32)', () => {
    function fakeLock() {
      const released: number[] = [];
      let n = 0;
      Object.defineProperty(navigator, 'wakeLock', {
        configurable: true,
        value: {
          request: async () => {
            const id = ++n;
            return { release: async () => void released.push(id), addEventListener: () => {} };
          }
        }
      });
      return released;
    }

    it('starts off, switches on, and turns itself off on leaving the page', async () => {
      const released = fakeLock();
      await open();
      const sw = page.getByRole('switch', { name: 'Keep screen awake' });
      await expect.element(sw).toHaveAttribute('aria-checked', 'false');
      await sw.click();
      await expect.element(sw).toHaveAttribute('aria-checked', 'true');
      expect(released).toEqual([]);
      for (const component of mounted.splice(0)) unmount(component);
      await vi.waitFor(() => expect(released).toEqual([1]));
      // Back on the page: off again.
      document.body.innerHTML = '';
      await open();
      await expect
        .element(page.getByRole('switch', { name: 'Keep screen awake' }))
        .toHaveAttribute('aria-checked', 'false');
    });

    it('is not shown where the browser can’t do it', async () => {
      Object.defineProperty(navigator, 'wakeLock', { configurable: true, value: undefined });
      await open();
      await expect.element(page.getByRole('heading', { name: 'Sambar' })).toBeVisible();
      expect(page.getByText('Keep screen awake').elements()).toHaveLength(0);
      expect(page.getByRole('switch').elements()).toHaveLength(0);
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

    it('offline says it needs the server and points to Shopping', async () => {
      await open();
      await expect.element(page.getByRole('heading', { name: 'Sambar' })).toBeVisible();
      network.offline = true;
      await expect.element(page.getByText('You’re offline.')).toBeVisible();
      await expect
        .element(
          page.getByText('Recipes needs your Mealwright server — your shopping list works offline.')
        )
        .toBeVisible();
      await expect
        .element(page.getByRole('link', { name: 'Edit', exact: true }))
        .not.toBeInTheDocument();
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
