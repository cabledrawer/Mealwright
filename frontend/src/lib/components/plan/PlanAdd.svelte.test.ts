import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { PlanActions } from '#lib/planActions.js';
import PlanAdd from './PlanAdd.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// The recipe list is a stand-in with one recipe, and no ingredient search goes out.
vi.mock('#lib/recipes.svelte.js', () => ({
  RecipeList: class {
    query = '';
    recipes = [{ id: 7, name: 'Stew', time_minutes: null, kcal: null }];
    loaded = true;
    problem = null;
    load = async () => {};
  }
}));
vi.mock('#lib/client/foods.js', () => ({ listFoods: vi.fn(async () => ({ foods: [] })) }));

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

describe('Cook once here… (F52) and a late answer', () => {
  it('opens Cook once only if the sheet is still on the same day when the plan answers', async () => {
    let answer: (value: unknown) => void = () => {};
    const openCookOnce = vi.fn();
    const model = {
      slotsOn: [{ id: 1, name: 'Dinner' }],
      slotName: () => 'Dinner',
      tubsLeft: [],
      today: '2026-11-02',
      add: () => new Promise((resolve) => (answer = resolve))
    };
    const actions = { model, readonly: false, openCookOnce } as unknown as PlanActions;
    const props = $state({
      actions,
      target: { day: '2026-11-03', slotId: 1 } as { day: string; slotId: number | null } | null,
      onclose: () => {}
    });
    component = mount(PlanAdd, { target: document.body, props });
    flushSync();
    await page.getByRole('button', { name: 'Cook once here…' }).click();
    await page.getByRole('button', { name: /Stew/ }).click();
    // The sheet is opened on another day before the answer comes.
    props.target = { day: '2026-11-04', slotId: 1 };
    flushSync();
    answer({ ok: true, value: { meal_id: 5, item_id: 9 } });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(openCookOnce).not.toHaveBeenCalled();
  });

  it('opens Cook once when the answer comes and nothing changed', async () => {
    let answer: (value: unknown) => void = () => {};
    const openCookOnce = vi.fn();
    const model = {
      slotsOn: [{ id: 1, name: 'Dinner' }],
      slotName: () => 'Dinner',
      tubsLeft: [],
      today: '2026-11-02',
      add: () => new Promise((resolve) => (answer = resolve))
    };
    const actions = { model, readonly: false, openCookOnce } as unknown as PlanActions;
    component = mount(PlanAdd, {
      target: document.body,
      props: { actions, target: { day: '2026-11-03', slotId: 1 }, onclose: () => {} }
    });
    flushSync();
    await page.getByRole('button', { name: 'Cook once here…' }).click();
    await page.getByRole('button', { name: /Stew/ }).click();
    answer({ ok: true, value: { meal_id: 5, item_id: 9 } });
    await vi.waitFor(() => expect(openCookOnce).toHaveBeenCalledTimes(1));
  });
});
