// Today's data (docs/dev/api-0.2.md 6.3c): one read, and the three answers to "Did you cook
// Sambar?". Online only, like the Plan: the last answer is kept in this browser's local storage
// (wiped at sign-out with every other copy, offline/wipe.ts) so Today still opens offline, with
// the answer buttons switched off. An answer shows at once (the card goes), is saved with its
// change ID, and is offered for Undo; then Today is fetched again.

import { cantReachWords, cantReach, forgetWhenSessionEnds } from './api';
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
import { network } from './network.svelte';
import { rememberedLogin } from './offline/device';
import { wipePending } from './offline/wipePending.svelte';
import { mealName } from './planMeals';
import { save } from './save';
import { session } from './session.svelte';

export const COPY_KEY = 'mealwright.today-copy';

/** Counts the wipes: a read that began before one must not write its copy after it. */
let wipes = 0;

/** Who the copy belongs to: the signed-in login, else (opening offline) the one this browser last knew. */
function owner(): number | null {
  return session.me?.id ?? rememberedLogin()?.id ?? null;
}

/**
 * What was saved last time Today was read, but only the signed-in login's own (the copy is
 * saved with its owner). Another login's copy, or one in the old format, is refused and removed.
 * Null when there is none.
 */
export function readCopy(): TodayData | null {
  try {
    const text = localStorage.getItem(COPY_KEY);
    if (!text) return null;
    const me = owner();
    if (me === null) return null; // can't tell whose it is: shown to nobody
    const copy = JSON.parse(text) as { v?: number; login_id?: number; data?: TodayData };
    if (copy.v === 2 && copy.login_id === me && copy.data && Array.isArray(copy.data.waiting)) {
      return copy.data;
    }
    localStorage.removeItem(COPY_KEY);
    return null;
  } catch {
    return null;
  }
}

/**
 * Keep an answer as the copy, for the login that asked, unless that login has signed out or the
 * browser has been wiped since the request began (`began` is `wipes` then).
 */
function writeCopy(data: TodayData, login: number, began: number): void {
  if (began !== wipes || session.me?.id !== login || wipePending()) return;
  try {
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 2, login_id: login, data }));
  } catch {
    // Storage blocked or full: Today just won't open offline.
  }
}

/** Forget the copy (sign-out, a wipe in any tab): another login may be next. */
export function forgetToday(): void {
  wipes += 1;
  try {
    localStorage.removeItem(COPY_KEY);
  } catch {
    // Storage blocked: nothing kept there.
  }
}

forgetWhenSessionEnds(forgetToday);

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
    const began = wipes;
    const login = session.me?.id ?? null;
    try {
      const data = await getToday();
      if (began !== wipes) return; // signed out or wiped meanwhile: nothing of it is kept
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
      this.problem = unreachable ? cantReachWords() : 'Couldn’t load Today. Try again.';
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
    return meal ? mealName(meal, this.data?.plan ?? null) : 'it';
  }

  #send(options: {
    label: string;
    mealId: number;
    send: (key: string) => ReturnType<typeof didntCook>;
    /** Also undone when this is: what "Cooked it" took from the pantry (one Undo for both). */
    alsoUndo?: () => Promise<string | void>;
  }) {
    let before: TodayData | null = null;
    let undoer: (() => Promise<string | void>) | null = null;
    return save({
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
      undo: {
        label: options.label,
        labelFrom: (value) => value.change?.summary,
        skip: (value) => value.change === null,
        run: (value) => {
          const change = value.change;
          if (!change?.can_undo) return false;
          undoer ??= serverUndo(change.id);
          return (async () => {
            const own = await undoer!();
            const more = await options.alsoUndo?.();
            return more ?? own;
          })();
        }
      }
    });
  }

  /**
   * Cooked it, with "Any left over?" if there is any. `undoCooked` takes back what the review
   * took from the pantry: this answer's Undo does both.
   */
  cooked(
    waiting: WaitingMeal,
    leftovers: Leftovers | null,
    undoCooked?: () => Promise<string | void>
  ) {
    const name = this.nameOf(waiting);
    return this.#send({
      label: `Cooked ${name}`,
      mealId: waiting.meal_id,
      send: (key) => cookedIt(waiting.meal_id, leftovers, key),
      alsoUndo: undoCooked
    });
  }

  didnt(waiting: WaitingMeal) {
    const name = this.nameOf(waiting);
    return this.#send({
      label: `Didn’t cook ${name}`,
      mealId: waiting.meal_id,
      send: (key) => didntCook(waiting.meal_id, key)
    });
  }

  move(waiting: WaitingMeal, day: string, slotId: number) {
    const name = this.nameOf(waiting);
    return this.#send({
      label: `Moved ${name} to ${this.slotName(slotId)}`,
      mealId: waiting.meal_id,
      send: (key) => moveIt(waiting.meal_id, { date: day, slot_id: slotId }, key)
    });
  }
}
