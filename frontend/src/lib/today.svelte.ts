// Today's data (docs/dev/api-endpoints.md 6.3c): one read, and the three answers to "Did you cook
// Sambar?". Online only, like the Plan: the last answer is kept in this browser's local storage
// (wiped at sign-out with every other copy, offline/wipe.ts) so Today still opens offline, with
// the answer buttons switched off. An answer shows at once (the card goes), is saved with its
// change ID, and is offered for Undo; then Today is fetched again.

import { cantReachWords, cantReach } from './api';
import { serverUndo } from './client/changes';
import type { PlanMeal } from './client/plan';
import {
  cookedIt,
  didntCook,
  getToday,
  moveIt,
  type Leftovers,
  type TodayData,
  type WaitingMeal
} from './client/today';
import { kitchen } from './freshness.svelte';
import { fetchCode } from './lazyCode.svelte';
import { loaders } from './lazyModules';
import { sendTwice } from './sendTwice';
import { network } from './network.svelte';
import { COPY_KEY, forgetToday, readCopy, wipeCount, writeCopy } from './todayCopy';
import { leftName } from './planMeals';
import { save } from './save';
import { session } from './session.svelte';
import { couldntLoad } from './errorWords.js';

export { COPY_KEY, forgetToday, readCopy };

export class TodayModel {
  data = $state<TodayData | null>(null);
  loaded = $state(false);
  problem = $state<string | null>(null);
  /** What is on screen is the saved copy, not what the server just said. */
  fromCopy = $state(false);

  #asked = 0;

  /** Answers wait for the server: offline, or showing the saved copy. */
  readonly readonly = $derived(network.offline || this.fromCopy);

  /** Today's meals that are still on the table, in the order of the day. */
  readonly eating = $derived.by((): PlanMeal[] => {
    const data = this.data;
    if (!data) return [];
    const at = (id: number) => data.slots.findIndex((s) => s.id === id);
    return data.plan.meals
      .filter(
        (m) =>
          m.date === data.today &&
          at(m.slot_id) >= 0 &&
          (m.status === 'planned' || m.status === 'cooked')
      )
      .sort((a, b) => at(a.slot_id) - at(b.slot_id));
  });

  /** The meal being asked about now, and how many more are waiting behind it. */
  readonly asking = $derived(this.data?.waiting[0] ?? null);
  readonly moreWaiting = $derived(Math.max(0, (this.data?.waiting.length ?? 0) - 1));

  async load(): Promise<void> {
    const asked = ++this.#asked;
    const began = wipeCount();
    const login = session.me?.id ?? null;
    try {
      const data = await getToday();
      if (began !== wipeCount()) return; // signed out or wiped meanwhile: nothing of it is kept
      if (asked !== this.#asked) return;
      this.data = data;
      this.fromCopy = false;
      this.loaded = true;
      this.problem = null;
      if (login !== null) writeCopy(data, login, began);
    } catch (error) {
      if (asked !== this.#asked) return;
      const unreachable = cantReach(error);
      if (unreachable && !this.data) {
        const copy = readCopy();
        if (copy) {
          this.data = copy;
          this.fromCopy = true;
          this.loaded = true;
          this.problem = null;
          return;
        }
      }
      if (this.data) {
        // Keep what is on screen; the answer buttons wait for the server.
        if (unreachable) this.fromCopy = true;
        return;
      }
      this.problem = unreachable ? cantReachWords() : couldntLoad('Today');
    }
  }

  slotName(slotId: number): string {
    return this.data?.slots.find((s) => s.id === slotId)?.name ?? 'Meal';
  }

  mealOf(waiting: WaitingMeal): PlanMeal | null {
    return this.data?.plan.meals.find((m) => m.id === waiting.meal_id) ?? null;
  }

  nameOf(waiting: WaitingMeal): string {
    const meal = this.mealOf(waiting);
    return meal ? leftName(meal, this.data?.plan ?? null) : 'it';
  }

  #send(options: {
    label: string;
    mealId: number;
    send: (key: string) => ReturnType<typeof didntCook>;
    /** Also undone when this is: what "Cooked it" took from the pantry (one Undo for both). */
    alsoUndo?: () => Promise<string | void>;
    /** Undone first (a tub put on a meal after "Cooked it", F65). */
    firstUndo?: () => Promise<string | void>;
    /** Sent again with the same ID, and no toast of its own: the caller says it once. */
    changeId?: string;
    quiet?: boolean;
  }) {
    let before: TodayData | null = null;
    let undoer: (() => Promise<string | void>) | null = null;
    return save(
      {
        apply: () => {
          before = $state.snapshot(this.data) as TodayData | null;
          if (this.data) {
            // The card goes at once; the next one (if any) shows.
            this.data = {
              ...this.data,
              waiting: this.data.waiting.filter((w) => w.meal_id !== options.mealId)
            };
          }
        },
        rollback: () => {
          if (before) this.data = before;
        },
        send: (key) => options.send(key),
        saved: () => kitchen.changed(),
        quiet: options.quiet,
        undo: {
          label: options.label,
          labelFrom: (value) => value.change?.summary,
          skip: (value) => value.change === null,
          run: (value) => {
            const change = value.change;
            if (!change?.can_undo) return false;
            undoer ??= serverUndo(change.id);
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
   * Cooked it, with "Any left over?" if there is any. `undoCooked` takes back what the review
   * took from the pantry: this answer's Undo does both.
   */
  cooked(
    waiting: WaitingMeal,
    leftovers: Leftovers | null,
    undoCooked?: () => Promise<string | void>,
    firstUndo?: () => Promise<string | void>,
    /** What this press cooked, "Cooked A and B" (the review's title), never the whole meal's name. */
    title?: string
  ) {
    const name = this.nameOf(waiting);
    return sendTwice((changeId) =>
      this.#send({
        label: title ?? `Cooked ${name}`,
        mealId: waiting.meal_id,
        send: (key) => cookedIt(waiting.meal_id, leftovers, key),
        alsoUndo: undoCooked,
        firstUndo,
        changeId,
        quiet: true
      })
    );
  }

  didnt(waiting: WaitingMeal) {
    const name = this.nameOf(waiting);
    return this.#send({
      label: `Didn’t cook ${name}`,
      mealId: waiting.meal_id,
      send: (key) => didntCook(waiting.meal_id, key)
    });
  }

  /**
   * "Move it": to a day and a meal. Each recipe in the meal that had a start time for its long
   * wait is asked "When will you start it?" again for the new day, as the Plan's Move does (Move,
   * No time yet, Cancel); Cancel moves nothing.
   */
  async move(waiting: WaitingMeal, day: string, slotId: number) {
    const name = this.nameOf(waiting);
    const meal = this.data?.plan.meals.find((m) => m.id === waiting.meal_id);
    const asking = (meal?.items ?? []).filter(
      (i) => i.kind === 'recipe' && i.recipe && i.ahead && i.ahead.start_day
    );
    const starts: { item_id: number; day: string; time: string }[] = [];
    if (asking.length) {
      const loaded = await fetchCode(loaders.startAsk);
      if (!loaded) return undefined; // Cancel: nothing is moved, and the next try fetches again
      const { startAsk } = loaded;
      for (const item of asking) {
        const start = await startAsk.ask(
          { id: item.recipe!.id, name: item.recipe!.name },
          { day, slotId, slotName: this.slotName(slotId) },
          { method: item.method_id ?? null, adding: true, button: 'Move' }
        );
        if (start === null) return undefined; // Cancel: nothing is moved
        if (start) starts.push({ item_id: item.id, ...start });
      }
    }
    return this.#send({
      label: `Moved ${name} to ${this.slotName(slotId)}`,
      mealId: waiting.meal_id,
      send: (key) =>
        moveIt(
          waiting.meal_id,
          { date: day, slot_id: slotId, ...(starts.length ? { starts } : {}) },
          key
        )
    });
  }
}
