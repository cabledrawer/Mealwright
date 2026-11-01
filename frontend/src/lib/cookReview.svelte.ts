// The "Cooked it" review's state (docs/dev/api-0.2.md 6.3d): what it would take from the pantry
// for each recipe of a meal (one tab each), the person's say on every row, and one Confirm that
// takes it all as one change with one Undo. Online only, like the Plan.
//
// Where it opens from: Today's card and "Did you cook…?", the Plan's menus, and a Cook once batch.
// A meal's recipes go to the server together (one pool of packets, so two recipes never take
// the same grams); a batch cook is its own call, as the server wants it (a batch is cooked once,
// for the cook day and its tubs).

import { ApiError, cantReach, cantReachWords } from './api';
import { serverUndo } from './client/changes';
import {
  cookBatch,
  cookMeal,
  previewBatch,
  previewMeal,
  type CookedMealWrite,
  type CookedWrite,
  type Proposal
} from './client/cook';
import type { Answer } from './client/types';
import { choicesOf, newRowState, withAnswer, type RowState } from './cookRows';
import { kitchen } from './freshness.svelte';
import { save, type Outcome } from './save';

/** One recipe to cook: a meal item, or a Cook once batch. */
export interface CookPart {
  itemId: number | null;
  batchId: number | null;
  name: string;
}

/** What the review is about. */
export interface CookTarget {
  /** "Cooked Sambar". */
  title: string;
  /** "Thu 15 Oct · dinner". */
  subtitle: string;
  /** The meal the recipes are in (the server shares the packets across them). */
  mealId: number | null;
  parts: CookPart[];
}

/** One tab: a recipe, with its portions, its rows as proposed, and the person's say on them. */
export class CookTab {
  proposal = $state<Proposal | null>(null);
  /** Portions the person set; null: as the server worked them out. */
  chosen = $state<number | null>(null);
  states = $state<Record<string, RowState>>({});

  constructor(readonly part: CookPart) {}

  readonly portions = $derived(this.chosen ?? this.proposal?.portions ?? 1);
  readonly rows = $derived(this.proposal?.rows ?? []);

  state(key: string): RowState | undefined {
    return this.states[key];
  }

  patch(key: string, change: Partial<RowState>): void {
    this.states[key] = { ...(this.states[key] ?? newRowState()), ...change };
  }
}

export class CookReview {
  target = $state<CookTarget | null>(null);
  tabs = $state<CookTab[]>([]);
  active = $state(0);
  answers = $state<Answer[]>([]);
  loading = $state(false);
  saving = $state(false);
  problem = $state<string | null>(null);

  #seq = 0;

  readonly tab = $derived(this.tabs[this.active] ?? null);
  /** A target with no recipe in it has nothing to take from the pantry. */
  readonly nothingToTake = $derived(this.target !== null && this.tabs.length === 0);

  async open(target: CookTarget): Promise<void> {
    this.target = target;
    this.tabs = target.parts.map((part) => new CookTab(part));
    this.active = 0;
    this.answers = [];
    this.problem = null;
    this.saving = false;
    await this.refresh();
  }

  close(): void {
    this.#seq++;
    this.target = null;
    this.tabs = [];
    this.loading = false;
    this.saving = false;
  }

  /** Ask the server again (portions changed, or an answer was given). Changes nothing there. */
  async refresh(): Promise<void> {
    const target = this.target;
    if (!target || this.tabs.length === 0) return;
    const seq = ++this.#seq;
    this.loading = true;
    try {
      const done: [CookTab, Proposal][] = [];
      const items = this.tabs.filter((t) => t.part.itemId !== null);
      if (items.length && target.mealId !== null) {
        const answer = await previewMeal(target.mealId, {
          items: items.map((t) => ({
            item_id: t.part.itemId as number,
            ...(t.chosen !== null ? { portions: t.chosen } : {})
          })),
          answers: this.answers
        });
        for (const one of answer.items) {
          const tab = items.find((t) => t.part.itemId === one.item_id);
          if (tab) done.push([tab, one.proposal]);
        }
      }
      for (const tab of this.tabs.filter((t) => t.part.batchId !== null)) {
        done.push([
          tab,
          await previewBatch(tab.part.batchId as number, {
            ...(tab.chosen !== null ? { portions: tab.chosen } : {}),
            answers: this.answers
          })
        ]);
      }
      if (seq !== this.#seq) return; // a newer question was asked meanwhile
      for (const [tab, proposal] of done) tab.proposal = proposal;
      this.problem = null;
    } catch (error) {
      if (seq !== this.#seq) return;
      this.problem = cantReach(error)
        ? cantReachWords()
        : error instanceof ApiError
          ? error.detail
          : 'Couldn’t work out what to take. Try again.';
    } finally {
      if (seq === this.#seq) this.loading = false;
    }
  }

  setPortions(tab: CookTab, portions: number): Promise<void> {
    tab.chosen = Math.min(999, Math.max(1, Math.round(portions)));
    return this.refresh();
  }

  /** An answer to a question (a weight, a size). A newer one for the same question replaces it. */
  addAnswer(answer: Answer, refresh = true): Promise<void> {
    this.answers = withAnswer(this.answers, answer);
    return refresh ? this.refresh() : Promise.resolve();
  }

  /**
   * Take it all out of the pantry: the meal's recipes as one change, each batch as its own.
   * Resolves with every outcome; nothing was taken for one that failed (its toast says why).
   */
  async confirm(): Promise<Outcome<CookedMealWrite | CookedWrite>[]> {
    const target = this.target;
    if (!target) return [];
    const outcomes: Outcome<CookedMealWrite | CookedWrite>[] = [];
    const items = this.tabs.filter((t) => t.part.itemId !== null);
    this.saving = true;
    const label = target.title;
    if (items.length && target.mealId !== null) {
      const mealId = target.mealId;
      const body = {
        items: items.map((t) => ({
          item_id: t.part.itemId as number,
          ...(t.chosen !== null ? { portions: t.chosen } : {}),
          choices: choicesOf(t.rows, t.states)
        })),
        answers: this.answers
      };
      outcomes.push(
        await this.#send(label, (key, asked) => cookMeal(mealId, withAsked(body, asked), key))
      );
    }
    for (const tab of this.tabs.filter((t) => t.part.batchId !== null)) {
      if (outcomes.some((o) => !o.ok)) break;
      const batchId = tab.part.batchId as number;
      const body = {
        ...(tab.chosen !== null ? { portions: tab.chosen } : {}),
        choices: choicesOf(tab.rows, tab.states),
        answers: this.answers
      };
      outcomes.push(
        await this.#send(label, (key, asked) => cookBatch(batchId, withAsked(body, asked), key))
      );
    }
    this.saving = false;
    return outcomes;
  }

  #send<T extends CookedMealWrite | CookedWrite>(
    label: string,
    send: (key: string, asked: Answer[]) => Promise<T>
  ): Promise<Outcome<T>> {
    return save<T>({
      apply: () => {},
      rollback: () => {},
      send,
      saved: () => kitchen.changed(),
      undo: {
        label,
        labelFrom: (value) => value.change.summary,
        skip: (value) => !value.change.can_undo,
        run: (value) => serverUndo(value.change.id)()
      }
    });
  }
}

/** The answers the person gave on the screen, then any the server asked for as the confirm went. */
function withAsked<B extends { answers: Answer[] }>(body: B, asked: Answer[]): B {
  return { ...body, answers: [...body.answers, ...asked].slice(0, 20) };
}
