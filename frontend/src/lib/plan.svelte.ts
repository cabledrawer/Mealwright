// The Plan screen's data (docs/dev/api-0.2.md 6.3a): the week or month on show, the meals
// that are on, and every change to them. Each change shows at once (optimistic), goes
// through save() with its change ID, and is offered for Undo; then the plan is fetched
// again so the server's version replaces the guess. Online only, like the Pantry.

import { cantReachWords, cantReach } from './api';
import { serverUndo } from './client/changes';
import { getHousehold } from './client/household';
import {
  editTub,
  fillFromFreezer,
  getMealSlots,
  getPeople,
  getPlan,
  getTubsLeft,
  makeBatch,
  movePlanItem,
  movePlanMeal,
  placeTub,
  planItem,
  removePlanItem,
  removePlanMeal,
  switchMealSlot,
  tubToFreezer,
  type BatchBody,
  type DropMode,
  type MealSlot,
  type Person,
  type Plan,
  type PlanMeal,
  type PlanWrite,
  type TubLeft
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
  /** Tubs in no meal, soonest use-by first (the tray's "Tubs left"). */
  tubsLeft = $state<TubLeft[]>([]);
  /** Who can be eating (the household's logins until member profiles in 0.8). */
  people = $state<Person[]>([]);
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
      void this.#loadTubs();
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem = cantReach(error) ? cantReachWords() : 'Couldn’t load the plan. Try again.';
    }
  }

  /** Tubs left and the people, beside the plan. A failure here leaves what is on screen. */
  async #loadTubs(): Promise<void> {
    try {
      const [left, people] = await Promise.all([
        getTubsLeft(),
        this.people.length ? Promise.resolve(this.people) : getPeople()
      ]);
      this.tubsLeft = left.tubs;
      this.people = people;
    } catch {
      // The plan itself is fine; the tray just keeps what it had.
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
    if (!this.anchor) return; // the household's today isn't here yet: nothing to step from
    if (this.view === 'week') this.anchor = addDays(this.anchor, 7 * direction);
    else this.anchor = direction === 1 ? nextMonth(this.anchor) : prevMonth(this.anchor);
    void this.load();
  }

  goToday(): void {
    if (!this.today) return;
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
    const name = item ? itemName(item, this.plan) : 'it';
    return this.#send({
      // A tub is not thrown away: it goes back to "tubs left".
      label: item?.kind === 'tub' ? `Put ${name} back in tubs left` : `Removed ${name}`,
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
      // Leftovers make a real tub on the server, so the screen waits for it.
      edit:
        mode === 'leftovers'
          ? undefined
          : (plan) =>
              'meal' in what
                ? withMealDropped(plan, what.meal, day, slotId, mode)
                : withItemDropped(plan, what.item, day, slotId, mode),
      send: (key) =>
        'meal' in what ? movePlanMeal(what.meal, to, key) : movePlanItem(what.item, to, key)
    });
  }

  // --- Cook once, eat for… and tubs --------------------------------------------------------

  /** Make a batch cook from a planned recipe, with its tubs placed as the preview showed. */
  cookOnce(itemId: number, recipeName: string, body: BatchBody) {
    const word = body.tub_count === 1 ? 'tub' : 'tubs';
    return this.#send({
      label: `Cooked ${recipeName} once for ${body.tub_count} ${word}`,
      send: (key) => makeBatch(itemId, body, key)
    });
  }

  /** Put a tub in a meal (from tubs left, or moving one that is in a meal already). */
  placeTub(tubId: number, name: string, day: string, slotId: number) {
    return this.#send({
      label: `Put ${name} in ${this.slotName(slotId)}`,
      send: (key) => placeTub(tubId, { date: day, slot_id: slotId }, key)
    });
  }

  /** "Whose tub?": a person's login id, or null for nobody in particular. */
  setWhose(tubId: number, name: string, loginId: number | null) {
    const who = this.people.find((p) => p.login_id === loginId)?.name;
    return this.#send({
      label: who ? `${name} is ${who}’s` : `${name} is nobody’s in particular`,
      send: (key) => editTub(tubId, { member_login_id: loginId }, key)
    });
  }

  setUseBy(tubId: number, name: string, useBy: string) {
    return this.#send({
      label: `Changed the use-by of ${name}`,
      send: (key) => editTub(tubId, { use_by: useBy }, key)
    });
  }

  toFreezer(tubId: number, name: string) {
    return this.#send({
      label: `${name} to the freezer`,
      send: (key) => tubToFreezer(tubId, key)
    });
  }

  /** Month's "Fill from freezer first": empty days in the range get a tub from the freezer. */
  fillFromFreezer(from: string, to: string) {
    return this.#send({
      label: 'Filled empty days from the freezer',
      send: (key) => fillFromFreezer(from, to, key)
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
