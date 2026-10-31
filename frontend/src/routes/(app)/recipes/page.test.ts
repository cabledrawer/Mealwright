import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { RecipePage, RecipeRow } from '#lib/client/recipes.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Recipes from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const row = (id: number, name: string, extra: Partial<RecipeRow> = {}): RecipeRow => ({
  id,
  name,
  description: null,
  makes: null,
  photo: null,
  version: 1,
  time_minutes: null,
  serves: 4,
  tags: [],
  ingredient_count: 5,
  kcal: null,
  stock: null,
  use_soon: null,
  stock_unchecked: false,
  ...extra
});

const sambar = row(1, 'Sambar', {
  time_minutes: 50,
  kcal: 320,
  tags: ['Batch-friendly'],
  stock: { counted: 7, missing: 1, can_cook_now: false }
});
const palak = row(2, 'Palak paneer', {
  stock: { counted: 3, missing: 0, can_cook_now: true },
  use_soon: { foods: [{ id: 9, name: 'Spinach' }], use_by: '2026-10-20', days_left: 0 }
});
const rajma = row(3, 'Rajma', { time_minutes: 60 });

const answer = (recipes: RecipeRow[], all = recipes.length, next: string | null = null) =>
  [200, { total: recipes.length, all_recipes: all, recipes, next } satisfies RecipePage] as [
    number,
    unknown
  ];

const TAGS = [
  { name: 'Batch-friendly', recipes: 1 },
  { name: 'Quick', recipes: 2 }
];

describe('the All recipes page', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];

  /** Open the page with the server answering `routes` (the list and the tags by default). */
  function open(routes: Parameters<typeof fakeApi>[0] = {}) {
    requests = fakeApi({
      'GET /recipes/tags': [200, { tags: TAGS }],
      'GET /recipes?limit=50': answer([palak, rajma, sambar]),
      ...routes
    });
    component = mount(Recipes, { target: document.body });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  it('shows the count in the title and the list, with each recipe’s line', async () => {
    open();
    await expect.element(page.getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
    await expect.element(page.getByText('3 recipes')).toBeVisible();
    await expect
      .element(page.getByText('50 min · 320 kcal · all in stock but 1'))
      .toBeInTheDocument();
    await expect.element(page.getByText('Uses spinach (today)')).toBeVisible();
    await expect.element(page.getByText('60 min · nutrition unknown')).toBeVisible();
    // A to Z is the server's order; the page keeps it.
    const names = [...document.querySelectorAll('li .name')].map((n) => n.textContent);
    expect(names).toEqual(['Palak paneer', 'Rajma', 'Sambar']);
  });

  it('says “1 recipe” for one', async () => {
    open({ 'GET /recipes?limit=50': answer([sambar]) });
    await expect.element(page.getByText('1 recipe', { exact: true })).toBeVisible();
  });

  it('has the Drafts and Ingredients buttons and New recipe', async () => {
    open();
    await expect
      .element(page.getByRole('link', { name: 'Drafts' }))
      .toHaveAttribute('href', '/recipes/drafts');
    await expect
      .element(page.getByRole('link', { name: 'Ingredients' }))
      .toHaveAttribute('href', '/recipes/ingredients');
    await expect
      .element(page.getByRole('link', { name: 'New recipe' }))
      .toHaveAttribute('href', '/recipes/new');
    await expect.element(page.getByText('Sambar')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/Planned/);
    await expect
      .element(page.getByRole('link', { name: 'Import a recipe' }))
      .toHaveAttribute('href', '/recipes/import');
  });

  it('shows how many drafts there are on the Drafts button, and no number for none', async () => {
    open();
    await expect.element(page.getByRole('link', { name: 'Drafts', exact: true })).toBeVisible();
    drafts.loaded = true;
    drafts.drafts = [1, 2, 3].map((id) => ({
      id,
      name: `Draft ${id}`,
      source: { kind: 'text' as const, site: null },
      started_by: 'Wren',
      started_at: '2026-10-20T10:00:00Z',
      updated_at: '2026-10-22T10:00:00Z',
      expires_at: '2026-11-06T10:00:00Z',
      days_left: 13,
      lines_total: 3,
      lines_checked: 1
    }));
    flushSync();
    await expect.element(page.getByRole('link', { name: 'Drafts 3' })).toBeVisible();
    drafts.forget();
  });

  it('each row opens its recipe', async () => {
    open();
    await expect.element(page.getByText('Sambar')).toBeVisible();
    const links = [...document.querySelectorAll('li a')].map((a) => a.getAttribute('href'));
    expect(links).toEqual(['/recipes/2', '/recipes/3', '/recipes/1']); // A to Z: Palak, Rajma, Sambar
    expect(document.querySelectorAll('li button')).toHaveLength(0);
  });

  it('has a filter row: All, Can cook now, Use soon, then the household’s tags', async () => {
    open();
    const group = page.getByRole('group', { name: 'Show' });
    await expect.element(group).toBeVisible();
    const labels = [...document.querySelectorAll('[aria-label="Show"] button')].map(
      (b) => b.textContent
    );
    expect(labels).toEqual(['All', 'Can cook now', 'Use soon', 'Batch-friendly', 'Quick']);
    await expect
      .element(group.getByRole('button', { name: 'All', exact: true }))
      .toHaveAttribute('aria-pressed', 'true');
  });

  it('Can cook now asks the server for just those', async () => {
    open({ 'GET /recipes?can_cook_now=true&limit=50': answer([palak], 3) });
    await page.getByRole('button', { name: 'Can cook now' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/recipes?can_cook_now=true&limit=50')).toBe(true)
    );
    await expect.element(page.getByText('Rajma')).not.toBeInTheDocument();
    // The title still counts every recipe.
    await expect.element(page.getByText('3 recipes')).toBeVisible();
  });

  it('Use soon asks the server for the recipes that use something about to go off, and works with search', async () => {
    open({
      'GET /recipes?use_soon=true&limit=50': answer([palak], 3),
      'GET /recipes?q=palak&use_soon=true&limit=50': answer([palak], 3)
    });
    const chip = page.getByRole('button', { name: 'Use soon', exact: true });
    await chip.click();
    await expect.element(chip).toHaveAttribute('aria-pressed', 'true');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/recipes?use_soon=true&limit=50')).toBe(true)
    );
    await expect.element(page.getByText('Rajma')).not.toBeInTheDocument();
    await expect.element(page.getByText('3 recipes')).toBeVisible(); // the title counts every recipe
    await page.getByRole('searchbox', { name: 'Search recipes' }).fill('palak');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/recipes?q=palak&use_soon=true&limit=50')).toBe(true)
    );
  });

  it('says so when no recipe uses anything that needs using up soon', async () => {
    open({ 'GET /recipes?use_soon=true&limit=50': answer([], 3) });
    await page.getByRole('button', { name: 'Use soon', exact: true }).click();
    await expect
      .element(page.getByText('No recipe uses anything that needs using up soon.'))
      .toBeVisible();
  });

  it('a tag filters, and search works with it', async () => {
    open({
      'GET /recipes?tag=Quick&limit=50': answer([rajma], 3),
      'GET /recipes?q=dal&tag=Quick&limit=50': answer([], 3)
    });
    await page.getByRole('button', { name: 'Quick' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/recipes?tag=Quick&limit=50')).toBe(true)
    );
    await page.getByRole('searchbox', { name: 'Search recipes' }).fill('dal');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/recipes?q=dal&tag=Quick&limit=50')).toBe(true)
    );
    await expect.element(page.getByText('No recipe matches “dal”.')).toBeVisible();
  });

  it('searches on the server, by whatever words are typed', async () => {
    open({ 'GET /recipes?q=thuvaram&limit=50': answer([sambar], 3) });
    await page.getByRole('searchbox', { name: 'Search recipes' }).fill('thuvaram');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/recipes?q=thuvaram&limit=50')).toBe(true)
    );
    await expect.element(page.getByText('Palak paneer')).not.toBeInTheDocument();
  });

  it('says so when Can cook now finds nothing', async () => {
    open({ 'GET /recipes?can_cook_now=true&limit=50': answer([], 3) });
    await page.getByRole('button', { name: 'Can cook now' }).click();
    await expect
      .element(page.getByText('No recipe can be cooked with what is in stock right now.'))
      .toBeVisible();
  });

  it('shows the first page and adds the next with Show more', async () => {
    open({
      'GET /recipes?limit=50': answer([sambar], 2, '1'),
      'GET /recipes?after=1&limit=50': answer([palak], 2)
    });
    await page.getByRole('button', { name: 'Show more' }).click();
    await expect.element(page.getByText('Palak paneer')).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Show more' })).not.toBeInTheDocument();
  });

  it('a failed Show more keeps the rows, the count and the filters, and Try again adds the next page', async () => {
    let fail = true;
    open({
      'GET /recipes?limit=50': answer([sambar], 2, '1'),
      'GET /recipes?after=1&limit=50': () =>
        fail ? [500, { detail: 'broken' }] : answer([palak], 2)
    });
    await page.getByRole('button', { name: 'Show more' }).click();
    await expect.element(page.getByText('Couldn’t load more recipes. Try again.')).toBeVisible();
    await expect.element(page.getByText('Sambar')).toBeVisible();
    await expect.element(page.getByText('2 recipes')).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Can cook now' })).toBeVisible();
    expect(document.body.textContent).not.toMatch(/Couldn’t load your recipes/);
    fail = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect.element(page.getByText('Palak paneer')).toBeVisible();
    await expect.element(page.getByText('Sambar')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/Couldn’t load more/);
    await expect.element(page.getByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('with no recipes at all, says so, and offers New recipe', async () => {
    open({ 'GET /recipes?limit=50': answer([], 0), 'GET /recipes/tags': [200, { tags: [] }] });
    await expect.element(page.getByRole('heading', { name: 'No recipes yet' })).toBeVisible();
    await expect.element(page.getByText('Recipes you add will show here.')).toBeVisible();
    await expect.element(page.getByText('0 recipes')).toBeVisible();
    expect(document.querySelector('[role="searchbox"], input[type="search"]')).toBeNull();
    await expect
      .element(page.getByRole('link', { name: 'New recipe' }))
      .toHaveAttribute('href', '/recipes/new');
    expect(document.body.textContent).not.toMatch(/Add a recipe/);
    await expect.element(page.getByRole('link', { name: 'Import a recipe' })).toBeVisible();
    expect(document.querySelectorAll('main button, button')).toHaveLength(0);
  });

  it('says Loading… while the first answer is on its way', async () => {
    open({ 'GET /recipes?limit=50': () => new Promise(() => {}) as never });
    await expect.element(page.getByText('Loading…')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/No recipes yet/);
  });

  it('says what went wrong and offers Try again', async () => {
    let fail = true;
    open({
      'GET /recipes?limit=50': () => (fail ? [500, { detail: 'broken' }] : answer([sambar]))
    });
    await expect.element(page.getByText('Couldn’t load your recipes. Try again.')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/No recipes yet/);
    fail = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect.element(page.getByText('Sambar')).toBeVisible();
  });

  it('long names wrap instead of pushing the page sideways', async () => {
    const long = row(
      4,
      'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது'.repeat(2),
      {
        use_soon: {
          foods: [
            { id: 1, name: 'Organic stone-ground whole wheat flour from the Saturday market' }
          ],
          use_by: '2026-10-20',
          days_left: 0
        }
      }
    );
    open({ 'GET /recipes?limit=50': answer([long]) });
    await expect.element(page.getByText(/பச்சைப்/).first()).toBeVisible();
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
  });

  it('offline from the start, the list not loaded: says it needs the server', async () => {
    network.offline = true;
    network.deviceOffline = true;
    open({
      'GET /recipes?limit=50': [502, ''],
      'GET /recipes/tags': [502, '']
    });
    await expect.element(page.getByRole('heading', { name: 'You’re offline.' })).toBeVisible();
    await expect
      .element(
        page.getByText('Recipes needs your Mealwright server. Your shopping list works offline.')
      )
      .toBeVisible();
    expect(document.body.textContent).not.toContain('New recipe');
  });

  it('the list already showing stays when the bar comes (F80)', async () => {
    open();
    await expect.element(page.getByText('Sambar')).toBeVisible();
    network.offline = true;
    network.deviceOffline = true;
    flushSync();
    await expect.element(page.getByText('Sambar')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/Can’t reach|You’re offline\./);
  });
});
