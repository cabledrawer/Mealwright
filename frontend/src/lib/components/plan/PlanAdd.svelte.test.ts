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

type Target = { day: string; slotId: number | null } | null;

/** Mounts the sheet on a day, picks "Cook once here…" and the recipe; the plan answers later. */
async function startCooking(first: Target) {
  let answer: (value: unknown) => void = () => {};
  const openCookOnce = vi.fn();
  const model = {
    slotsOn: [
      { id: 1, name: 'Dinner' },
      { id: 2, name: 'Lunch' }
    ],
    slotName: () => 'Dinner',
    tubsLeft: [],
    today: '2026-11-02',
    add: () => new Promise((resolve) => (answer = resolve))
  };
  const actions = { model, readonly: false, openCookOnce } as unknown as PlanActions;
  const props = $state({ actions, target: first, onclose: () => {} });
  component = mount(PlanAdd, { target: document.body, props });
  flushSync();
  await page.getByRole('button', { name: 'Cook once here…' }).click();
  await page.getByRole('button', { name: /Stew/ }).click();
  const reply = async () => {
    answer({ ok: true, value: { meal_id: 5, item_id: 9 } });
    for (let n = 0; n < 20; n++) await Promise.resolve(); // let the continuation run
  };
  return { props, openCookOnce, reply };
}

describe('Cook once here… (F52) and a late answer', () => {
  it('opens Cook once when the answer comes and nothing changed', async () => {
    const { openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    await reply();
    await vi.waitFor(() => expect(openCookOnce).toHaveBeenCalledTimes(1));
  });

  it('does nothing if the sheet is opened on another day before the answer', async () => {
    const { props, openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    props.target = { day: '2026-11-04', slotId: 1 };
    flushSync();
    await reply();
    expect(openCookOnce).not.toHaveBeenCalled();
  });

  it('does nothing if the sheet is opened on another meal of the same day', async () => {
    const { props, openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    props.target = { day: '2026-11-03', slotId: 2 };
    flushSync();
    await reply();
    expect(openCookOnce).not.toHaveBeenCalled();
  });

  it('does nothing if the sheet was closed before the answer', async () => {
    const { props, openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    props.target = null;
    flushSync();
    await reply();
    expect(openCookOnce).not.toHaveBeenCalled();
  });
});
