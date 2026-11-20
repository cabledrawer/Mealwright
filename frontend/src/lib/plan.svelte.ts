// The Plan screen's data (docs/dev/api-endpoints.md 6.3a): the week or month on show, the meals
// that are on, and every change to them. Each change shows at once (optimistic), goes
// through save() with its change ID, and is offered for Undo; then the plan is fetched
// again so the server's version replaces the guess. Online only, like the Pantry.

import { cantReachWords, cantReach, type ApiError } from './api';
import { changeSession, makeSession, removeSession, type SessionBody } from './client/batch';
import { serverUndo } from './client/changes';
import { getHousehold } from './client/household';
import { cookedIt, type Leftovers } from './client/today';
import { sendTwice } from './sendTwice';
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
  planLeftovers,
  removePlanItem,
  removePlanMeal,
  setPlanEaters,
  setPlanMethod,
  setPlanOptional,
  setPlanServings,
  setPlanStart,
  switchMealSlot,
  tubToFreezer,
  type BatchBody,
  type DropMode,
  type MealSlot,
  type Person,
  type Plan,
  type PlanItem,
  type PlanSession,
  type PlanMeal,
  type PlanWrite,
  type Spot,
  type StartAt,
  type TubLeft,
  type WhenNoneLeft
} from './client/plan';
import { forgetBatchMode } from './batchModeStore';
import { kitchen } from './freshness.svelte';
import { fetchCode } from './lazyCode.svelte';
import { loaders } from './lazyModules';
import {
  addDays,
  dayShort,
  monthGrid,
  monthStart,
  msUntilNextDay,
  nextMonth,
  prevMonth,
  weekDays,
  weekStart
} from './planDates';
import {
  withEaters,
  withItemDropped,
  withMealDropped,
  withoutItem,
  withoutMeal,
  withServings
} from './planEdits';
import { cookBatchOfItem, itemName, leftName, mealName } from './planMeals';
import { optionalAsk } from './optionalAsk.svelte';
import type { StepWait } from './timeWords';
import { save, type Outcome } from './save';

export type PlanView = 'week' | 'month';

/** What is being moved: a whole meal, or one thing in a meal. */
export type Mover = { meal: number } | { item: number };

/** What is being planned: a recipe or a plain ingredient. */
export type Planned =
  | {
      /** `optional_count`: how many of its lines are Optional, when it is known (0: no question). */
      recipe: {
        id: number;
        name: string;
        optional_count?: number;
        method_count?: number;
        /** All the recipe's waits added up, when known: none that is long means nothing to ask. */
        wait?: StepWait | null;
      };
    }
  | { ingredient: { id: number; name: string } };

/** How many days past a screen's last day the plan is read, to find the starts that fall on it:
 * the longest wait (ten days) and a day more. Same as the server's `MOST_DAYS_AHEAD`. */
export const START_DAYS_AHEAD = 11;

export class PlanModel {
  view = $state<PlanView>('week');
  /** Any day in the week or month on show. */
  anchor = $state('');
  today = $state('');
  /** The household's time zone, for the midnight timer. */
  zone = $state<string | null>(null);
  startsOn = $state(1);
  /** Days a tub keeps in the fridge (its default use-by), from the household. */
  tubFridgeDays = $state(0);
  /** Months a tub keeps in the freezer, from the household. */
  tubFreezerMonths = $state(0);
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

  /** The Batch cook sessions cooked on this day (their card sits in the day, above its meals). */
  sessionsOn(day: string): PlanSession[] {
    return (this.plan?.batch_sessions ?? []).filter((s) => s.cook_day === day);
  }

  /** The meals that are on, in order. */
  slotsOn = $derived(
    this.slots.filter((s) => s.enabled).sort((a, b) => a.position - b.position || a.id - b.id)
  );

  /**
   * Read everything again, the household's today too (RF5, H3): coming back to the tab, after
   * midnight, after another person's change. A Plan that was showing today's week moves on with
   * the day; one someone has paged to stays where it is.
   */
  async refresh(): Promise<void> {
    return this.load(true);
  }

  #soon: ReturnType<typeof setTimeout> | undefined;

  /**
   * Read again shortly: another person changed the plan (the live `plan` event). A burst of
   * events makes one read, and none while `busy()` says something is being carried (a drag), so
   * the card under the finger doesn't move; it tries again a second later.
   */
  refreshSoon(busy: () => boolean): void {
    clearTimeout(this.#soon);
    const run = () => {
      if (busy()) {
        this.#soon = setTimeout(run, 1000);
        return;
      }
      void this.refresh();
    };
    this.#soon = setTimeout(run, 400);
  }

  /** The Plan was left: no read waits to happen (RF5 review r2). */
  cancelSoon(): void {
    clearTimeout(this.#soon);
    this.#soon = undefined;
  }

  /**
   * Refresh at each midnight in the household's time zone. Returns a function that stops it.
   * (A laptop that was asleep through midnight is caught by coming back to the tab.)
   */
  watchDay(): () => void {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      timer = setTimeout(
        () => {
          void this.refresh();
          arm();
        },
        msUntilNextDay(Date.now(), this.zone)
      );
    };
    arm();
    return () => clearTimeout(timer);
  }

  async load(again = false): Promise<void> {
    const asked = ++this.#asked;
    try {
      if (!this.today || again) {
        const household = await getHousehold();
        if (asked !== this.#asked) return;
        if (!this.anchor || this.anchor === this.today) this.anchor = household.today;
        this.zone = household.time_zone;
        this.today = household.today;
        this.startsOn = household.week_starts_on || 1;
        this.tubFridgeDays = household.tub_fridge_days ?? 0;
        this.tubFreezerMonths = household.tub_freezer_months ?? 0;
        this.anchor ||= household.today;
      }
      const first = this.days[0];
      const last = this.days.at(-1);
      if (!first || !last) return;
      // Past the last day as far as a start can reach (the server's `start_ahead.MOST_DAYS_AHEAD`,
      // the same number Today reads): a recipe started on the last day for a meal up to ten
      // days later shows too.
      const [slots, plan] = await Promise.all([
        getMealSlots(),
        getPlan(first, addDays(last, START_DAYS_AHEAD))
      ]);
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

  /** The recipe page's Plan it: today and the 13 days after, read in one go (the next 14). */
  async loadAhead(): Promise<void> {
    await this.load();
    if (!this.loaded || !this.today) return;
    const asked = ++this.#asked;
    try {
      const plan = await getPlan(this.today, addDays(this.today, 13));
      if (asked === this.#asked) this.plan = plan;
    } catch (error) {
      if (asked === this.#asked) {
        this.loaded = false;
        this.problem = cantReach(error) ? cantReachWords() : 'Couldn’t load the plan. Try again.';
      }
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
    /** Also undone when this is (what "Cooked it" took from the pantry). */
    alsoUndo?: () => Promise<string | void>;
    /** Undone first (a tub put on a meal after "Cooked it", F65). */
    firstUndo?: () => Promise<string | void>;
    /** Sent again with the same ID, and no toast of its own: the caller says it once. */
    changeId?: string;
    quiet?: boolean;
    /** The toast button's words when they are not "Undo". */
    undoButton?: string;
    /** Deal with a refusal yourself (return true): no problem toast is shown. */
    refused?: (error: ApiError) => boolean;
  }) {
    let before: Plan | null = null;
    let undoer: (() => Promise<string | void>) | null = null;
    return save<PlanWrite>(
      {
        apply: () => {
          before = $state.snapshot(this.plan) as Plan | null;
          if (this.plan && options.edit) this.plan = options.edit(this.plan);
        },
        rollback: () => {
          if (before) this.plan = before;
        },
        send: (key) => options.send(key),
        refused: options.refused,
        // The screen fetches the plan again when the kitchen changes.
        saved: () => kitchen.changed(),
        quiet: options.quiet,
        undo: {
          label: options.label,
          buttonLabel: options.undoButton,
          labelFrom: (value) => value.change?.summary,
          skip: (value) => value.change === null,
          run: (value) => {
            const change = value.change;
            if (!change?.can_undo) return false;
            undoer ??= serverUndo(change.id);
            if (!options.alsoUndo && !options.firstUndo) return undoer();
            return (async () => {
              const placed = await options.firstUndo?.();
              const own = (await undoer!()) ?? placed;
              const more = await options.alsoUndo?.();
              return more ?? own;
            })();
          }
        }
      },
      options.changeId
    );
  }

  /**
   * Plan a recipe or an ingredient on a day and meal. A recipe with Optional ingredients first
   * asks which of them the meal will use (R3); cancelling the question plans nothing. Every
   * way of adding a recipe comes through here: dragging from the tray, picking in the Add sheet,
   * Plan it on the recipe page, Copy to… on a recipe in the tray's menu, and Cook once here.
   * All but Cook once ask when a long wait will be started (`askStart: false` skips it: Cook once
   * is cooking now, as Cook now is, so there is nothing to start ahead).
   */
  async add(
    what: Planned,
    day: string,
    slotId: number,
    options: { askStart?: boolean } = {}
  ): Promise<Outcome<PlanWrite>> {
    const name = 'recipe' in what ? what.recipe.name : what.ingredient.name;
    const body: {
      recipe_id?: number;
      ingredient_id?: number;
      optional_use?: number[];
      method_id?: number;
      start?: StartAt;
    } = 'recipe' in what ? { recipe_id: what.recipe.id } : { ingredient_id: what.ingredient.id };
    if ('recipe' in what) {
      const where = `${dayShort(day)} ${this.slotName(slotId).toLocaleLowerCase()}`;
      // A recipe with two ways of cooking it asks which first (M2), then which optional
      // ingredients of that way.
      let method: number | null | undefined;
      if (what.recipe.method_count !== 1) {
        const loaded = await fetchCode(loaders.methodAsk);
        if (!loaded) return { ok: false, error: null, cancelled: true };
        method = await loaded.methodAsk.ask(
          { id: what.recipe.id, methodCount: what.recipe.method_count },
          where
        );
      }
      if (method === null) return { ok: false, error: null, cancelled: true };
      if (method !== undefined) body.method_id = method;
      const use = await optionalAsk.ask(
        { id: what.recipe.id, optionalCount: what.recipe.optional_count },
        where,
        { method }
      );
      if (use === null) return { ok: false, error: null, cancelled: true };
      if (use !== undefined) body.optional_use = use;
      // A recipe with a long wait asks when it will be started (M3), for the way chosen. Known
      // not to have one (the server's rule: a wait of 4 hours or more), it is not even loaded.
      const wait = what.recipe.wait;
      let start: StartAt | null | undefined;
      if (
        options.askStart !== false &&
        (wait === undefined ||
          (what.recipe.method_count ?? 1) > 1 ||
          (wait?.max_minutes ?? 0) >= 240)
      ) {
        const loaded = await fetchCode(loaders.startAsk);
        if (!loaded) return { ok: false, error: null, cancelled: true };
        start = await loaded.startAsk.ask(
          what.recipe,
          { day, slotId, slotName: this.slotName(slotId) },
          { method, adding: true }
        );
      }
      if (start === null) return { ok: false, error: null, cancelled: true };
      if (start !== undefined) body.start = start;
    }
    return this.#send({
      label: `Planned ${name} for ${this.slotName(slotId)}`,
      send: (key) => planItem({ date: day, slot_id: slotId, ...body }, key)
    });
  }

  /** Change which way of cooking a planned recipe uses, from its meal (M2). */
  async changeMethod(item: PlanItem, day: string): Promise<void> {
    if (item.kind !== 'recipe' || !item.recipe) return;
    const meal = this.plan?.meals.find((m) => m.items.some((i) => i.id === item.id));
    const loaded = await fetchCode(loaders.methodAsk);
    if (!loaded) return; // nothing is changed
    const picked = await loaded.methodAsk.ask(
      { id: item.recipe.id },
      `${dayShort(day)} ${meal ? this.slotName(meal.slot_id).toLocaleLowerCase() : 'meal'}`,
      { current: item.method_id ?? null, button: 'Save' }
    );
    if (picked === null || picked === undefined || picked === item.method_id) return;
    await this.#send({
      label: `Changed how ${itemName(item, this.plan)} is cooked`,
      send: (key) => setPlanMethod(item.id, picked, key)
    });
  }

  /** Change when a planned recipe's long wait will be started, from its meal (M3). */
  async changeStart(item: PlanItem, day: string): Promise<void> {
    if (item.kind !== 'recipe' || !item.recipe || !item.ahead) return;
    const meal = this.plan?.meals.find((m) => m.items.some((i) => i.id === item.id));
    if (!meal) return;
    const current = item.ahead.start_day
      ? { day: item.ahead.start_day, time: item.ahead.start_time! }
      : null;
    const loaded = await fetchCode(loaders.startAsk);
    if (!loaded) return; // nothing is changed
    const picked = await loaded.startAsk.ask(
      { id: item.recipe.id, name: item.recipe.name },
      { day, slotId: meal.slot_id, slotName: this.slotName(meal.slot_id) },
      { method: item.method_id ?? null, current, button: 'Save' }
    );
    if (picked === null || picked === undefined) return;
    if (current && picked.day === current.day && picked.time === current.time) return;
    await this.#send({
      label: `Changed when to start ${itemName(item, this.plan)}`,
      send: (key) => setPlanStart(item.id, picked, key)
    });
  }

  /** "Done already": the long wait of a planned recipe is begun (M3). */
  async markStarted(item: PlanItem) {
    const loaded = await fetchCode(loaders.startNow); // loaded when first used (size limit)
    if (!loaded) return { ok: false, error: null, cancelled: true } as const; // nothing is marked
    return loaded.markStarted(item.id, itemName(item, this.plan));
  }

  /** Change which Optional ingredients a planned recipe will use, from its meal (R3). */
  async changeOptional(item: PlanItem, day: string): Promise<void> {
    if (item.kind !== 'recipe' || !item.recipe) return;
    const meal = this.plan?.meals.find((m) => m.items.some((i) => i.id === item.id));
    const skipped = item.optional_skipped ?? [];
    const use = await optionalAsk.ask(
      { id: item.recipe.id },
      `${dayShort(day)} ${meal ? this.slotName(meal.slot_id).toLocaleLowerCase() : 'meal'}`,
      { button: 'Save', skipped, servings: item.eating, method: item.method_id }
    );
    if (use === null || use === undefined) return;
    await this.#send({
      label: `Changed the optional ingredients of ${itemName(item, this.plan)}`,
      send: (key) => setPlanOptional(item.id, use, key)
    });
  }

  /** A note ("Eating out", "At Tess’s") on a day and meal. */
  addNote(text: string, day: string, slotId: number) {
    return this.#send({
      label: `Planned ${text} for ${this.slotName(slotId)}`,
      send: (key) => planItem({ date: day, slot_id: slotId, note: text }, key)
    });
  }

  /** Serves − N +: how many people a planned recipe is for; amounts and the list follow. */
  setServings(item: PlanItem, servings: number) {
    return this.#send({
      label: `Set ${itemName(item, this.plan)} for ${servings}`,
      edit: (plan) => withServings(plan, item.id, servings),
      send: (key) => setPlanServings(item.id, servings, key)
    });
  }

  /** Who is eating a meal, by sign-in (an empty list: everyone). */
  setEaters(meal: PlanMeal, memberIds: number[]) {
    return this.#send({
      label: `Changed who is eating ${mealName(meal, this.plan)}`,
      edit: (plan) => withEaters(plan, meal.id, memberIds),
      send: (key) => setPlanEaters(meal.id, memberIds, key)
    });
  }

  /**
   * "Leftovers on…" with several meals ticked at once. `whenNone` is what to do for the meals the
   * portions left don't reach. A refusal "no portions left" (someone else took the last one) is
   * left to the sheet, which asks again with the new numbers.
   */
  leftoversOn(item: PlanItem, spots: Spot[], whenNone: WhenNoneLeft) {
    return this.#send({
      label: `Planned leftovers of ${itemName(item, this.plan)}`,
      send: (key) => planLeftovers(item.id, spots, whenNone, key),
      refused: (error) => error.code === 'no_portions_left'
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

  /**
   * Set when a "Leftovers here" found no portion left (the drop zone, or the one-day picker): the
   * screen asks Cook more or Add anyway (cabledrawer 28 Oct). Cleared when answered or put away.
   */
  noPortions = $state<{ what: Mover; day: string; slotId: number; name: string } | null>(null);

  /** Move, copy or plan leftovers of a meal or one thing in it, to another day and meal. */
  drop(
    what: Mover,
    day: string,
    slotId: number,
    mode: DropMode,
    ifNoneLeft: Exclude<WhenNoneLeft, 'ask'> | 'ask' = 'ask'
  ): Promise<Outcome<PlanWrite>> {
    // When a long wait will be started is asked again for the new day: for a copy of a recipe
    // with a long wait, as every other way of adding it does (M3), and for each recipe moved
    // that had a start time (cabledrawer 10 Nov).
    what = this.#mover(what, mode);
    const asking = this.#startsToAsk(what, mode);
    if (asking.length === 0) return this.#drop(what, day, slotId, mode, ifNoneLeft);
    return (async () => {
      const loaded = await fetchCode(loaders.startAsk);
      if (!loaded) return { ok: false, error: null, cancelled: true } as const; // nothing is moved
      const starts: { item_id: number; day: string; time: string }[] = [];
      for (const item of asking) {
        const start = await loaded.startAsk.ask(
          { id: item.recipe!.id, name: item.recipe!.name },
          { day, slotId, slotName: this.slotName(slotId) },
          {
            method: item.method_id ?? null,
            adding: true,
            ...(mode === 'move' ? { button: 'Move' } : {}) // proposed, for cabledrawer
          }
        );
        if (start === null) return { ok: false, error: null, cancelled: true } as const;
        if (start) starts.push({ item_id: item.id, ...start });
      }
      return this.#drop(what, day, slotId, mode, ifNoneLeft, starts);
    })();
  }

  /** The cooking moves with its whole meal (cabledrawer 10 Nov; the server does the same). */
  #mover(what: Mover, mode: DropMode): Mover {
    if (mode !== 'move' || !('item' in what)) return what;
    const itemId = what.item;
    const from = this.plan?.meals.find((m) => m.items.some((i) => i.id === itemId));
    const item = from?.items.find((i) => i.id === itemId);
    return from && item && cookBatchOfItem(this.plan, from, item) ? { meal: from.id } : what;
  }

  /** The recipes a move or copy asks the start time of, in the meal's order. */
  #startsToAsk(what: Mover, mode: DropMode): PlanItem[] {
    if (mode === 'leftovers') return [];
    const items =
      'meal' in what
        ? mode === 'move'
          ? (this.plan?.meals.find((m) => m.id === what.meal)?.items ?? [])
          : [] // a whole meal copied has no times yet
        : (this.plan?.meals.flatMap((m) => m.items).filter((i) => i.id === what.item) ?? []);
    return items.filter(
      (i) =>
        i.kind === 'recipe' &&
        i.recipe &&
        i.ahead &&
        (mode === 'copy' || (i.ahead.start_day !== null && i.ahead.start_day !== undefined))
    );
  }

  #drop(
    what: Mover,
    day: string,
    slotId: number,
    mode: DropMode,
    ifNoneLeft: Exclude<WhenNoneLeft, 'ask'> | 'ask',
    starts: { item_id: number; day: string; time: string }[] = []
  ) {
    const verb = { move: 'Moved', copy: 'Copied', leftovers: 'Leftovers of' }[mode];
    const meal =
      'meal' in what
        ? this.plan?.meals.find((m) => m.id === what.meal)
        : this.plan?.meals.find((m) => m.items.some((i) => i.id === what.item));
    const name = !meal
      ? 'it'
      : 'meal' in what
        ? leftName(meal, this.plan)
        : itemName(
            meal.items.find((i) => i.id === what.item)!,
            this.plan
          );
    const first = starts[0];
    const to = {
      date: day,
      slot_id: slotId,
      mode,
      ...(mode === 'leftovers' ? { if_none_left: ifNoneLeft } : {}),
      ...('meal' in what
        ? starts.length
          ? { starts }
          : {}
        : first
          ? { start: { day: first.day, time: first.time } }
          : {})
    };
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
        'meal' in what ? movePlanMeal(what.meal, to, key) : movePlanItem(what.item, to, key),
      refused: (error) => {
        if (mode !== 'leftovers' || error.code !== 'no_portions_left') return false;
        this.noPortions = { what, day, slotId, name };
        return true;
      }
    });
  }

  // --- Cook once, eat for… and tubs --------------------------------------------------------

  /** Make a batch cook from a planned recipe, with its tubs placed as the preview showed. */
  cookOnce(itemId: number, recipeName: string, body: BatchBody) {
    const word = body.tub_count === 1 ? 'tub' : 'tubs';
    return this.#send({
      label: `Planned ${recipeName} once for ${body.tub_count} ${word}`,
      send: (key) => makeBatch(itemId, body, key)
    });
  }

  /** Plan this batch (Batch cook, Experimental): each recipe through Cook once on the cook day,
   * one change with one Undo. */
  planBatch(body: SessionBody, count: number) {
    return this.#send({
      label: `Planned a batch cook of ${count} recipes`,
      send: (key) => makeSession(body, key)
    });
  }

  /** Change a session: its recipes are taken off and the new ones planned, in one change. */
  changeBatch(id: number, body: SessionBody, count: number) {
    return this.#send({
      label: `Changed the batch cook to ${count} recipes`,
      send: (key) => changeSession(id, body, key)
    });
  }

  /** Take the whole session off the plan: one change, one Undo. */
  async removeBatch(id: number) {
    const result = await this.#send({
      label: 'Took the batch cook off the plan',
      send: (key) => removeSession(id, key)
    });
    if (result.ok) forgetBatchMode(id); // the session is gone: the phone's copy goes (S5)
    return result;
  }

  /** Cooked it, for a meal on the Plan: the meal is answered, with "Any left over?" tubs if any.
   * The pantry was already changed by the review; this is Today's answer, as on Today. */
  cooked(
    meal: PlanMeal,
    leftovers: Leftovers | null,
    undoCooked?: () => Promise<string | void>,
    firstUndo?: () => Promise<string | void>,
    /** What this press cooked, "Cooked A and B" (the review's title), never the whole meal's name. */
    title?: string
  ) {
    const name = mealName(meal, this.plan);
    return sendTwice((changeId) =>
      this.#send({
        label: title ?? `Cooked ${name}`,
        send: (key) => cookedIt(meal.id, leftovers, key),
        alsoUndo: undoCooked,
        firstUndo,
        changeId,
        quiet: true
      })
    );
  }

  /** Put a tub from tubs left in a meal. If another phone has put it in a meal meanwhile, the
   * server refuses (409 tub_taken) rather than moving it out of that meal; the plan reloads. */
  placeTub(tubId: number, name: string, day: string, slotId: number) {
    return this.#send({
      label: `Put ${name} in ${this.slotName(slotId)}`,
      send: (key) => placeTub(tubId, { date: day, slot_id: slotId }, key, true),
      refused: (error) => {
        if (error.code === 'tub_taken') kitchen.changed();
        return false;
      }
    });
  }

  /** "Whose tub?": a person's login id, or null for nobody in particular. */
  setWhose(tubId: number, name: string, memberId: number | null) {
    const who = this.people.find((p) => p.member_id === memberId)?.name;
    return this.#send({
      label: who ? `${name} is ${who}’s` : `${name} is nobody’s in particular`,
      send: (key) => editTub(tubId, { member_id: memberId }, key)
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
      undoButton: 'Undo all', // one Undo takes back every meal it filled
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
