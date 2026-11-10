// "When will you start it?" (M3, F124; cabledrawer 31 Oct and 9 Nov, mockup PlanStart08): adding a
// recipe with a long wait (a step that waits four hours or more) asks when the wait will be
// started, with times worked out from the meal's usual time and the wait, and again from the
// meal when the person wants to change it. PlanStart.svelte shows the question; this holds it.
// What reads the server for the times loads when the question is first asked (the size limit).
// Online only, like the rest of the Plan.

import type { StartAt, StartOption } from './client/plan';
import { optionalAsk } from './optionalAsk.svelte';
import type { StepWait } from './timeWords';

export interface StartQuestion {
  recipeName: string;
  /** "Sat breakfast". */
  where: string;
  /** The meal's own day, and its usual time ("08:00"): a start has to be before them. */
  day: string;
  eatsAt: string;
  /** "Breakfast at 08:00". */
  eatsWords: string;
  wait: StepWait;
  options: StartOption[];
  /** The time the meal has now, when it is being changed. */
  current: StartAt | null;
  /** The main button: "Add to plan", or "Save" when the meal's time is being changed. */
  button: string;
}

interface Pending {
  question: StartQuestion;
  resolve: (start: StartAt | null) => void;
}

/** The shortest wait that is started ahead (the server's rule, kept in step with it). */
export const MIN_AHEAD_MINUTES = 240;

class StartAsk {
  current = $state<Pending | null>(null);

  /**
   * Ask when the recipe's long wait will be started. Resolves with the day and time, null when
   * the person cancels, and undefined when there is nothing to ask: the recipe has no long wait
   * (or the server can't be reached, and adding it goes on as it always did, with no time).
   * `known` is what the caller already knows of the recipe's waits: `null` or a short one with
   * one way of cooking it means nothing is fetched; left out, the server is asked.
   */
  async ask(
    recipe: { id: number; name: string; wait?: StepWait | null; method_count?: number },
    meal: { day: string; slotId: number; slotName: string },
    options: { method?: number | null; current?: StartAt | null; button?: string } = {}
  ): Promise<StartAt | null | undefined> {
    if (
      recipe.wait !== undefined &&
      (recipe.method_count ?? 1) <= 1 &&
      (recipe.wait === null || recipe.wait.max_minutes < MIN_AHEAD_MINUTES)
    ) {
      return undefined;
    }
    let found;
    try {
      const { getStartOptions } = await import('./client/plan');
      found = await getStartOptions(recipe.id, meal.day, meal.slotId, options.method);
    } catch {
      return undefined;
    }
    if (!found.wait) return undefined;
    this.current?.resolve(null);
    const { forMeal } = await import('./startWords');
    optionalAsk.startOpen = true;
    return new Promise((resolve) => {
      this.current = {
        question: {
          recipeName: recipe.name,
          where: forMeal(meal.day, meal.slotName),
          day: meal.day,
          eatsAt: found.eats_at,
          eatsWords: `${meal.slotName} at ${found.eats_at}`,
          wait: found.wait!,
          options: found.options,
          current: options.current ?? null,
          button: options.button ?? 'Add to plan'
        },
        resolve
      };
    });
  }

  answer(start: StartAt): void {
    const pending = this.current;
    this.current = null;
    optionalAsk.startOpen = false;
    pending?.resolve(start);
  }

  dismiss(): void {
    const pending = this.current;
    this.current = null;
    optionalAsk.startOpen = false;
    pending?.resolve(null);
  }
}

export const startAsk = new StartAsk();
