// The All recipes list: every recipe, A to Z, searched and filtered on the server
// (docs/dev/api-0.4-recipes.md section 4). An answer that arrives late (an older search) is
// ignored. The tags for the filter row come with it.

import { ApiError } from './api';
import { listRecipes, listTags, type RecipeRow, type TagCount } from './client/recipes';

const PAGE = 50;

/**
 * What the filter row has chosen: everything, only what can be cooked now, only what uses
 * something about to go off ("soon"), or one tag.
 */
export type RecipeFilter = 'all' | 'cook' | 'soon' | `tag:${string}`;

/** Pantry's "Recipes for these" opens All recipes at `/recipes?filter=use-soon`. */
export function filterFromSearch(search: URLSearchParams): RecipeFilter {
  return search.get('filter') === 'use-soon' ? 'soon' : 'all';
}

export class RecipeList {
  query = $state('');
  filter: RecipeFilter = $state('all');
  recipes = $state<RecipeRow[]>([]);
  tags = $state<TagCount[]>([]);
  /** How many match. */
  total = $state(0);
  /** Every recipe the household has. */
  all = $state(0);
  next = $state<string | null>(null);
  /** False until the first answer, so the page can say "Loading…" instead of "No recipes". */
  loaded = $state(false);
  problem = $state<string | null>(null);
  /** "Show more" failed. Kept apart from `problem`, so the rows, the count and the filters stay. */
  moreProblem = $state<string | null>(null);

  #asked = 0;

  constructor(filter: RecipeFilter = 'all') {
    this.filter = filter;
  }

  #options() {
    return {
      q: this.query,
      tag: this.filter.startsWith('tag:') ? this.filter.slice(4) : null,
      canCookNow: this.filter === 'cook',
      useSoon: this.filter === 'soon'
    };
  }

  /** Fetch the first page for the current search and filter. */
  async load(): Promise<void> {
    const asked = ++this.#asked;
    try {
      const [page, tags] = await Promise.all([
        listRecipes({ ...this.#options(), limit: PAGE }),
        listTags()
      ]);
      if (asked !== this.#asked) return; // a newer search has started
      this.recipes = page.recipes;
      this.total = page.total;
      this.all = page.all_recipes;
      this.next = page.next;
      this.tags = tags.tags;
      this.problem = null;
      this.moreProblem = null;
      // A tag no recipe has any more is gone from the row; so is the choice.
      if (
        this.filter.startsWith('tag:') &&
        !tags.tags.some((t) => `tag:${t.name}` === this.filter)
      ) {
        this.filter = 'all';
      }
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem =
        error instanceof ApiError && error.status === 0
          ? error.detail
          : 'Couldn’t load your recipes. Try again.';
    } finally {
      if (asked === this.#asked) this.loaded = true;
    }
  }

  /** The next page, added to the end. */
  async more(): Promise<void> {
    if (!this.next) return;
    const asked = this.#asked;
    try {
      const page = await listRecipes({ ...this.#options(), after: this.next, limit: PAGE });
      if (asked !== this.#asked) return;
      this.recipes = [...this.recipes, ...page.recipes];
      this.next = page.next;
      this.moreProblem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.moreProblem =
        error instanceof ApiError && error.status === 0
          ? error.detail
          : 'Couldn’t load more recipes. Try again.';
    }
  }
}
