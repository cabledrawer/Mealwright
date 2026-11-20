// A screen's code that is fetched when first wanted (the size limit). A failed fetch is
// forgotten, so the next ask fetches again, and says so: "Couldn’t open that. Try again."
// (cabledrawer 15 Nov). The ask that wanted it ends as if cancelled (words.md §6).

import type { Component } from 'svelte';
import { toasts } from './toast.svelte';

export function couldntOpen(retry?: () => void) {
  toasts.problem('Couldn’t open that. Try again.', retry);
}

export class LazyCode {
  /** The code, once wanted; null before that and after a failed fetch. */
  code = $state.raw<Promise<Component | null> | null>(null);
  /** Where the code comes from; a test swaps it. */
  loader: () => Promise<{ default: Component }>;

  constructor(loader: () => Promise<{ default: Component }>) {
    this.loader = loader;
  }

  /**
   * Start fetching unless it is already on its way or here. If the fetch fails the failed
   * promise is not kept, the toast shows and `onFail` runs (the ask ends as cancelled).
   */
  load(onFail: () => void): void {
    if (this.code) return;
    const code: Promise<Component | null> = this.loader().then(
      (module) => module.default,
      () => {
        if (this.code === code) this.code = null;
        couldntOpen(() => this.load(() => {}));
        onFail();
        return null;
      }
    );
    this.code = code;
  }
}

/**
 * Fetch a module's code on first use: `await fetchCode(() => import('./x'))`. If the fetch fails
 * the toast shows and the result is null, so the caller ends as if cancelled, with nothing
 * changed; nothing is kept, so the next try fetches again. `again` is what the toast's Try again
 * runs (default: fetch the code once more); a caller whose ask can be asked again passes the ask.
 */
export async function fetchCode<T>(load: () => Promise<T>, again?: () => void): Promise<T | null> {
  try {
    return await load();
  } catch {
    couldntOpen(again ?? (() => void fetchCode(load)));
    return null;
  }
}
