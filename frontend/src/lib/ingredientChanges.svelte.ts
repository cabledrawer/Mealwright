// Ingredients → Recent changes (spec, History and undo): the latest changes to
// ingredients (new, Staple on/off, removed, merged, edited), with Undo for 7 days. The
// list comes from GET /changes?area=ingredients. Answers that arrive late are ignored.

import { ApiError } from './api';
import { listChanges, undoFromList } from './client/changes';
import type { Change } from './client/types';

/** How many changes the panel and the sheet show. */
export const RECENT_INGREDIENT_CHANGES = 10;

export class IngredientChanges {
  changes = $state<Change[]>([]);
  /** There are more than the ones listed (the server has a next page). */
  more = $state(false);
  loaded = $state(false);
  problem = $state<string | null>(null);

  #asked = 0;

  async load(): Promise<void> {
    const asked = ++this.#asked;
    try {
      const list = await listChanges({
        area: 'ingredients',
        limit: RECENT_INGREDIENT_CHANGES
      });
      if (asked !== this.#asked) return;
      this.changes = list.changes;
      this.more = list.next !== null;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem =
        error instanceof ApiError && error.status === 0
          ? error.detail
          : 'Couldn’t load the recent changes.';
    } finally {
      if (asked === this.#asked) this.loaded = true;
    }
  }

  /** Undo from the list (anyone's change, within the undo window). */
  undo(change: Change): Promise<void> {
    return undoFromList(change, this);
  }
}
