import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { PlanItem, PlanMeal } from '#lib/client/plan.js';
import MealRecipes from './MealRecipes.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function item(id: number, name: string, cooked: boolean): PlanItem {
  return {
    id,
    position: id,
    kind: 'recipe',
    recipe: { id, name, removed: false, photo_url: null, time_minutes: null, kcal: null },
    tub_id: null,
    ingredient: null,
    kept_name: null,
    servings: 2,
    note: null,
    eating: 2,
    cooked
  };
}

function show(
  status: PlanMeal['status'],
  items: PlanItem[],
  oncook: (i: PlanItem) => void = () => {}
) {
  const meal: PlanMeal = {
    id: 5,
    date: '2026-11-02',
    slot_id: 1,
    status,
    items,
    kcal: null,
    eater_login_ids: []
  };
  component = mount(MealRecipes, { target: document.body, props: { meal, plan: null, oncook } });
  flushSync();
}

describe('Today’s lines for a meal cooked in parts (F160)', () => {
  it('ticks the cooked recipes and gives the others their own Cooked it', async () => {
    const pressed: number[] = [];
    show('planned', [item(1, 'Khichdi', false), item(2, 'Soup', true)], (i) => pressed.push(i.id));
    const lines = page.getByTestId('today-cooked-parts');
    await expect.element(lines).toBeVisible();
    expect(lines.element().textContent).toContain('Soup');
    await expect.element(lines.getByText('Cooked', { exact: true })).toBeVisible();
    const button = page.getByRole('button', { name: 'Cooked it: Khichdi' });
    await expect.element(button).toBeVisible();
    expect(page.getByRole('button').elements()).toHaveLength(1); // the cooked one has none
    expect(button.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    await button.click();
    expect(pressed).toEqual([1]);
  });

  it('gives a recipe taken out of the recipe list no Cooked it (F158 review)', async () => {
    const gone = item(3, 'Old stew', false);
    gone.recipe!.removed = true;
    show('planned', [item(1, 'Khichdi', false), gone]);
    await expect.element(page.getByRole('button', { name: 'Cooked it: Khichdi' })).toBeVisible();
    expect(page.getByRole('button').elements()).toHaveLength(1);
    expect(page.getByTestId('today-cooked-parts').element().textContent).toContain('Old stew');
  });
});
