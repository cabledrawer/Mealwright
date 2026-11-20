// Batch cook's screen (Experimental; 0.8 wave 6, B2; mockups Dark-BatchPick08-Phone and
// -Desktop): the cook day, how many recipes, the picks the server suggests, Swap and Show me
// others. The server works the picks out (docs/dev/api-endpoints.md 6.3a-2): the same data always gives
// the same picks, so a swap sends the others as `keep` and the swapped one as `skip`, and Show me
// others sends the whole last set as `skip`.

import { ApiError, cantReach, cantReachWords } from './api';
import { getSuggestions, type BatchPick, type BatchSuggestions } from './client/batch';

export const COUNTS = [2, 3, 4] as const;

const once = (ids: number[]) => ids.filter((id, at) => ids.indexOf(id) === at);

export class BatchPickModel {
  /** The cook day the person chose, or null: the server's own (the next day with no cooking). */
  day = $state<string | null>(null);
  count = $state(3);
  result = $state<BatchSuggestions | null>(null);
  /** Something is being fetched (the first time, or a swap, others, a new count). */
  loading = $state(false);
  problem = $state<string | null>(null);
  /** The recipes swapped out, and the sets shown before: asked not to come back first. */
  #skipped: number[] = [];
  #asked = 0;

  get picks(): BatchPick[] {
    return this.result?.picks ?? [];
  }

  /** The day shown: the person's choice, else the server's default. */
  get cookDay(): string | null {
    return this.day ?? this.result?.day ?? null;
  }

  /** The days offered as chips: the next free ones, with the chosen day among them. */
  get chips(): string[] {
    const free = this.result?.free_days ?? [];
    const chosen = this.cookDay;
    return chosen && !free.includes(chosen) ? [chosen, ...free].slice(0, 4) : free;
  }

  /** Start from a session's own picks ("Change"): its day, its size and its recipes kept. */
  async startFrom(day: string, recipeIds: number[]): Promise<void> {
    this.day = day;
    this.count = Math.min(4, Math.max(2, recipeIds.length));
    await this.#ask({ keep: recipeIds });
  }

  async load(): Promise<void> {
    await this.#ask({});
  }

  async setCount(count: number): Promise<void> {
    if (count === this.count) return;
    this.count = count;
    await this.#ask({ keep: this.picks.map((p) => p.recipe_id).slice(0, count) });
  }

  setDay(day: string): void {
    this.day = day;
  }

  /** Swap one: the next best that is not already picked, the others staying. */
  async swap(recipeId: number): Promise<void> {
    this.#skipped = once([...this.#skipped, recipeId]);
    await this.#ask({
      keep: this.picks.map((p) => p.recipe_id).filter((id) => id !== recipeId)
    });
  }

  /** A fresh set, while there are others. */
  async others(): Promise<void> {
    this.#skipped = once([...this.#skipped, ...this.picks.map((p) => p.recipe_id)]);
    await this.#ask({});
  }

  async #ask(ask: { keep?: number[] }): Promise<void> {
    const asked = ++this.#asked;
    this.loading = true;
    try {
      const found = await getSuggestions({
        day: this.day ?? undefined,
        count: this.count,
        keep: ask.keep,
        skip: this.#skipped.slice(-200)
      });
      if (asked !== this.#asked) return;
      this.result = found;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem = cantReach(error)
        ? cantReachWords()
        : error instanceof ApiError && error.code === 'batch_cook_hidden'
          ? error.detail
          : 'Couldn’t find recipes. Try again.';
    } finally {
      if (asked === this.#asked) this.loading = false;
    }
  }
}
