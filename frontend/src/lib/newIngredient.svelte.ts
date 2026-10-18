// "How do you count it?" (sync-protocol 16.2, spec L304): asked once when a typed name is a
// brand-new ingredient, from the Shopping add box and from the Ingredients "New ingredient"
// button. NewIngredient.svelte shows it; callers wait for the answer.

import { ApiError } from './api';
import { newChangeId } from './changeId';
import { addSize, createFood } from './client/foods';
import type { CountedAs, Ref } from './client/types';
import { kitchen } from './freshness.svelte';
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

interface Pending {
  /** The name typed already, or empty when the dialog should ask for it. */
  name: string;
  resolve: (made: Made | null) => void;
}

class NewIngredientFlow {
  current = $state<Pending | null>(null);

  /** Open the dialog. Resolves with the ingredient once it exists, or null if cancelled. */
  ask(name = ''): Promise<Made | null> {
    this.current?.resolve(null);
    return new Promise((resolve) => {
      this.current = { name: name.trim(), resolve };
    });
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
      for (const size of staple ? [] : sizes) {
        try {
          await addSize(
            made.id,
            { name: size.name, amount: { amount: size.amount, unit: size.unit } },
            newChangeId()
          );
        } catch {
          toasts.show(`Couldn’t add the ${size.name} size. You can add it in Ingredients.`, {
            tone: 'problem'
          });
        }
      }
    } catch (error) {
      const existing =
        error instanceof ApiError && error.code === 'name_taken'
          ? (error.body as { food_id?: number } | null)?.food_id
          : undefined;
      if (!existing) throw error;
      made = { id: existing, name, counted_as: 'weight', staple: false };
    }
    kitchen.changed();
    this.current = null;
    pending.resolve(made);
  }
}

export const newIngredient = new NewIngredientFlow();
