import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { PlanItem, PlanMeal } from '#lib/client/plan.js';
import CookedParts from './CookedParts.svelte';
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

function show(status: PlanMeal['status'], items: PlanItem[]) {
  const meal: PlanMeal = {
    id: 5,
    date: '2026-11-02',
    slot_id: 1,
    status,
    items,
    kcal: null,
    eater_login_ids: []
  };
  component = mount(CookedParts, { target: document.body, props: { meal, plan: null } });
  flushSync();
}

describe('Today’s “Cooked …” line under a meal cooked in parts (F157)', () => {
  it('names the recipes cooked so far, and only those', async () => {
    show('planned', [item(1, 'Khichdi', false), item(2, 'Soup', true), item(3, 'Raita', true)]);
    await expect
      .element(page.getByTestId('today-cooked-parts'))
      .toHaveTextContent('Cooked Soup and Raita');
  });

  it('is not there when nothing is cooked, or when the whole meal is', () => {
    show('planned', [item(1, 'Khichdi', false)]);
    expect(page.getByTestId('today-cooked-parts').elements()).toHaveLength(0);
    unmount(component!);
    document.body.innerHTML = '';
    show('cooked', [item(1, 'Khichdi', true)]);
    expect(page.getByTestId('today-cooked-parts').elements()).toHaveLength(0);
  });
});
