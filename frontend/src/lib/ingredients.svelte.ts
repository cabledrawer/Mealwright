// The Ingredients list: every food, searched by any name on the server (contract 6.2).
// Answers that arrive late (an older search) are ignored.

import { cantReachWords, cantReach } from './api';
import { listFoods } from './client/foods';
import type { FoodFilter, FoodList, FoodRow } from './client/types';

const PAGE = 50;

export class IngredientsList {
  query = $state('');
  filter = $state<FoodFilter>('all');
  foods = $state<FoodRow[]>([]);
  counts = $state<FoodList['counts']>({
    all: 0,
    staples: 0,
    unused: 0,
    maybe_same: 0,
    maybe_same_pairs: 0
  });
  next = $state<string | null>(null);
  /** False until the first answer, so the page can show "Loading…" instead of "No foods". */
  loaded = $state(false);
  problem = $state<string | null>(null);
  /** The list has had a good answer since the page opened. */
  answered = $state(false);
  /** The search and filter the rows on show are the answer to (the "+ New ingredient" offer
   *  waits until they match what is typed). */
  answeredFor = $state<{ query: string; filter: FoodFilter } | null>(null);

  /** Nothing has loaded yet and the last try failed: the page shows its note instead of an
   *  empty list. Once rows are showing, a failed reload (a search, the live stream) keeps them
   *  and says so in the list (F67 review). */
  get couldntLoad(): boolean {
    return this.problem !== null && !this.answered;
  }

  #asked = 0;

  /** Fetch the first page for the current search and filter. */
  async load(): Promise<void> {
    const asked = ++this.#asked;
    const { query, filter } = this;
    try {
      const list = await listFoods({ q: query, filter, limit: PAGE });
      if (asked !== this.#asked) return; // a newer search has started
      this.foods = list.foods;
      this.counts = list.counts;
      this.next = list.next;
      this.problem = null;
      this.answered = true;
      this.answeredFor = { query, filter };
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem = cantReach(error) ? cantReachWords() : 'Couldn’t load your ingredients.';
    } finally {
      if (asked === this.#asked) this.loaded = true;
    }
  }

  /** The next page, added to the end. */
  async more(): Promise<void> {
    if (!this.next) return;
    const asked = this.#asked;
    const list = await listFoods({
      q: this.query,
      filter: this.filter,
      after: this.next,
      limit: PAGE
    });
    if (asked !== this.#asked) return;
    this.foods = [...this.foods, ...list.foods];
    this.next = list.next;
  }
}
