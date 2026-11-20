import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import {
  PLACES,
  SHOPS,
  changeOf,
  fakeApi,
  rowOf,
  toorDal,
  type FakeRequest
} from '#lib/testing/fakeApi.js';
import { network } from '#lib/network.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import NewIngredient from '#lib/components/NewIngredient.svelte';
import { newIngredient } from '#lib/newIngredient.svelte.js';
import Ingredients from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// The page's address: "Edit staples" on Pantry opens it with ?filter=staples.
const route = vi.hoisted(() => ({ search: '' }));
vi.mock('$app/state', () => ({
  page: {
    get url() {
      return new URL(`http://mealwright.test/recipes/ingredients${route.search}`);
    }
  }
}));

const dal = toorDal({ used_in_recipes: 5 });
const sticks = toorDal({
  id: 40,
  name: 'Drumsticks (moringa)',
  other_names: [],
  counted_as: 'count',
  maybe_same: [{ id: 12, name: 'Drumsticks', merge_into: 12, merge_this: true }]
});

describe('the Ingredients page', () => {
  let component: ReturnType<typeof mount> | null = null;
  let dialog: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];

  beforeEach(() => {
    undoHistory.clear();
    toasts.dismiss();
    requests = fakeApi({
      'GET /foods': (request) => {
        const params = new URLSearchParams(request.url.split('?')[1]);
        const q = params.get('q');
        // Every ingredient is in a recipe, so “Not in any recipe” finds none.
        const foods = (params.get('filter') === 'unused' ? [] : [rowOf(sticks), rowOf(dal)]).filter(
          (f) => !q || f.name.toLowerCase().includes(q) || f.other_names.some((n) => n.includes(q))
        );
        return [
          200,
          {
            total: 2,
            counts: { all: 2, staples: 0, unused: 9, maybe_same: 2, maybe_same_pairs: 1 },
            foods,
            next: null
          }
        ];
      },
      'GET /foods/7': [200, dal],
      'GET /foods/50': [200, toorDal({ id: 50, name: 'Tahini', counted_as: 'count' })],
      'POST /foods': [
        201,
        {
          food: toorDal({ id: 50, name: 'Tahini', counted_as: 'count' }),
          change: changeOf(960, 'Added Tahini')
        }
      ],
      'GET /places': [200, { places: PLACES }],
      'GET /shops': [200, { shops: SHOPS }],
      'POST /foods/40/merge': [
        200,
        {
          food: toorDal({ id: 12, name: 'Drumsticks' }),
          change: changeOf(950, 'Merged Drumsticks (moringa) into Drumsticks')
        }
      ]
    });
    component = mount(Ingredients, { target: document.body });
    dialog = mount(NewIngredient, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    newIngredient.cancel();
    if (dialog) unmount(dialog);
    dialog = null;
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
    network.reset();
  });

  it('a search that fails once the list has loaded keeps the list: no server note (F67 review)', async () => {
    await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('', { status: 502 })));
    await page.getByRole('searchbox', { name: 'Search ingredients' }).fill('arhar');
    await vi.waitFor(() => expect(network.down).toBe(true));
    flushSync();
    await expect.element(page.getByRole('searchbox', { name: 'Search ingredients' })).toBeVisible();
    expect(document.body.textContent).not.toContain('Can’t reach your Mealwright server.');
  });

  it('lists every ingredient from the server, with its counts', async () => {
    await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
    await expect.element(page.getByText(/^2 ingredients · shared by/)).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Maybe the same · 1' })).toBeVisible();
  });

  it('searches by any name on the server', async () => {
    await page.getByRole('searchbox', { name: 'Search ingredients' }).fill('arhar');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?q=arhar&limit=50')).toBe(true)
    );
    await expect.element(page.getByRole('button', { name: /^Drumsticks/ })).not.toBeInTheDocument();
  });

  it('filters', async () => {
    await page.getByRole('button', { name: 'Staples' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?filter=staples&limit=50')).toBe(true)
    );
  });

  it('says how many recipes use each ingredient, where there are any', async () => {
    // “5 recipes” on a phone row; a screen reader hears “Used in 5 recipes”.
    const row = page.getByRole('listitem').filter({ hasText: 'Toor dal' });
    await expect.element(row).toBeVisible();
    expect(row.element().textContent).toMatch(/Used in 5 recipes$/);
    const used = row.element().querySelector('.used')!.cloneNode(true) as HTMLElement;
    used.querySelector('.visually-hidden')!.remove();
    expect(used.textContent!.replace(/\s+/g, ' ').trim()).toBe('5 recipes');
    // A Maybe-the-same row has its Merge button there instead, as in the mockups; nothing is
    // said about an ingredient no recipe uses.
    const maybe = page.getByRole('listitem').filter({ hasText: 'Drumsticks (moringa)' });
    expect(maybe.getByText(/recipe/).elements()).toHaveLength(0);
  });

  it('“Not in any recipe · 9” is a filter beside Staples, and asks the server for it', async () => {
    const chip = page.getByRole('button', { name: 'Not in any recipe · 9' });
    await expect.element(chip).toBeVisible();
    const chips = Array.from(document.querySelectorAll('.chips button')).map((b) =>
      b.textContent?.trim()
    );
    expect(chips.slice(0, 3)).toEqual(['All', 'Staples', 'Not in any recipe · 9']);
    await expect.element(chip).toHaveAttribute('aria-pressed', 'false');
    await chip.click();
    await expect.element(chip).toHaveAttribute('aria-pressed', 'true');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?filter=unused&limit=50')).toBe(true)
    );
  });

  it('says so calmly when every ingredient is in a recipe', async () => {
    await page.getByRole('button', { name: 'Not in any recipe · 9' }).click();
    await expect.element(page.getByText('Every ingredient is in a recipe.')).toBeVisible();
  });

  it('Merge is greyed out while the server can’t be reached', async () => {
    const merge = page.getByRole('button', { name: 'Merge', exact: true });
    await expect.element(merge).toBeEnabled();
    network.offline = true;
    flushSync();
    try {
      await expect.element(merge).toBeDisabled();
    } finally {
      network.reset();
    }
  });

  it('Merge on a Maybe-the-same row merges straight away, with Undo', async () => {
    await page.getByRole('button', { name: 'Merge', exact: true }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === '/foods/40/merge')?.body).toMatchObject({
        into_id: 12
      })
    );
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Merged Drumsticks (moringa) into Drumsticks')
    );
    expect(toasts.current?.action?.label).toBe('Undo');
  });

  it('New ingredient asks Pantry keeps it by, makes it and opens it', async () => {
    requests.length = 0;
    // A phone shows the round + (the words would squeeze the title); a computer the words.
    await expect
      .element(page.getByRole('button', { name: '+ New ingredient' }))
      .not.toBeInTheDocument();
    await page.getByRole('button', { name: 'New ingredient', exact: true }).click();
    await expect.element(page.getByRole('heading', { name: 'Pantry keeps it by' })).toBeVisible();
    await expect
      .element(page.getByText(/The way you buy it: a 500.g jar → by weight\./))
      .toBeVisible();
    await page.getByRole('textbox', { name: 'Name' }).fill('Tahini');
    await page.getByRole('radio', { name: /One by one/ }).click();
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'POST' && r.path === '/foods')?.body).toEqual({
        name: 'Tahini',
        staple: false,
        counted_as: 'count'
      })
    );
  });

  describe('“+ New ingredient: …” in the search box (F97)', () => {
    const search = () => page.getByRole('searchbox', { name: 'Search ingredients' });
    const offer = (name: string) =>
      page.getByRole('button', { name: `+ New ingredient: “${name}”` });

    it('is offered when nothing has the typed name, and asks with the name filled in', async () => {
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
      await search().fill('tahini');
      await expect.element(offer('tahini')).toBeVisible();
      requests.length = 0;
      await offer('tahini').click();
      await expect.element(page.getByRole('heading', { name: 'Pantry keeps it by' })).toBeVisible();
      await expect.element(page.getByText('tahini', { exact: true }).last()).toBeVisible();
      await page.getByRole('radio', { name: /One by one/ }).click();
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await vi.waitFor(() =>
        expect(
          requests.find((r) => r.method === 'POST' && r.path === '/foods')?.body
        ).toMatchObject({
          name: 'tahini',
          counted_as: 'count'
        })
      );
      // The new ingredient is opened (as the button by the title does), and the search is cleared.
      await expect.element(search()).toHaveValue('');
    });

    it('is offered at the end of partial matches, but not for an exact name or other name', async () => {
      await search().fill('toor');
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect.element(offer('toor')).toBeVisible();
      await search().fill('  TOOR   dal ');
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
      await search().fill('arhar dal');
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
    });

    it('offers nothing for a name the server found by folding accents and spaces', async () => {
      const pepper = toorDal({ id: 60, name: 'Jalapeño', other_names: [], counted_as: 'count' });
      const flakes = toorDal({
        id: 61,
        name: 'Chilli flakes',
        other_names: [],
        counted_as: 'count'
      });
      fakeApi({
        'GET /foods': (request) => {
          const q = new URLSearchParams(request.url.split('?')[1]).get('q') ?? '';
          const foods = q.includes('jalapeno') ? [rowOf(pepper)] : [rowOf(flakes)];
          return [
            200,
            {
              total: 2,
              counts: { all: 2, staples: 0, unused: 0, maybe_same: 0, maybe_same_pairs: 0 },
              foods,
              next: null
            }
          ];
        },
        'GET /places': [200, { places: PLACES }],
        'GET /shops': [200, { shops: SHOPS }]
      });
      await search().fill('jalapeno');
      await expect.element(page.getByRole('button', { name: /^Jalapeño/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
      await search().fill('chilli  flakes');
      await expect.element(page.getByRole('button', { name: /^Chilli flakes/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
    });

    it('is hidden while the server can’t be reached, and with another filter', async () => {
      await search().fill('tahini');
      await expect.element(offer('tahini')).toBeVisible();
      network.offline = true;
      flushSync();
      try {
        await expect.element(offer('tahini')).not.toBeInTheDocument();
      } finally {
        network.reset();
      }
      await expect.element(offer('tahini')).toBeVisible();
      await page.getByRole('button', { name: 'Staples' }).click();
      await expect.element(offer('tahini')).not.toBeInTheDocument();
    });

    it('Enter with nothing found asks for the name, as Enter does in Shopping', async () => {
      await search().fill('tahini');
      await expect.element(offer('tahini')).toBeVisible();
      await search().click();
      await userEvent.keyboard('{Enter}');
      await expect.element(page.getByRole('heading', { name: 'Pantry keeps it by' })).toBeVisible();
      await expect.element(page.getByText('tahini', { exact: true }).last()).toBeVisible();
    });
  });

  it('a computer shows the words “+ New ingredient”, not the round +', async () => {
    await page.viewport(1300, 900);
    await expect.element(page.getByRole('button', { name: '+ New ingredient' })).toBeVisible();
    expect(
      page.getByRole('button', { name: 'New ingredient', exact: true }).elements()
    ).toHaveLength(0);
  });

  it('has no Recent changes of its own: that list is in Settings (F172)', async () => {
    await page.viewport(1300, 900);
    expect(page.getByRole('button', { name: /^Recent changes/ }).elements()).toHaveLength(0);
    expect(page.getByRole('region', { name: 'Recent changes' }).elements()).toHaveLength(0);
    await page.viewport(390, 800);
    expect(page.getByRole('button', { name: /^Recent changes/ }).elements()).toHaveLength(0);
    expect(requests.filter((r) => r.path === '/changes')).toHaveLength(0);
  });

  it('opens with the Staples filter when Pantry’s Edit staples link asked for it', async () => {
    unmount(component!);
    document.body.innerHTML = '';
    requests.length = 0;
    route.search = '?filter=staples';
    try {
      component = mount(Ingredients, { target: document.body });
      flushSync();
      await vi.waitFor(() =>
        expect(requests.some((r) => r.url === '/foods?filter=staples&limit=50')).toBe(true)
      );
      await expect
        .element(page.getByRole('button', { name: 'Staples', exact: true }))
        .toHaveAttribute('aria-pressed', 'true');
    } finally {
      route.search = '';
    }
  });
});
