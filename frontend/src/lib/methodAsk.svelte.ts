// "Which way will you cook it?" (M2, cabledrawer 9 Nov: "adding a recipe with two methods to the plan
// asks which one (the one used last is pre-picked)"). A recipe with two ways of cooking it asks
// before it is added to the plan, and again from its meal when the person wants to change it.
// PlanMethod.svelte shows the question; this holds it. Online only, like the rest of the Plan.

import { forgetAtSignOut } from './api';
import { getRecipe, type RecipeMethodRef } from './client/recipes';
import { optionalAsk } from './optionalAsk.svelte';

export interface MethodQuestion {
  recipeName: string;
  /** "Sat dinner". */
  where: string;
  methods: RecipeMethodRef[];
  /** The one ticked to begin with: the meal's own, else the one used last, else the first. */
  picked: number;
  /** The main button: "Add to plan", or "Save" when the meal's way is being changed. */
  button: string;
}

interface Pending {
  question: MethodQuestion;
  resolve: (id: number | null) => void;
}

class MethodAsk {
  current = $state<Pending | null>(null);

  /**
   * Ask which way of cooking the recipe the meal will use. Resolves with the method's id, null
   * when the person cancels, and undefined when there is nothing to ask: the recipe has one way
   * (or can't be read, and adding it goes on as it always did).
   * `methodCount` is the number the caller already knows (1: no question, nothing is fetched).
   */
  async ask(
    recipe: { id: number; methodCount?: number },
    where: string,
    options: { current?: number | null; button?: string } = {}
  ): Promise<number | null | undefined> {
    if (recipe.methodCount === 1) return undefined;
    let methods: RecipeMethodRef[];
    let name: string;
    try {
      const found = await getRecipe(recipe.id);
      methods = found.methods ?? [];
      name = found.name;
    } catch {
      return undefined;
    }
    if (methods.length < 2) return undefined;
    this.current?.resolve(null);
    optionalAsk.methodOpen = true;
    const picked =
      methods.find((m) => m.id === options.current)?.id ??
      methods.find((m) => m.used_last)?.id ??
      methods[0]!.id;
    return new Promise((resolve) => {
      this.current = {
        question: {
          recipeName: name,
          where,
          methods,
          picked,
          button: options.button ?? 'Add to plan'
        },
        resolve
      };
    });
  }

  answer(id: number): void {
    const pending = this.current;
    this.current = null;
    optionalAsk.methodOpen = false;
    pending?.resolve(id);
  }

  dismiss(): void {
    const pending = this.current;
    this.current = null;
    optionalAsk.methodOpen = false;
    pending?.resolve(null);
  }
}

export const methodAsk = new MethodAsk();
forgetAtSignOut(() => methodAsk.dismiss());
