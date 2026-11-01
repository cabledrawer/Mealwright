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
import { TOO_MANY_ANSWERS, choicesOf, newRowState, withAnswer, type RowState } from './cookRows';
import { kitchen } from './freshness.svelte';
import { save, worthRetrying, type Outcome } from './save';
import { newChangeId } from './changeId';
import { toasts } from './toast.svelte';
import { undoHistory, type UndoEntry } from './undo.svelte';

export const COULDNT_REACH_COOK =
  'Couldn’t reach the server. Some of “Cooked it” may be saved: check Recent changes.';
export const COULDNT_COOK = 'Couldn’t save “Cooked it”. Nothing was changed. Try again.';

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

type Outcomes = Outcome<CookedMealWrite | CookedWrite>[];

export class CookReview {
  target = $state<CookTarget | null>(null);
  tabs = $state<CookTab[]>([]);
  active = $state(0);
  answers = $state<Answer[]>([]);
  loading = $state(false);
  saving = $state(false);
  problem = $state<string | null>(null);
  /** An answer could not be kept: the server takes at most 20 at a time. */
  tooMany = $state(false);

  #seq = 0;

  readonly tab = $derived(this.tabs[this.active] ?? null);
  /** A target with no recipe in it has nothing to take from the pantry. */
  readonly nothingToTake = $derived(this.target !== null && this.tabs.length === 0);

  async open(target: CookTarget): Promise<void> {
    this.target = target;
    this.tabs = target.parts.map((part) => new CookTab(part));
    this.active = 0;
    this.answers = [];
    this.tooMany = false;
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
    const kept = withAnswer(this.answers, answer);
    this.tooMany = kept === this.answers;
    this.answers = kept;
    if (this.tooMany) return Promise.resolve();
    return refresh ? this.refresh() : Promise.resolve();
  }

  /**
   * Take it all out of the pantry: the meal's recipes as one change, each batch as its own.
   * Resolves with every outcome; nothing was taken for one that failed (its toast says why).
   */
  async confirm(
    options: {
      /**
       * What follows the pantry (the meal's answer). false: it was refused, so the pantry is put
       * back. 'unsure': its reply was lost, so nothing is taken back.
       */
      after?: (outcomes: Outcomes) => Promise<boolean | 'unsure'>;
    } = {}
  ): Promise<{ ok: boolean; outcomes: Outcomes }> {
    const target = this.target;
    if (!target) return { ok: false, outcomes: [] };
    const outcomes: Outcomes = [];
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
        await this.#send((key, asked) => cookMeal(mealId, this.#merged(body, asked), key))
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
        await this.#send((key, asked) => cookBatch(batchId, this.#merged(body, asked), key))
      );
    }
    // A refusal (the server answered no) takes back what worked. A reply that never came may
    // still have been saved, so then nothing is taken back (proposed, for cabledrawer).
    const failed = outcomes.find((o) => !o.ok);
    let result: 'ok' | 'unsure' | 'refused' = 'ok';
    if (failed && !failed.ok)
      result = !failed.cancelled && worthRetrying(failed.error) ? 'unsure' : 'refused';
    if (result === 'ok' && options.after) {
      const answered = await options.after(outcomes);
      result = answered === true ? 'ok' : answered === 'unsure' ? 'unsure' : 'refused';
    }
    if (result === 'refused') await this.#takeBack(outcomes);
    else if (result === 'unsure') this.#keep(outcomes);
    else if (!options.after && outcomes.length > 0) {
      const done = outcomes.flatMap((o) => (o.ok ? [o.value] : []));
      undoHistory.record(
        this.#undoEntry(done, done.length === 1 ? done[0]!.change.summary : label)
      );
    }
    this.saving = false;
    return { ok: result !== 'refused', outcomes };
  }

  /** The screen's answers plus any the server asked for as the confirm went; 20 at most. */
  #merged<B extends { answers: Answer[] }>(body: B, asked: Answer[]): B {
    const merged = withAsked(body, asked);
    if (asked.some((a) => !merged.answers.includes(a))) {
      this.tooMany = true;
      throw new ApiError(422, TOO_MANY_ANSWERS, 'too_many_answers');
    }
    return merged;
  }

  #undoEntry(done: (CookedMealWrite | CookedWrite)[], label: string): UndoEntry {
    const undoers = done.filter((v) => v.change.can_undo).map((v) => serverUndo(v.change.id));
    return {
      label,
      needsServer: true,
      undo: async () => {
        let said: string | void = undefined;
        for (const undo of [...undoers].reverse()) said = (await undo()) ?? said;
        return said;
      }
    };
  }

  /** The reply was lost: keep every change that worked, each with its Undo, and say so. */
  #keep(outcomes: Outcomes): void {
    for (const o of outcomes) {
      if (o.ok)
        undoHistory.record(this.#undoEntry([o.value], o.value.change.summary), { toast: false });
    }
    toasts.show(COULDNT_REACH_COOK, { tone: 'problem' });
    kitchen.changed();
  }

  /**
   * A call was refused (or the meal's answer): put back what the others took, last first, and
   * say nothing was changed. An Undo that comes back "partly" counts as stayed, and its message
   * is shown. Whatever cannot be put back (the server went away) keeps a normal Undo, so
   * nothing is left without one. (Proposed, for cabledrawer.)
   */
  async #takeBack(outcomes: Outcomes): Promise<void> {
    const worked = outcomes.flatMap((o) => (o.ok && o.value.change.can_undo ? [o.value] : []));
    const stayed: (CookedMealWrite | CookedWrite)[] = [];
    const notes: string[] = [];
    for (const value of [...worked].reverse()) {
      try {
        const said = await serverUndo(value.change.id)();
        if (said) notes.push(said);
      } catch {
        stayed.push(value);
      }
    }
    if (stayed.length === 0) {
      toasts.show(notes.length ? notes.join(' ') : COULDNT_COOK, { tone: 'problem' });
      return;
    }
    for (const value of stayed) {
      undoHistory.record(this.#undoEntry([value], value.change.summary));
    }
  }

  /** One call, sent again once with the same key if the reply never came (the server then
   * answers from the first, taking nothing twice). It shows nothing itself: the review says it. */
  async #send<T extends CookedMealWrite | CookedWrite>(
    send: (key: string, asked: Answer[]) => Promise<T>
  ): Promise<Outcome<T>> {
    const key = newChangeId();
    const once = () =>
      save<T>(
        {
          apply: () => {},
          rollback: () => {},
          send,
          saved: () => kitchen.changed(),
          quiet: true
        },
        key
      );
    const first = await once();
    return !first.ok && !first.cancelled && worthRetrying(first.error) ? once() : first;
  }
}

/** The answers the person gave on the screen, then any the server asked for as the confirm went. */
function withAsked<B extends { answers: Answer[] }>(body: B, asked: Answer[]): B {
  return { ...body, answers: asked.reduce(withAnswer, body.answers) };
}

/** One Undo for what the outcomes changed in the pantry (the meal's Undo runs it too). */
export function undoAll(
  outcomes: Outcome<CookedMealWrite | CookedWrite>[]
): () => Promise<string | void> {
  const undoers = outcomes.flatMap((o) =>
    o.ok && o.value.change.can_undo ? [serverUndo(o.value.change.id)] : []
  );
  return async () => {
    let said: string | void = undefined;
    for (const undo of [...undoers].reverse()) said = (await undo()) ?? said;
    return said;
  };
}

/** What the meal's answer came to for the review: done, refused, or its reply never came. */
export function answered(outcome: Outcome<unknown>): boolean | 'unsure' {
  if (outcome.ok) return true;
  return !outcome.cancelled && worthRetrying(outcome.error) ? 'unsure' : false;
}
