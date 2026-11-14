// The meal's menu with Serves - N +, who's eating and Leftovers on… (0.7 P1), against a pretend
// server. Serves must work on a meal planned before the update (no number set).
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { Plan, PlanItem, PlanMeal, Portions } from '#lib/client/plan.js';
import { PlanModel } from '#lib/plan.svelte.js';
import type { PlanActions, PlanTarget } from '#lib/planActions.js';
import { changeOf, fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import PlanSheet from './PlanSheet.svelte';
import '../../styles/tokens.css';
import '../../styles/base.css';

const SLOTS = [
  { id: 2, name: 'Lunch', position: 1, enabled: true },
  { id: 4, name: 'Dinner', position: 3, enabled: true }
];

const recipeItem = (id: number, name: string, over: Partial<PlanItem> = {}): PlanItem => ({
  id,
  position: 0,
  kind: 'recipe',
  recipe: { id: id + 100, name, removed: false, photo_url: null, time_minutes: null, kcal: null },
  tub_id: null,
  ingredient: null,
  kept_name: null,
  servings: null,
  note: null,
  eating: 4,
  cooked: false,
  ...over
});
const noteItem = (id: number, text: string): PlanItem => ({
  ...recipeItem(id, text),
  kind: 'note',
  recipe: null,
  note: text,
  eating: null,
  cooked: false
});
const mealOf = (id: number, day: string, slot: number, items: PlanItem[]): PlanMeal => ({
  id,
  date: day,
  slot_id: slot,
  status: 'planned',
  items,
  kcal: null,
  eater_member_ids: []
});

const written = (summary: string) => ({
  change: changeOf(900, summary),
  meal_id: 1,
  item_id: 11
});

const PORTIONS: Portions = {
  recipe_name: 'Veg biryani',
  has_batch: true,
  batch_id: 7,
  portions: 4,
  cook_day: 1,
  tubs: 3,
  in_meals: 2,
  left: 1,
  use_by: '2026-10-22',
  spare_use_by: ['2026-10-22']
};

describe('the meal’s menu (0.7 P1)', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];
  let model: PlanModel;
  let target: PlanTarget | null;

  function plan(meals: PlanMeal[]): Plan {
    return {
      start: '2026-10-19',
      end: '2026-10-25',
      meals,
      batch_cooks: [],
      tubs: []
    };
  }

  function open(next: PlanTarget, close = () => {}) {
    target = next;
    const actions = {
      model,
      readonly: false,
      desktop: false,
      openMeal: () => {},
      openItem: () => {},
      openCookOnce: () => {},
      add: () => {},
      openDay: () => {},
      carryMeal: () => null,
      carryItem: () => null
    } as unknown as PlanActions;
    component = mount(PlanSheet, {
      target: document.body,
      props: { actions, target, onclose: close }
    });
    flushSync();
    return page.getByRole('dialog');
  }

  beforeEach(() => {
    undoHistory.clear();
    toasts.dismiss();
    model = new PlanModel();
    model.today = '2026-10-19';
    model.anchor = '2026-10-19';
    model.slots = SLOTS;
    model.people = [
      { member_id: 1, name: 'Tess', colour: null, portion_quarters: 4 },
      { member_id: 2, name: 'Wren', colour: null, portion_quarters: 4 }
    ];
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  describe('Serves - N +', () => {
    let item: PlanItem;
    let meal: PlanMeal;

    beforeEach(() => {
      // A meal planned before the update: no number set, so the recipe's own Serves (4) shows.
      item = recipeItem(11, 'Sambar');
      meal = mealOf(1, '2026-10-20', 4, [item]);
      model.plan = plan([meal]);
      requests = fakeApi({
        'PATCH /plan/items/11': () => [200, written('Set Sambar for 6')],
        'GET /plan': [200, plan([meal])]
      });
    });

    it('starts from the recipe’s Serves on a meal planned before the update', async () => {
      const dialog = open({ kind: 'meal', meal });
      await expect.element(dialog.getByRole('group', { name: 'Serves' })).toBeVisible();
      expect(dialog.getByTestId('serves-11').element().textContent).toBe('4');
    });

    it('sends one change a moment after the last press, with the new number', async () => {
      const dialog = open({ kind: 'meal', meal });
      await dialog.getByRole('button', { name: 'One more' }).click();
      await dialog.getByRole('button', { name: 'One more' }).click();
      expect(dialog.getByTestId('serves-11').element().textContent).toBe('6');
      await expect
        .poll(() => requests.filter((r) => r.method === 'PATCH').map((r) => r.body))
        .toEqual([{ servings: 6 }]);
      expect(requests.filter((r) => r.method === 'PATCH')[0]?.path).toBe('/plan/items/11');
      expect(requests.find((r) => r.method === 'PATCH')?.headers['idempotency-key']).toBeTruthy();
    });

    it('stops at 1', async () => {
      item.eating = 1;
      const dialog = open({ kind: 'meal', meal });
      await expect.element(dialog.getByRole('button', { name: 'One fewer' })).toBeDisabled();
    });

    it('sends what is waiting when the menu closes', async () => {
      const dialog = open({ kind: 'meal', meal });
      await dialog.getByRole('button', { name: 'One fewer' }).click();
      unmount(component!);
      component = null;
      await expect
        .poll(() => requests.filter((r) => r.method === 'PATCH').map((r) => r.body))
        .toEqual([{ servings: 3 }]);
    });

    it('names each recipe when a meal has several', async () => {
      const second = recipeItem(12, 'Rasam', { servings: 2, eating: 2 });
      const both = mealOf(1, '2026-10-20', 4, [item, second]);
      model.plan = plan([both]);
      const dialog = open({ kind: 'meal', meal: both });
      await expect.element(dialog.getByRole('group', { name: 'Sambar serves' })).toBeVisible();
      await expect.element(dialog.getByRole('group', { name: 'Rasam serves' })).toBeVisible();
    });

    it('is not offered on a recipe of the meal that is cooked already (F157)', async () => {
      const done = recipeItem(12, 'Rasam', { servings: 2, eating: 2, cooked: true });
      const part = mealOf(1, '2026-10-20', 4, [item, done]);
      model.plan = plan([part]);
      const dialog = open({ kind: 'meal', meal: part });
      // The one left to cook names its recipe (F166): "Serves · Sambar".
      await expect.element(dialog.getByRole('group', { name: 'Serves · Sambar' })).toBeVisible();
      expect(dialog.getByRole('group', { name: 'Serves · Rasam' }).elements()).toHaveLength(0);
      expect(dialog.getByRole('group', { name: 'Rasam serves' }).elements()).toHaveLength(0);
    });

    it('is not offered on a note, or on a meal that was already dealt with', async () => {
      const noted = mealOf(2, '2026-10-21', 4, [noteItem(21, 'Eating out')]);
      model.plan = plan([noted]);
      const dialog = open({ kind: 'meal', meal: noted });
      await expect.element(dialog.getByRole('heading', { name: 'Eating out' })).toBeVisible();
      expect(dialog.getByRole('group', { name: 'Serves' }).elements()).toHaveLength(0);
      // A note has no leftovers; it can still move, be copied and be removed.
      expect(dialog.getByRole('button', { name: 'Leftovers on…' }).elements()).toHaveLength(0);
      await expect.element(dialog.getByRole('button', { name: 'Copy to…' })).toBeVisible();
      await expect.element(dialog.getByRole('button', { name: 'Remove' })).toBeVisible();
    });
  });

  describe('who’s eating', () => {
    let meal: PlanMeal;
    beforeEach(() => {
      meal = mealOf(1, '2026-10-20', 4, [recipeItem(11, 'Sambar')]);
      model.plan = plan([meal]);
      requests = fakeApi({
        'PUT /plan/meals/1/eaters': () => [200, written('Changed who is eating Sambar')],
        'GET /plan': [200, plan([meal])]
      });
    });

    it('starts with Everyone, and ticking a person sends just them', async () => {
      const dialog = open({ kind: 'meal', meal });
      const everyone = dialog.getByRole('button', { name: 'Everyone' });
      await expect.element(everyone).toHaveAttribute('aria-pressed', 'true');
      await dialog.getByRole('button', { name: 'Wren' }).click();
      await expect.element(everyone).toHaveAttribute('aria-pressed', 'false');
      await expect
        .poll(() => requests.filter((r) => r.method === 'PUT').map((r) => r.body))
        .toEqual([{ member_ids: [2] }]);
    });

    it('ticking everyone one by one is the same as Everyone', async () => {
      meal.eater_member_ids = [2];
      const dialog = open({ kind: 'meal', meal });
      await dialog.getByRole('button', { name: 'Tess' }).click();
      await expect
        .poll(() => requests.filter((r) => r.method === 'PUT').map((r) => r.body))
        .toEqual([{ member_ids: [] }]);
    });

    it('a removed person ticked on a past meal stays ticked, and is named, not "Everyone"', async () => {
      meal.eater_member_ids = [99];
      model.plan = { ...plan([meal]), removed_people: [{ member_id: 99, name: 'Lorna' }] };
      const dialog = open({ kind: 'meal', meal });
      await expect.element(dialog.getByText('Lorna (removed)')).toBeVisible();
      await dialog.getByRole('button', { name: 'Tess' }).click();
      await expect
        .poll(() => requests.filter((r) => r.method === 'PUT').map((r) => r.body))
        .toEqual([{ member_ids: [1, 99] }]);
    });

    it('a meal ticked only for a removed person does not show Everyone pressed', async () => {
      meal.eater_member_ids = [99];
      model.plan = { ...plan([meal]), removed_people: [{ member_id: 99, name: 'Lorna' }] };
      const dialog = open({ kind: 'meal', meal });
      await expect.element(dialog.getByText('Lorna (removed)')).toBeVisible();
      await expect
        .element(dialog.getByRole('button', { name: 'Everyone' }))
        .toHaveAttribute('aria-pressed', 'false');
    });

    it('is not asked when only one person signs in', async () => {
      model.people = [{ member_id: 1, name: 'Tess', colour: null, portion_quarters: 4 }];
      const dialog = open({ kind: 'meal', meal });
      await expect.element(dialog.getByRole('heading', { name: 'Sambar' })).toBeVisible();
      expect(dialog.getByRole('group', { name: 'Who’s eating?' }).elements()).toHaveLength(0);
    });
  });

  describe('Leftovers on…', () => {
    let meal: PlanMeal;
    let batch: Portions;
    let reply: () => [number, unknown];

    beforeEach(() => {
      batch = { ...PORTIONS };
      meal = mealOf(1, '2026-10-19', 4, [recipeItem(11, 'Veg biryani')]);
      model.plan = plan([meal]);
      reply = () => [200, written('Planned leftovers of Veg biryani')];
      requests = fakeApi({
        'GET /plan/items/11/portions': () => [200, batch],
        'GET /plan': [200, plan([meal])],
        'POST /plan/items/11/leftovers': () => reply()
      });
    });

    async function openLeftovers() {
      const dialog = open({ kind: 'meal', meal });
      await dialog.getByRole('button', { name: 'Leftovers on…' }).click();
      await expect.element(dialog.getByText('Leftovers of Veg biryani')).toBeVisible();
      return dialog;
    }

    const sent = () => requests.filter((r) => r.method === 'POST').map((r) => r.body);

    it('lists meals after the cook up to the use-by, and says the portions', async () => {
      const dialog = await openLeftovers();
      await expect
        .element(dialog.getByText('Cooked Mon 19 · dinner · keeps in the fridge until Thu 22'))
        .toBeVisible();
      await expect
        .element(dialog.getByText('Makes 4 · 1 eaten Mon · 2 tubs planned · 1 left'))
        .toBeVisible();
      const boxes = dialog.getByRole('checkbox').elements();
      // Tue, Wed, Thu: lunch and dinner each (nothing on the cook day: dinner is the last meal).
      expect(boxes).toHaveLength(6);
      expect(dialog.getByRole('checkbox', { name: /Fri/ }).elements()).toHaveLength(0);
      expect(dialog.getByRole('checkbox', { name: /Mon/ }).elements()).toHaveLength(0);
      await expect.element(dialog.getByRole('img', { name: /4 portions/ })).toBeVisible();
    });

    it('plans several meals at once when the portions reach', async () => {
      batch = {
        ...PORTIONS,
        left: 2,
        in_meals: 1,
        spare_use_by: ['2026-10-22', '2026-10-22']
      };
      const dialog = await openLeftovers();
      await dialog.getByRole('checkbox', { name: /Tue 20 · Lunch/ }).click();
      await dialog.getByRole('checkbox', { name: /Wed 21 · Dinner/ }).click();
      await expect
        .element(dialog.getByText('Makes 4 · 1 eaten Mon · 1 tub planned · 2 picked, 0 left'))
        .toBeVisible();
      expect(dialog.getByRole('alert').elements()).toHaveLength(0);
      await dialog.getByRole('button', { name: 'Plan 2 tubs' }).click();
      await expect.poll(sent).toEqual([
        {
          meals: [
            { date: '2026-10-20', slot_id: 2 },
            { date: '2026-10-21', slot_id: 4 }
          ],
          if_none_left: 'ask'
        }
      ]);
    });

    it('with none left says so, and asks for Cook more or Add anyway before planning', async () => {
      batch = { ...PORTIONS, left: 0, in_meals: 3, spare_use_by: [] };
      const dialog = await openLeftovers();
      await dialog.getByRole('checkbox', { name: /Wed 21 · Lunch/ }).click();
      const alert = dialog.getByRole('alert');
      await expect.element(alert).toHaveTextContent('No portions left for Wed 21 lunch.');
      await expect.element(dialog.getByRole('button', { name: /Cook more/ })).toBeVisible();
      await expect.element(dialog.getByRole('button', { name: /Add anyway/ })).toBeVisible();
      await expect.element(dialog.getByText('Makes 5 · list updates')).toBeVisible();
      await expect.element(dialog.getByText('Plans it; the batch stays at 4')).toBeVisible();
      await expect.element(dialog.getByRole('button', { name: 'Plan 1 tub' })).toBeDisabled();
      expect(sent()).toEqual([]);
    });

    it('a spare tub that goes off before a meal does not reach it', async () => {
      // Two spare tubs: one off on Tue 20, one keeps to Thu 22.
      batch = { ...PORTIONS, left: 2, in_meals: 1, spare_use_by: ['2026-10-20', '2026-10-22'] };
      const dialog = await openLeftovers();
      await dialog.getByRole('checkbox', { name: /Wed 21 · Lunch/ }).click();
      expect(dialog.getByRole('alert').elements()).toHaveLength(0); // the tub that keeps reaches it
      await dialog.getByRole('checkbox', { name: /Thu 22 · Lunch/ }).click();
      await expect
        .element(dialog.getByRole('alert'))
        .toHaveTextContent('No portions left for Thu 22 lunch.');
      await expect.element(dialog.getByText('2 picked, only 1 left')).toBeVisible();
    });

    it('Add anyway counts only the tubs in the button, as the mockup does', async () => {
      batch = { ...PORTIONS, left: 1, spare_use_by: ['2026-10-22'] };
      const dialog = await openLeftovers();
      await dialog.getByRole('checkbox', { name: /Tue 20 · Lunch/ }).click();
      await dialog.getByRole('checkbox', { name: /Tue 20 · Dinner/ }).click();
      await dialog.getByRole('button', { name: /Add anyway/ }).click();
      await expect.element(dialog.getByRole('button', { name: 'Plan 1 tub' })).toBeEnabled();
    });

    it('Cook more plans it with a bigger batch', async () => {
      batch = { ...PORTIONS, left: 0, in_meals: 3, spare_use_by: [] };
      const dialog = await openLeftovers();
      await dialog.getByRole('checkbox', { name: /Wed 21 · Lunch/ }).click();
      await dialog.getByRole('button', { name: /Cook more/ }).click();
      await dialog.getByRole('button', { name: 'Plan 1 tub' }).click();
      await expect
        .poll(sent)
        .toEqual([{ meals: [{ date: '2026-10-21', slot_id: 2 }], if_none_left: 'cook_more' }]);
    });

    it('Add anyway plans it and leaves the batch', async () => {
      batch = { ...PORTIONS, left: 0, in_meals: 3, spare_use_by: [] };
      const dialog = await openLeftovers();
      await dialog.getByRole('checkbox', { name: /Wed 21 · Lunch/ }).click();
      await dialog.getByRole('button', { name: /Add anyway/ }).click();
      await dialog.getByRole('button', { name: 'Plan 1 meal' }).click();
      await expect
        .poll(sent)
        .toEqual([{ meals: [{ date: '2026-10-21', slot_id: 2 }], if_none_left: 'add_anyway' }]);
    });

    it('un-ticking the meal that was short takes the question away', async () => {
      batch = { ...PORTIONS, left: 0, in_meals: 3, spare_use_by: [] };
      const dialog = await openLeftovers();
      const box = dialog.getByRole('checkbox', { name: /Wed 21 · Lunch/ });
      await box.click();
      await dialog.getByRole('button', { name: /Cook more/ }).click();
      await box.click();
      expect(dialog.getByRole('alert').elements()).toHaveLength(0);
      await box.click();
      // Asked again, not remembered.
      await expect.element(dialog.getByRole('button', { name: 'Plan 1 tub' })).toBeDisabled();
    });

    it('when someone else took the last portion, it asks again with the new numbers', async () => {
      const dialog = await openLeftovers();
      await dialog.getByRole('checkbox', { name: /Tue 20 · Lunch/ }).click();
      reply = () => [
        409,
        { detail: 'No portions left.', code: 'no_portions_left', left: 0, wanted: 1 }
      ];
      batch = { ...PORTIONS, left: 0, in_meals: 3, spare_use_by: [] };
      await dialog.getByRole('button', { name: 'Plan 1 tub' }).click();
      await expect
        .element(dialog.getByRole('alert'))
        .toHaveTextContent('No portions left for Tue 20 lunch.');
      // No "Couldn’t save" toast: the sheet itself asks.
      expect(toasts.current?.tone).not.toBe('problem');
    });

    it('a recipe with no batch yet has no count, and plans a tub for each meal', async () => {
      batch = {
        recipe_name: 'Veg biryani',
        has_batch: false,
        batch_id: null,
        portions: null,
        cook_day: null,
        tubs: null,
        in_meals: null,
        left: null,
        use_by: '2026-10-22',
        spare_use_by: []
      };
      const dialog = await openLeftovers();
      expect(dialog.getByRole('img').elements()).toHaveLength(0);
      await dialog.getByRole('checkbox', { name: /Tue 20 · Lunch/ }).click();
      await dialog.getByRole('checkbox', { name: /Tue 20 · Dinner/ }).click();
      expect(dialog.getByRole('alert').elements()).toHaveLength(0);
      await dialog.getByRole('button', { name: 'Plan 2 tubs' }).click();
      await expect.poll(sent).toHaveLength(1);
    });

    it('a meal of several things keeps the single-day picker', async () => {
      const two = mealOf(1, '2026-10-19', 4, [
        recipeItem(11, 'Veg biryani'),
        recipeItem(12, 'Raita')
      ]);
      model.plan = plan([two]);
      const dialog = open({ kind: 'meal', meal: two });
      await dialog.getByRole('button', { name: 'Leftovers on…' }).click();
      await expect
        .element(dialog.getByRole('button', { name: 'Plan leftovers here' }))
        .toBeVisible();
      expect(dialog.getByRole('checkbox').elements()).toHaveLength(0);
    });
  });
});
