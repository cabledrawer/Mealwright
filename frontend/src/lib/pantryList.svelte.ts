// Pantry → the shopping list (spec, "Tap a staple when it runs out" and "+ List", cabledrawer
// 18 Oct, 0.3): a tap on a staple chip, or on "+ List" in a running-low row, adds that
// ingredient to the MAIN shopping list. It goes through the same add action and waiting
// list as Shopping's own add box (ShoppingModel.add, sync-protocol 4.2 and 11.3), so a tap
// made while the connection is failing is kept on this phone and sent once, when the server
// is back. Never lost, never doubled.
//
// What is on the list comes from the same copy Shopping draws from (the server's last answer
// with the waiting changes on top), so a tap shows its tick at once, and the tick follows
// live updates, Undo and another phone's changes the way Shopping does. An ingredient
// counts as "on the list" while it has an unticked line there.

import { untrack } from 'svelte';
import { SvelteSet } from 'svelte/reactivity';
import { toasts } from '$lib/toast.svelte';
import { ShoppingModel } from './shopping/store.svelte';

export class PantryList {
  readonly #shopping = new ShoppingModel();
  /** Taps whose line isn't on the screen yet (a second tap in that moment is the same tap). */
  readonly #pending = new SvelteSet<number>();

  /** Is this ingredient on the main shopping list now (including a tap still waiting to be sent)? */
  onList(foodId: number): boolean {
    return this.#shopping.lineFor(foodId) !== undefined;
  }

  /** Fetch the list again (the copy only changes by what the server says). */
  refresh(): Promise<void> {
    return untrack(() => this.#shopping.load());
  }

  /** The counter this phone's copy is at: a live update above it means something changed. */
  get cursor(): number {
    return this.#shopping.copy.cursor;
  }

  get loaded(): boolean {
    return this.#shopping.loaded;
  }

  /**
   * A tap on a staple chip or "+ List": adds the ingredient with Undo, or says it is on the
   * list already. Never removes anything.
   */
  async tap(food: {
    id: number;
    name: string;
    counted_as?: 'weight' | 'volume' | 'count';
    staple?: boolean;
  }) {
    if (this.#pending.has(food.id) || this.onList(food.id)) {
      toasts.show(`${food.name} is already on the shopping list.`);
      return;
    }
    if (!this.#shopping.list) {
      // The list hasn't arrived yet (a moment after opening, or never on this phone).
      await this.refresh();
      if (!this.#shopping.list) {
        toasts.show("Your shopping list isn't ready yet. Try again in a moment.", {
          tone: 'problem'
        });
        return;
      }
      if (this.onList(food.id)) {
        toasts.show(`${food.name} is already on the shopping list.`);
        return;
      }
    }
    this.#pending.add(food.id);
    try {
      await this.#shopping.add(food, `${food.name} added to the shopping list`);
    } finally {
      this.#pending.delete(food.id);
    }
  }
}

/** The screen-reader words for the chip or button, as the spec words them. */
export const listLabel = (name: string, onList: boolean) =>
  onList ? `${name}, on the shopping list` : `Add ${name} to the shopping list`;
