// "Pantry keeps it by" (sync-protocol 16.2, spec L304): asked once when a typed name is a
// brand-new ingredient, from the Shopping add box and from the Ingredients "New ingredient"
// button. NewIngredient.svelte shows it; callers wait for the answer.

import type { Component } from 'svelte';
import { ApiError, forgetAtSignOut } from './api';
import { newChangeId } from './changeId';
import { addSize, createFood, getFood } from './client/foods';
import type { CountedAs, Ref } from './client/types';
import { kitchen } from './freshness.svelte';
import { couldntOpen } from './lazyCode.svelte';
import { toasts } from './toast.svelte';

export type HowCounted = CountedAs | 'staple';

export interface Made extends Ref {
  counted_as: CountedAs;
  staple: boolean;
}

/** A packet size to make along with the ingredient: "packet = 500 g". */
export interface NewSize {
  name: string;
  amount: number;
  unit: string;
}

/** What the person chose, before anything is made (the Shopping add box sends it as `add`). */
export interface Chosen {
  name: string;
  counted_as: CountedAs;
  staple: boolean;
  /** Packet sizes to add afterwards, as a separate online step. */
  sizes: NewSize[];
}

interface Pending {
  /** The name typed already, or empty when the dialog should ask for it. */
  name: string;
  /** make: the dialog makes the ingredient (Ingredients). choose: it only asks (Shopping). */
  mode: 'make' | 'choose';
  /** How the typed amount counts it ("1 l" is by volume): the dialog starts there. */
  hint: CountedAs | null;
  resolve: (answer: Made | Chosen | null) => void;
}

/** Add the packet sizes chosen in the dialog to an ingredient that now exists (online only). */
export async function addChosenSizes(foodId: number, sizes: NewSize[]): Promise<void> {
  for (const size of sizes) {
    try {
      await addSize(
        foodId,
        { name: size.name, amount: { amount: size.amount, unit: size.unit } },
        newChangeId()
      );
    } catch {
      toasts.problem(`Couldn’t add the ${size.name} size. You can add it in Ingredients.`);
    }
  }
}

class NewIngredientFlow {
  current = $state<Pending | null>(null);
  /** The dialog's code, once wanted (asked, or warmed when the page is idle); kept (size limit). */
  code = $state.raw<Promise<Component | null> | null>(null);
  /** Where the code comes from; a test swaps it. */
  loader: () => Promise<{ default: Component }> = () => import('./components/NewIngredient.svelte');

  get wanted(): boolean {
    return this.code !== null;
  }

  /**
   * Fetch the dialog's code now, without opening it (the app layout does this once the page is
   * idle), so asking offline works where the network layer blocks a first-use fetch.
   */
  warm() {
    this.#fetch();
  }

  /**
   * Starts fetching the code unless it is already on its way or here. A failed fetch is
   * forgotten, so the next ask fetches again; an ask waiting at that moment is answered as
   * Cancel (null) with a toast, never left hanging. A failed warm-up is forgotten quietly.
   */
  #fetch() {
    if (this.code) return;
    const code: Promise<Component | null> = this.loader().then(
      (module) => module.default,
      () => {
        if (this.code === code) this.code = null;
        const waiting = this.current;
        if (waiting) {
          this.current = null;
          waiting.resolve(null);
          couldntOpen(() => this.#fetch());
        }
        return null;
      }
    );
    this.code = code;
  }

  /** Open the dialog. Resolves with the ingredient once it exists, or null if cancelled. */
  ask(name = ''): Promise<Made | null> {
    return this.#open(name, 'make') as Promise<Made | null>;
  }

  /** Open the dialog only to ask: nothing is made until the caller sends it. */
  choose(name: string, hint: CountedAs | null = null): Promise<Chosen | null> {
    return this.#open(name, 'choose', hint) as Promise<Chosen | null>;
  }

  #open(
    name: string,
    mode: Pending['mode'],
    hint: CountedAs | null = null
  ): Promise<Made | Chosen | null> {
    this.current?.resolve(null);
    const asked = new Promise<Made | Chosen | null>((resolve) => {
      this.current = { name: name.trim(), mode, hint, resolve };
    });
    this.#fetch();
    return asked;
  }

  /** "choose" mode: hand the answer back. */
  pick(chosen: Chosen): void {
    const pending = this.current;
    this.current = null;
    pending?.resolve(chosen);
  }

  cancel(): void {
    const pending = this.current;
    this.current = null;
    pending?.resolve(null);
  }

  /**
   * Make the ingredient with the chosen way of counting, then its sizes. Throws an ApiError
   * with the server's reason if the ingredient itself can't be made. A name someone already
   * uses gives that ingredient back.
   */
  async make(name: string, how: HowCounted, sizes: NewSize[]): Promise<void> {
    const pending = this.current;
    if (!pending) return;
    const staple = how === 'staple';
    let made: Made;
    try {
      const result = await createFood(
        { name, staple, ...(staple ? {} : { counted_as: how }) },
        newChangeId()
      );
      made = {
        id: result.food.id,
        name: result.food.name,
        counted_as: result.food.counted_as,
        staple: result.food.staple
      };
      if (!staple) await addChosenSizes(made.id, sizes);
    } catch (error) {
      const existing =
        error instanceof ApiError && error.code === 'name_taken'
          ? (error.body as { food_id?: number } | null)?.food_id
          : undefined;
      if (!existing) throw error;
      const real = await getFood(existing);
      made = { id: existing, name: real.name, counted_as: real.counted_as, staple: real.staple };
    }
    kitchen.changed();
    this.current = null;
    pending.resolve(made);
  }
}

export const newIngredient = new NewIngredientFlow();
forgetAtSignOut(() => newIngredient.cancel());
