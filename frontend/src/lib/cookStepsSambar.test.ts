import { describe, expect, it } from 'vitest';
import type { RecipeLine } from './client/recipes';
import { cookSteps, sharedLineIds, stepLines, type StepIn } from './cookSteps';

// F142 (cabledrawer 3 Nov; hand test of 0.7.0-beta.1, Swasthi's Sambar): the guesses for "Ingredients
// for each step" didn't help. The lines and steps below are Sambar's, as written for the test: the
// importer's lines (words, then the ingredient each is linked to) and the method's steps in order.

const line = (
  id: number,
  words: string,
  food: string,
  extra: Partial<RecipeLine> = {}
): RecipeLine => ({
  id,
  kind: 'ingredient',
  words,
  amount: null,
  amount_text: null,
  unit: null,
  size: null,
  food: { id: id + 100, name: food, other_names: [] },
  recipe: null,
  link: 'ingredient',
  note: null,
  ...extra
});

const SAMBAR_LINES: RecipeLine[] = [
  line(1, 'toor dal', 'Toor dal', { amount: 0.75, amount_text: '¾', unit: 'cup' }),
  line(2, 'water', 'Water', { amount: 2, amount_text: '2', unit: 'cup' }),
  line(3, 'tamarind', 'Tamarind'),
  line(4, 'coriander seeds', 'Coriander seeds', { amount: 2, amount_text: '2', unit: 'tbsp' }),
  line(5, 'dried red chilies', 'Red chilli'),
  line(6, 'coriander leaves', 'Coriander', { amount: 2, amount_text: '2', unit: 'tbsp' }),
  line(7, 'curry leaves', 'Curry leaves'),
  line(8, 'mustard seeds', 'Mustard seeds'),
  line(9, 'oil', 'Oil')
];

const step = (text: string): StepIn => ({ kind: 'step', text });
const SAMBAR_STEPS: StepIn[] = [
  step('Rinse the toor dal and pressure cook it with 2 cups water and turmeric for 3 whistles.'),
  step('Soak the tamarind in warm water.'),
  step('Dry roast the coriander seeds, fenugreek seeds and red chillies until fragrant.'),
  step('Grind the roasted spices with the coconut and a little water to a smooth paste.'),
  step('Heat oil and fry the mustard seeds, the red chillies and curry leaves.'),
  step('Add the vegetables and the tamarind water. Boil in 2 cups water until soft.'),
  step('Add the mashed dal and the ground paste with 2 cups of water. Simmer.'),
  step('Finish with the coriander leaves.')
];

const guessed = (n: number) =>
  stepLines(cookSteps(SAMBAR_STEPS)[n - 1]!, SAMBAR_LINES).map((l) => l.id);

describe('F142: Sambar’s per-step guesses', () => {
  it('(a) seeds and leaves of one plant are different: the leaves are not on the seeds step', () => {
    expect(guessed(3)).toContain(4);
    expect(guessed(3)).not.toContain(6);
    expect(guessed(8)).toEqual([6]);
  });

  it('(a) a step that says only the plant still finds it', () => {
    const lines = [line(6, 'coriander leaves', 'Coriander')];
    const only = cookSteps([step('Chop the coriander finely.')])[0]!;
    expect(stepLines(only, lines).map((l) => l.id)).toEqual([6]);
  });

  it('(b) a liquid used across several steps is not shown at its full amount on each', () => {
    const steps = cookSteps(SAMBAR_STEPS);
    const shared = sharedLineIds(steps, SAMBAR_LINES);
    expect(shared.has(2)).toBe(true); // water: steps 1, 4, 6, 7
    expect(shared.has(1)).toBe(false); // toor dal: step 1 only
    expect(shared.has(6)).toBe(false); // coriander leaves: the last step only
  });

  it('(c) an ingredient named in the step is found, however it was spelt or described', () => {
    expect(guessed(3)).toContain(5); // "dried red chilies" on the step that says "red chillies"
    expect(guessed(5)).toContain(5);
    expect(guessed(5)).toContain(7);
    expect(guessed(5)).toContain(8);
    expect(guessed(5)).toContain(9);
  });
});
