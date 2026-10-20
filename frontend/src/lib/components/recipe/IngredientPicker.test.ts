import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { FoodRow } from '$lib/client/types';
import IngredientPicker from './IngredientPicker.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;
afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

const food = (id: number, name: string, matched_name: string | null = null): FoodRow =>
  ({ id, name, matched_name, other_names: [] }) as unknown as FoodRow;
const brief = (id: number, name: string) => ({
  id,
  name,
  description: null,
  makes: id === 3 ? { amount: 200, amount_text: '200', unit: 'g' } : null,
  version: 1
});

function render(props: Record<string, unknown>) {
  component = mount(IngredientPicker, { target: document.body, props: props as never });
  flushSync();
}

const search = async () => ({
  foods: [food(7, 'Toor dal', 'thuvaram paruppu')],
  recipes: [brief(3, 'Sambar powder'), brief(1, 'Sambar')]
});

describe('IngredientPicker', () => {
  it('finds ingredients by another name and recipes, in two groups', async () => {
    render({ query: 'thuvaram', search, onpick: () => {}, oncreate: () => {} });
    await expect.element(page.getByText('also called: thuvaram paruppu')).toBeVisible();
    await expect.element(page.getByText('Ingredients', { exact: true })).toBeVisible();
    await expect.element(page.getByText('Recipes', { exact: true })).toBeVisible();
    await expect.element(page.getByText('recipe · makes 200 g')).toBeVisible();
  });

  it('picks an ingredient or a recipe', async () => {
    const picked: unknown[] = [];
    render({ query: 'sam', search, onpick: (p: unknown) => picked.push(p), oncreate: () => {} });
    await page.getByRole('button', { name: /^Toor dal/ }).click();
    await page.getByRole('button', { name: /^Sambar powder/ }).click();
    expect(picked).toEqual([
      { kind: 'ingredient', food: { id: 7, name: 'Toor dal' } },
      { kind: 'recipe', recipe: { id: 3, name: 'Sambar powder' } }
    ]);
  });

  it('greys out a recipe that would make a loop, with the reason, and does not pick it', async () => {
    const onpick = vi.fn();
    const reason = 'Sambar can’t use Sambar rice, because Sambar rice uses Sambar.';
    render({
      query: 'sam',
      search: async () => ({ foods: [], recipes: [brief(5, 'Sambar rice')] }),
      blocked: [{ id: 5, name: 'Sambar rice', reason, chain: ['Sambar', 'Sambar rice'] }],
      onpick,
      oncreate: () => {}
    });
    const row = page.getByRole('button', { name: /^Sambar rice/ });
    await expect.element(row).toHaveAttribute('aria-disabled', 'true');
    await expect.element(page.getByText(reason)).toBeVisible();
    await row.click({ force: true });
    expect(onpick).not.toHaveBeenCalled();
  });

  it('offers + New ingredient for a name nobody has, and not for one that exists exactly', async () => {
    const oncreate = vi.fn();
    render({
      query: 'Kokum',
      search: async () => ({ foods: [], recipes: [] }),
      onpick: () => {},
      oncreate
    });
    await page.getByRole('button', { name: '+ New ingredient “Kokum”' }).click();
    expect(oncreate).toHaveBeenCalledWith('Kokum');
    unmount(component!);
    document.body.innerHTML = '';
    render({ query: 'toor dal', search, onpick: () => {}, oncreate });
    await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: /New ingredient/ }))
      .not.toBeInTheDocument();
  });

  it('says so when it can’t search', async () => {
    render({
      query: 'x',
      search: async () => {
        throw new Error('down');
      },
      onpick: () => {},
      oncreate: () => {}
    });
    await expect.element(page.getByText('Couldn’t search. Try again.')).toBeVisible();
  });
});
