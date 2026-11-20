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
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory, undoneWords, type UndoEntry } from '#lib/undo.svelte.js';
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
    const already = () => this.#pending.has(food.id) || this.onList(food.id);
    const say = () => toasts.show(`${food.name} is already on the shopping list.`);
    if (already()) return say();
    // This tap is under way from here on, so a second tap in the next moments (while the
    // list arrives, or the add goes into the waiting list) is "already on the list".
    this.#pending.add(food.id);
    try {
      if (!this.#shopping.list) {
        // The list hasn't arrived yet (a moment after opening, or never on this phone).
        await this.refresh();
        if (!this.#shopping.list) {
          toasts.problem(
            'Your shopping list isn’t ready yet. Try again in a moment.',
            () => void this.tap(food)
          );
          return;
        }
        if (this.onList(food.id)) return say();
      }
      await this.#shopping.add(food, `${food.name} added to the shopping list`);
    } finally {
      this.#pending.delete(food.id);
    }
  }

  /**
   * Several ingredients at once (a recipe's missing ones): each goes through the same add
   * action and waiting list as one tap, so what is queued is exactly what adding them by hand
   * sends. Only the toast is shared: "3 ingredients added to the shopping list", with one Undo
   * (and Ctrl+Z) that takes them all back. Ones already on the list are left alone.
   */
  async tapMany(foods: { id: number; name: string; counted_as?: 'weight' | 'volume' | 'count' }[]) {
    const fresh = foods.filter((f) => !this.#pending.has(f.id) && !this.onList(f.id));
    if (fresh.length <= 1) {
      if (fresh[0]) return this.tap(fresh[0]);
      return;
    }
    for (const food of fresh) this.#pending.add(food.id);
    try {
      if (!this.#shopping.list) {
        await this.refresh();
        if (!this.#shopping.list) {
          toasts.problem(
            'Your shopping list isn’t ready yet. Try again in a moment.',
            () => void this.tapMany(foods)
          );
          return;
        }
      }
      const added: { id: string; name: string }[] = [];
      const wording = () =>
        added.length === 1
          ? `${added[0]!.name} added to the shopping list`
          : `${added.length} ingredients added to the shopping list`;
      // The group's one Undo entry (on the list once everything is in the queue), and whether
      // a refusal came before that.
      let recorded = false;
      let refusal = false;
      const group: UndoEntry = {
        label: '',
        // Newest first, each as an `undo` action queued after its add (works offline too).
        undo: async () => {
          const label = group.label;
          for (const one of [...added].reverse()) {
            await this.#shopping.undo(one.id, `${one.name} added to the shopping list`);
          }
          toasts.show(undoneWords(label));
          return false as const;
        }
      };
      for (const food of fresh) {
        if (this.onList(food.id)) continue; // it arrived while the list was loading
        let inQueue!: () => void;
        const queued = new Promise<void>((resolve) => (inQueue = resolve));
        const mine = { id: '', name: food.name };
        const done = this.#shopping.add(food, `${food.name} added to the shopping list`, {
          queued: (id) => {
            mine.id = id;
            added.push(mine);
            inQueue();
          }
        });
        // A refusal (its reason is already on the screen) takes that add out of the group, the
        // way a single add forgets its own Undo: nothing is left to undo for it.
        void done.then((outcome) => {
          if (outcome?.ok !== false) return;
          const at = added.indexOf(mine);
          if (at === -1) return;
          added.splice(at, 1);
          refusal = true;
          if (!recorded) return;
          if (added.length === 0) undoHistory.forget(group);
          else group.label = wording();
        });
        // In the queue (the same moment a single add shows its toast), or refused.
        await Promise.race([queued, done]);
      }
      if (added.length === 0) return;
      group.label = wording();
      recorded = true;
      // Something was refused while the rest went in: that message stays on the screen (Undo
      // is still there, with Ctrl+Z). Otherwise one toast says how many were added.
      undoHistory.record(group, { toast: !refusal });
    } finally {
      for (const food of fresh) this.#pending.delete(food.id);
    }
  }
}

/** The screen-reader words for the chip or button, as the spec words them. */
export const listLabel = (name: string, onList: boolean) =>
  onList ? `${name}, on the shopping list` : `Add ${name} to the shopping list`;
