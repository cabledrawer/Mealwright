// The Plan screen's data (docs/dev/api-0.2.md 6.3a): the week or month on show, the meals
// that are on, and every change to them. Each change shows at once (optimistic), goes
// through save() with its change ID, and is offered for Undo; then the plan is fetched
// again so the server's version replaces the guess. Online only, like the Pantry.

import { ApiError } from './api';
import { serverUndo } from './client/changes';
import { getHousehold } from './client/household';
import {
  getMealSlots,
  getPlan,
  movePlanItem,
  movePlanMeal,
  planItem,
  removePlanItem,
  removePlanMeal,
  switchMealSlot,
  type DropMode,
  type MealSlot,
  type Plan,
  type PlanMeal,
  type PlanWrite
} from './client/plan';
import { kitchen } from './freshness.svelte';
import {
  addDays,
  monthGrid,
  monthStart,
  nextMonth,
  prevMonth,
  weekDays,
  weekStart
} from './planDates';
import { withItemDropped, withMealDropped, withoutItem, withoutMeal } from './planEdits';
import { itemName, mealName } from './planMeals';
import { save } from './save';

export type PlanView = 'week' | 'month';

/** What is being moved: a whole meal, or one thing in a meal. */
export type Mover = { meal: number } | { item: number };

/** What is being planned: a recipe or a plain ingredient. */
export type Planned =
  { recipe: { id: number; name: string } } | { ingredient: { id: number; name: string } };

export class PlanModel {
  view = $state<PlanView>('week');
  /** Any day in the week or month on show. */
  anchor = $state('');
  today = $state('');
  startsOn = $state(1);
  slots = $state<MealSlot[]>([]);
  plan = $state<Plan | null>(null);
  loaded = $state(false);
  problem = $state<string | null>(null);

  #asked = 0;

  /** Every day on show: seven for a week, whole weeks for a month. */
  days = $derived.by(() => {
    if (!this.anchor) return [] as string[];
    return this.view === 'week'
      ? weekDays(weekStart(this.anchor, this.startsOn))
      : monthGrid(this.anchor, this.startsOn);
  });

  /** The meals that are on, in order. */
  slotsOn = $derived(
    this.slots.filter((s) => s.enabled).sort((a, b) => a.position - b.position || a.id - b.id)
  );

  async load(): Promise<void> {
    const asked = ++this.#asked;
    try {
      if (!this.today) {
        const household = await getHousehold();
        if (asked !== this.#asked) return;
        this.today = household.today;
        this.startsOn = household.week_starts_on || 1;
        this.anchor ||= household.today;
      }
      const first = this.days[0];
      const last = this.days.at(-1);
      if (!first || !last) return;
      const [slots, plan] = await Promise.all([getMealSlots(), getPlan(first, last)]);
      if (asked !== this.#asked) return; // something newer is on its way
      this.slots = slots;
      this.plan = plan;
      this.loaded = true;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem =
        error instanceof ApiError && error.status === 0
          ? error.detail
          : 'Couldn’t load the plan. Try again.';
    }
  }

  // --- Moving about -------------------------------------------------------------------

  setView(view: PlanView): void {
    if (view === this.view) return;
    this.view = view;
    void this.load();
  }

  /** One week or one month back (-1) or forward (1). */
  step(direction: -1 | 1): void {
    if (this.view === 'week') this.anchor = addDays(this.anchor, 7 * direction);
    else this.anchor = direction === 1 ? nextMonth(this.anchor) : prevMonth(this.anchor);
    void this.load();
  }

  goToday(): void {
    this.anchor = this.today;
    void this.load();
  }

  /** Whether the week or month on show holds today. */
  get onToday(): boolean {
    return (
      this.days.includes(this.today) &&
      (this.view === 'week' || monthStart(this.anchor) === monthStart(this.today))
    );
  }

  // --- Reading ------------------------------------------------------------------------

  mealAt(day: string, slotId: number): PlanMeal | null {
    return this.plan?.meals.find((m) => m.date === day && m.slot_id === slotId) ?? null;
  }

  slotName(slotId: number): string {
    return this.slots.find((s) => s.id === slotId)?.name ?? 'Meal';
  }

  /** The meal a recipe dropped on a day (Month view) goes to: the last meal that is on and
   * still empty, else the last one on. Proposed, for cabledrawer. */
  slotForDay(day: string): number | null {
    const on = this.slotsOn;
    const empty = on.filter((s) => !this.mealAt(day, s.id));
    return (empty.at(-1) ?? on.at(-1))?.id ?? null;
  }

  // --- Changes ------------------------------------------------------------------------

  #send(options: {
    label: string;
    edit?: (plan: Plan) => Plan;
    send: (key: string) => Promise<PlanWrite>;
  }) {
    let before: Plan | null = null;
    let undoer: (() => Promise<string | void>) | null = null;
    return save<PlanWrite>({
      apply: () => {
        before = $state.snapshot(this.plan) as Plan | null;
        if (this.plan && options.edit) this.plan = options.edit(this.plan);
      },
      rollback: () => {
        if (before) this.plan = before;
      },
      send: (key) => options.send(key),
      // The screen fetches the plan again when the kitchen changes.
      saved: () => kitchen.changed(),
      undo: {
        label: options.label,
        labelFrom: (value) => value.change?.summary,
        skip: (value) => value.change === null,
        run: (value) => {
          const change = value.change;
          if (!change?.can_undo) return false;
          undoer ??= serverUndo(change.id);
          return undoer();
        }
      }
    });
  }

  /** Plan a recipe or an ingredient on a day and meal. */
  add(what: Planned, day: string, slotId: number) {
    const name = 'recipe' in what ? what.recipe.name : what.ingredient.name;
    const body =
      'recipe' in what ? { recipe_id: what.recipe.id } : { ingredient_id: what.ingredient.id };
    return this.#send({
      label: `Planned ${name} for ${this.slotName(slotId)}`,
      send: (key) => planItem({ date: day, slot_id: slotId, ...body }, key)
    });
  }

  removeItem(itemId: number) {
    const item = this.plan?.meals.flatMap((m) => m.items).find((i) => i.id === itemId);
    return this.#send({
      label: `Removed ${item ? itemName(item, this.plan) : 'it'}`,
      edit: (plan) => withoutItem(plan, itemId),
      send: (key) => removePlanItem(itemId, key)
    });
  }

  removeMeal(mealId: number) {
    const meal = this.plan?.meals.find((m) => m.id === mealId);
    return this.#send({
      label: `Removed ${meal ? mealName(meal, this.plan) : 'it'}`,
      edit: (plan) => withoutMeal(plan, mealId),
      send: (key) => removePlanMeal(mealId, key)
    });
  }

  /** Move, copy or plan leftovers of a meal or one thing in it, to another day and meal. */
  drop(what: Mover, day: string, slotId: number, mode: DropMode) {
    const verb = { move: 'Moved', copy: 'Copied', leftovers: 'Leftovers of' }[mode];
    const meal =
      'meal' in what
        ? this.plan?.meals.find((m) => m.id === what.meal)
        : this.plan?.meals.find((m) => m.items.some((i) => i.id === what.item));
    const name = !meal
      ? 'it'
      : 'meal' in what
        ? mealName(meal, this.plan)
        : itemName(
            meal.items.find((i) => i.id === what.item)!,
            this.plan
          );
    const to = { date: day, slot_id: slotId, mode };
    return this.#send({
      label: `${verb} ${name} ${mode === 'leftovers' ? 'on' : 'to'} ${this.slotName(slotId)}`,
      edit: (plan) =>
        'meal' in what
          ? withMealDropped(plan, what.meal, day, slotId, mode)
          : withItemDropped(plan, what.item, day, slotId, mode),
      send: (key) =>
        'meal' in what ? movePlanMeal(what.meal, to, key) : movePlanItem(what.item, to, key)
    });
  }

  /** The "Meals" switches: show or hide Breakfast, Lunch… for the household. */
  switchSlot(slot: MealSlot, enabled: boolean) {
    const before = this.slots;
    return save<PlanWrite>({
      apply: () => {
        this.slots = this.slots.map((s) => (s.id === slot.id ? { ...s, enabled } : s));
      },
      rollback: () => {
        this.slots = before;
      },
      send: (key) => switchMealSlot(slot.id, enabled, key),
      saved: () => kitchen.changed(),
      undo: {
        label: `${enabled ? 'Showed' : 'Hid'} ${slot.name}`,
        labelFrom: (value) => value.change?.summary,
        skip: (value) => value.change === null,
        run: (value) => {
          const change = value.change;
          if (!change?.can_undo) return false;
          return serverUndo(change.id)();
        }
      }
    });
  }
}
