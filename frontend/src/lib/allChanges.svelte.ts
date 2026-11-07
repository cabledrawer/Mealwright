// Settings → Recent changes (F172, cabledrawer 7 Nov): every kind of change (pantry, shopping, plan,
// cooking, recipes, imports, ingredients), newest first, each with Undo for 7 days, and
// "Show more" for older ones. The list comes from GET /changes with no `area`. Answers that
// arrive late are ignored.

import { cantReach, cantReachWords } from './api';
import { listChanges, undoFromList } from './client/changes';
import type { Change } from './client/types';

/** How many changes one page shows. */
export const RECENT_PAGE = 20;

export class AllChanges {
  changes = $state<Change[]>([]);
  /** The server has older ones: the `next` of the last page. */
  next = $state<string | null>(null);
  loaded = $state(false);
  loadingMore = $state(false);
  problem = $state<string | null>(null);
  moreProblem = $state<string | null>(null);

  #asked = 0;

  /** The newest page (and, after a change, again: any pages shown past it are dropped). */
  async load(): Promise<void> {
    const asked = ++this.#asked;
    try {
      const list = await listChanges({ limit: RECENT_PAGE });
      if (asked !== this.#asked) return;
      this.changes = list.changes;
      this.next = list.next;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem = cantReach(error) ? cantReachWords() : 'Couldn’t load the recent changes.';
    } finally {
      if (asked === this.#asked) this.loaded = true;
    }
  }

  /** "Show more": the next older page, added below. */
  async more(): Promise<void> {
    if (this.next === null || this.loadingMore) return;
    const asked = this.#asked;
    this.loadingMore = true;
    this.moreProblem = null;
    try {
      const list = await listChanges({ limit: RECENT_PAGE, before: this.next });
      if (asked !== this.#asked) return;
      const have = new Set<number>(this.changes.map((c) => c.id)); // eslint-disable-line svelte/prefer-svelte-reactivity -- local, not state
      this.changes = [...this.changes, ...list.changes.filter((c) => !have.has(c.id))];
      this.next = list.next;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.moreProblem = cantReach(error)
        ? cantReachWords()
        : 'Couldn’t load more changes. Try again.';
    } finally {
      this.loadingMore = false;
    }
  }

  /** Undo from the list (anyone's change, within the undo window). */
  async undo(change: Change): Promise<void> {
    await undoFromList(change, this);
    void this.load();
  }
}
