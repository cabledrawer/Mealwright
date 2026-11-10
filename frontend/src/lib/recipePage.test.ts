import { describe, expect, it } from 'vitest';
import { RecipeView, stepGroups } from './recipePage.svelte';
import type { Recipe } from './client/recipes';

describe('the method in runs', () => {
  it('numbers steps through the headings and says which are Optional (R3)', () => {
    expect(
      stepGroups([
        { kind: 'step', text: 'Rub the mutton.' },
        { kind: 'step', text: 'Fry onions.', optional: true },
        { kind: 'heading', text: 'To serve' },
        { kind: 'step', text: 'Top it.' }
      ])
    ).toEqual([
      {
        heading: null,
        start: 1,
        steps: ['Rub the mutton.', 'Fry onions.'],
        optional: [false, true],
        waits: [null, null]
      },
      { heading: 'To serve', start: 3, steps: ['Top it.'], optional: [false], waits: [null] }
    ]);
  });
});

describe('two ways of cooking it (M2)', () => {
  const line = (id: number, words: string) =>
    ({ id, kind: 'ingredient', words, amount: null, amount_text: null, unit: null }) as never;
  const recipe = {
    id: 1,
    name: 'Chicken curry',
    time_minutes: 45,
    wait: null,
    lines: [line(1, 'water')],
    steps: [{ id: 1, kind: 'step', text: 'Simmer.' }],
    methods: [
      { id: 10, name: 'Stovetop', time_minutes: 45, used_last: false },
      { id: 11, name: 'Instant Pot', time_minutes: 30, used_last: true }
    ],
    second_method: {
      id: 11,
      name: 'Instant Pot',
      time_minutes: 30,
      used_last: true,
      wait: null,
      lines: [line(2, 'stock')],
      steps: [{ id: 2, kind: 'step', text: 'Pressure cook.' }]
    }
  } as unknown as Recipe;

  it('shows the first method until the other is picked, then its lines, steps and time', () => {
    const view = new RecipeView(1);
    view.full = recipe;
    expect(view.recipe?.lines.map((l) => l.words)).toEqual(['water']);
    expect(view.recipe?.time_minutes).toBe(45);
    view.methodId = 11;
    expect(view.recipe?.lines.map((l) => l.words)).toEqual(['stock']);
    expect(view.recipe?.steps.map((s) => s.text)).toEqual(['Pressure cook.']);
    expect(view.recipe?.time_minutes).toBe(30);
    view.methodId = 10;
    expect(view.recipe?.time_minutes).toBe(45);
  });
});
