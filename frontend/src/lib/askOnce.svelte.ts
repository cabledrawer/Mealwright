// "Ask once" (spec, Foods and units): when the server needs a figure it doesn't know
// ("About how much does 1 cup of toor dal weigh?"), the app asks, with a "Remember for
// next time" switch, and sends the same change again with the answer (contract 4.4).
// AskOnce.svelte shows the question; save() waits for the answer.

import type { Answer, Ask } from './client/types';

interface Pending {
  ask: Ask;
  resolve: (answer: Answer | null) => void;
}

/** The answer the server expects for a question. */
export function answerFor(ask: Ask, value: number, remember: boolean): Answer {
  if (ask.kind === 'weight_per_ml' || ask.kind === 'item_weight') {
    return { kind: ask.kind, food_id: ask.food_id, grams: value, remember };
  }
  return { kind: 'size', food_id: ask.food_id, name: ask.name ?? ask.per ?? '', amount: value };
}

class AskOnce {
  current = $state<Pending | null>(null);

  /** Ask a question. Resolves with the answer, or null if the person chose not to. */
  ask(ask: Ask): Promise<Answer | null> {
    this.current?.resolve(null);
    return new Promise((resolve) => {
      this.current = { ask, resolve };
    });
  }

  answer(value: number, remember: boolean): void {
    const pending = this.current;
    if (!pending) return;
    this.current = null;
    pending.resolve(answerFor(pending.ask, value, remember));
  }

  dismiss(): void {
    const pending = this.current;
    this.current = null;
    pending?.resolve(null);
  }
}

export const askOnce = new AskOnce();
