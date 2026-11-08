import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { Plan, PlanItem, PlanMeal } from '#lib/client/plan.js';
import type { PlanActions, PlanTarget } from '#lib/planActions.js';
import PlanSheet from './PlanSheet.svelte';
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

/** A part-cooked dinner today: the soup is cooked, the khichdi is not. */
const khichdi = item(1, 'Khichdi', false);
const soup = item(2, 'Soup', true);
const meal: PlanMeal = {
  id: 5,
  date: '2026-11-02',
  slot_id: 1,
  status: 'planned',
  items: [khichdi, soup],
  kcal: null,
  eater_login_ids: []
};

function open(target: PlanTarget, plan: Plan | null = null) {
  const openCooked = vi.fn();
  const model = {
    slotsOn: [{ id: 1, name: 'Dinner' }],
    slotName: () => 'Dinner',
    tubsLeft: [],
    today: '2026-11-02',
    startsOn: 1,
    anchor: '2026-11-02',
    plan,
    people: [],
    removeItem: vi.fn(),
    removeMeal: vi.fn()
  };
  const actions = { model, readonly: false, openCooked } as unknown as PlanActions;
  component = mount(PlanSheet, {
    target: document.body,
    props: { actions, target, onclose: () => {} }
  });
  flushSync();
  return openCooked;
}

describe('the Plan menu of a part-cooked meal (F157)', () => {
  it('Cooked it is on the recipe not cooked yet, and not on the one that is', async () => {
    const openCooked = open({ kind: 'item', meal, item: khichdi });
    await page.getByRole('button', { name: 'Cooked it' }).click();
    expect(openCooked).toHaveBeenCalledWith(meal);
    unmount(component!);
    document.body.innerHTML = '';
    open({ kind: 'item', meal, item: soup });
    expect(page.getByRole('button', { name: 'Cooked it' }).elements()).toHaveLength(0);
  });

  it('a cooked recipe can’t be moved or removed: the menu says to Undo Cooked it', async () => {
    open({ kind: 'item', meal, item: soup });
    expect(page.getByRole('button', { name: 'Move to…' }).elements()).toHaveLength(0);
    expect(page.getByRole('button', { name: 'Remove' }).elements()).toHaveLength(0);
    await expect.element(page.getByTestId('cooked-stays')).toBeVisible();
  });

  it('nor can a meal that holds one, but the recipe not cooked yet can', async () => {
    open({ kind: 'meal', meal });
    expect(page.getByRole('button', { name: 'Remove' }).elements()).toHaveLength(0);
    unmount(component!);
    document.body.innerHTML = '';
    open({ kind: 'item', meal, item: khichdi });
    await expect.element(page.getByRole('button', { name: 'Remove' })).toBeVisible();
  });
});

describe('To freezer on a leftover tub (cabledrawer 8 Nov)', () => {
  function tubMeal(useBy: string) {
    const tubItem = { ...item(7, 'Lemon rice', false), kind: 'tub' as const, tub_id: 70 };
    const tubMeal: PlanMeal = { ...meal, id: 6, items: [tubItem] };
    const plan = {
      start: '2026-11-02',
      end: '2026-11-02',
      meals: [tubMeal],
      batch_cooks: [{ id: 3, cooked_on: '2026-10-30', recipe_name: 'Lemon rice' }],
      tubs: [
        {
          id: 70,
          batch_id: 3,
          amount_quarters: 4,
          number: 1,
          place_id: 1,
          place_kind: 'fridge',
          member_login_id: null,
          use_by: useBy
        }
      ]
    } as unknown as Plan;
    return { target: { kind: 'item', meal: tubMeal, item: tubItem } as PlanTarget, plan };
  }

  it('is greyed out with the note once the use-by date has passed', async () => {
    const { target, plan } = tubMeal('2026-11-01');
    open(target, plan);
    const button = page.getByRole('button', { name: 'To freezer' });
    await expect.element(button).toBeDisabled();
    await expect
      .element(page.getByTestId('tub-too-late'))
      .toHaveTextContent('Too late to freeze: the use by date has passed.');
    expect(button.element().getAttribute('aria-describedby')).toBe(
      page.getByTestId('tub-too-late').element().id
    );
  });

  it('still works on the use-by day itself, with no note', async () => {
    const { target, plan } = tubMeal('2026-11-02');
    open(target, plan);
    await expect.element(page.getByRole('button', { name: 'To freezer' })).toBeEnabled();
    expect(page.getByTestId('tub-too-late').elements()).toHaveLength(0);
  });
});
