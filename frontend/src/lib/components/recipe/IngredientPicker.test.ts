import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { FoodRow } from '#lib/client/types.js';
import IngredientPicker from './IngredientPicker.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;
afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

const food = (
  id: number,
  name: string,
  matched_name: string | null = null,
  used_in_recipes?: number,
  other_names: string[] = matched_name ? [matched_name] : []
): FoodRow => ({ id, name, matched_name, other_names, used_in_recipes }) as unknown as FoodRow;
const brief = (id: number, name: string) => ({
  id,
  name,
  description: null,
  makes: id === 3 ? { amount: 200, amount_text: '200', unit: 'g' } : null,
  version: 1
});

function render(props: Record<string, unknown>) {
  component = mount(IngredientPicker, {
    target: document.body,
    props: { id: 'list', ...props } as never
  });
  flushSync();
}

const search = async () => ({
  foods: [food(7, 'Toor dal', 'thuvaram paruppu', 4)],
  recipes: [brief(3, 'Sambar powder'), brief(1, 'Sambar')]
});

const key = (name: string) => new KeyboardEvent('keydown', { key: name, cancelable: true });

describe('IngredientPicker', () => {
  it('is a listbox of options: ingredients with other names and recipe counts, then recipes', async () => {
    render({ query: 'thuvaram', search, onpick: () => {}, oncreate: () => {} });
    await expect.element(page.getByRole('listbox', { name: 'Matching ingredients' })).toBeVisible();
    await expect
      .element(
        page.getByRole('option', { name: /^Toor dal.*also called thuvaram paruppu · in 4 recipes/ })
      )
      .toBeVisible();
    await expect.element(page.getByText('recipe · makes 200 g')).toBeVisible();
    await expect.element(page.getByRole('status')).toHaveTextContent('3 matches');
  });

  it('says "in 1 recipe", "in no recipes", and shows the first other name when the name itself matched', async () => {
    render({
      query: 'dru',
      search: async () => ({
        foods: [
          food(1, 'Drumsticks', null, 2, ['murungakkai']),
          food(2, 'Drumstick leaves', null, 1),
          food(3, 'Drumstick pickle', null, 0)
        ],
        recipes: []
      }),
      onpick: () => {},
      oncreate: () => {}
    });
    await expect
      .element(
        page.getByRole('option', { name: /^Drumsticks.*also called murungakkai · in 2 recipes/ })
      )
      .toBeVisible();
    await expect.element(page.getByText('in 1 recipe', { exact: true })).toBeVisible();
    await expect.element(page.getByText('in no recipes', { exact: true })).toBeVisible();
  });

  it('picks an ingredient or a recipe by clicking', async () => {
    const picked: unknown[] = [];
    render({ query: 'sam', search, onpick: (p: unknown) => picked.push(p), oncreate: () => {} });
    await page.getByRole('option', { name: /^Toor dal/ }).click();
    await page.getByRole('option', { name: /^Sambar powder/ }).click();
    expect(picked).toEqual([
      { kind: 'ingredient', food: { id: 7, name: 'Toor dal' }, otherNames: ['thuvaram paruppu'] },
      { kind: 'recipe', recipe: { id: 3, name: 'Sambar powder' } }
    ]);
  });

  it('the arrow keys move through the options (activeId follows), Enter picks, nothing is picked before', async () => {
    const picked: unknown[] = [];
    let active: string | undefined;
    component = mount(IngredientPicker, {
      target: document.body,
      props: {
        id: 'list',
        query: 'sam',
        search,
        onpick: (p: unknown) => picked.push(p),
        oncreate: () => {},
        get activeId() {
          return active;
        },
        set activeId(v: string | undefined) {
          active = v;
        }
      } as never
    });
    flushSync();
    const picker = component as unknown as { key: (e: KeyboardEvent) => boolean };
    await expect.element(page.getByRole('option', { name: /^Toor dal/ })).toBeVisible();
    // Enter before the arrows has nothing to pick.
    expect(picker.key(key('Enter'))).toBe(false);
    expect(picked).toEqual([]);
    expect(picker.key(key('ArrowDown'))).toBe(true);
    flushSync();
    await expect
      .element(page.getByRole('option', { name: /^Toor dal/ }))
      .toHaveAttribute('aria-selected', 'true');
    expect(active).toBe('list-f7');
    picker.key(key('ArrowDown'));
    flushSync();
    expect(active).toBe('list-r3');
    picker.key(key('ArrowUp'));
    flushSync();
    expect(active).toBe('list-f7');
    expect(picker.key(key('Enter'))).toBe(true);
    expect(picked).toEqual([
      { kind: 'ingredient', food: { id: 7, name: 'Toor dal' }, otherNames: ['thuvaram paruppu'] }
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
    const row = page.getByRole('option', { name: /^Sambar rice/ });
    await expect.element(row).toHaveAttribute('aria-disabled', 'true');
    await expect.element(page.getByText(reason)).toBeVisible();
    await row.click({ force: true });
    expect(onpick).not.toHaveBeenCalled();
  });

  it('offers + New ingredient last, for a name nobody has, and not for one that exists exactly', async () => {
    const oncreate = vi.fn();
    render({
      query: 'Kokum',
      search: async () => ({ foods: [], recipes: [] }),
      onpick: () => {},
      oncreate
    });
    await page.getByRole('option', { name: '+ New ingredient “Kokum”' }).click();
    expect(oncreate).toHaveBeenCalledWith('Kokum');
    unmount(component!);
    document.body.innerHTML = '';
    render({ query: 'toor dal', search, onpick: () => {}, oncreate });
    await expect.element(page.getByRole('option', { name: /^Toor dal/ })).toBeVisible();
    await expect
      .element(page.getByRole('option', { name: /New ingredient/ }))
      .not.toBeInTheDocument();
  });

  it('puts + New ingredient after the matches', async () => {
    render({
      query: 'dru',
      search: async () => ({ foods: [food(1, 'Drumsticks', null, 2)], recipes: [] }),
      onpick: () => {},
      oncreate: () => {}
    });
    await expect.element(page.getByRole('option', { name: /^Drumsticks/ })).toBeVisible();
    const names = [...document.querySelectorAll('[role=option]')].map((o) => o.textContent ?? '');
    expect(names).toHaveLength(2);
    expect(names[1]).toContain('+ New ingredient “dru”');
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
