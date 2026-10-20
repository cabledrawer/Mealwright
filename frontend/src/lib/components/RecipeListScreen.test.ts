import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { RecipePage, RecipeRow } from '$lib/client/recipes';
import { network } from '$lib/network.svelte';
import { RecipeList } from '$lib/recipes.svelte';
import { fakeApi } from '$lib/testing/fakeApi';
import RecipeListScreen from './RecipeListScreen.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const row = (id: number, name: string): RecipeRow => ({
  id,
  name,
  description: null,
  makes: null,
  version: 1,
  time_minutes: 30,
  serves: 4,
  tags: [],
  ingredient_count: 3,
  kcal: null,
  stock: null,
  use_soon: null,
  stock_unchecked: false
});

const rows = [row(1, 'Sambar'), row(2, 'Palak paneer'), row(3, 'Rajma')];
const answer = (recipes: RecipeRow[]) =>
  [
    200,
    { total: recipes.length, all_recipes: recipes.length, recipes, next: null } satisfies RecipePage
  ] as [number, unknown];

// The list as the desktop's middle pane (`pane`): its own title, the open recipe's row marked,
// no Ingredients button (the sidebar has it), no page header.
describe('All recipes as the middle pane', () => {
  let component: ReturnType<typeof mount> | null = null;

  function open(
    props: { currentId?: number | null; pane?: boolean; list?: RecipeList } = {},
    answers: Record<string, [number, unknown]> = {}
  ) {
    fakeApi({
      'GET /recipes/tags': [200, { tags: [] }],
      'GET /recipes?limit=50': answer(rows),
      ...answers
    });
    component = mount(RecipeListScreen, { target: document.body, props: { pane: true, ...props } });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(1280, 800);
    network.reset();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  it('is a region called Recipe list, with the title and the count', async () => {
    open();
    await expect.element(page.getByRole('region', { name: 'Recipe list' })).toBeVisible();
    await expect.element(page.getByRole('heading', { name: 'Recipes', level: 1 })).toBeVisible();
    await expect.element(page.getByText('3 recipes')).toBeVisible();
  });

  it('has no Ingredients button and no page header, but keeps search, filters and rows', async () => {
    open();
    await expect.element(page.getByText('Sambar')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/Ingredients|Drafts|New recipe|Import|Planned/);
    expect(document.querySelector('.page-header')).toBeNull();
    await expect.element(page.getByRole('searchbox', { name: 'Search recipes' })).toBeVisible();
    await expect.element(page.getByRole('group', { name: 'Show' })).toBeVisible();
  });

  it('marks the open recipe’s row as the current page, and no other', async () => {
    open({ currentId: 2 });
    await expect.element(page.getByText('Palak paneer')).toBeVisible();
    const current = [...document.querySelectorAll('li a[aria-current="page"]')].map((a) =>
      a.getAttribute('href')
    );
    expect(current).toEqual(['/recipes/2']);
  });

  it('marks no row when no recipe is open, and the title is the page’s heading', async () => {
    open({ currentId: null });
    await expect.element(page.getByText('Sambar')).toBeVisible();
    expect(document.querySelectorAll('li a[aria-current]')).toHaveLength(0);
    await expect.element(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  it('with a recipe open the title is a second-level heading, so the recipe’s name is the one h1', async () => {
    open({ currentId: 1 });
    await expect.element(page.getByRole('heading', { name: 'Recipes', level: 2 })).toBeVisible();
    expect(document.querySelectorAll('h1')).toHaveLength(0);
  });

  it('rows are links that open the recipe, never buttons', async () => {
    open();
    await expect.element(page.getByText('Rajma')).toBeVisible();
    const links = [...document.querySelectorAll('li a')].map((a) => a.getAttribute('href'));
    expect(links).toEqual(['/recipes/1', '/recipes/2', '/recipes/3']);
    expect(document.querySelectorAll('li button')).toHaveLength(0);
  });

  it('in the panes, rows keep the Use soon filter in the recipe’s address, so a reload and Back find it', async () => {
    open(
      { list: new RecipeList('soon') },
      { 'GET /recipes?use_soon=true&limit=50': answer([rows[1]!]) }
    );
    await expect.element(page.getByText('Palak paneer')).toBeVisible();
    expect([...document.querySelectorAll('li a')].map((a) => a.getAttribute('href'))).toEqual([
      '/recipes/2?filter=use-soon'
    ]);
    await expect
      .element(page.getByRole('button', { name: 'Use soon', exact: true }))
      .toHaveAttribute('aria-pressed', 'true');
  });

  it('offline it leaves the note to the panes’ layout (one for both panes)', async () => {
    open();
    await expect.element(page.getByText('Sambar')).toBeVisible();
    network.offline = true;
    flushSync();
    expect(document.body.textContent).not.toContain('needs your Mealwright server');
  });
});
