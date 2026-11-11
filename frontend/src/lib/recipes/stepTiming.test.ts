import { describe, expect, it } from 'vitest';
import type { RecipeOut } from '#lib/client/recipes.js';
import { blankStep } from './draft.svelte.js';
import {
  equipmentWords,
  guessAgain,
  handsWords,
  minutesFrom,
  shownTiming,
  takeAsYours
} from './stepTiming.js';

const guessed = (text = 'Pressure cook the dal for 3 whistles.') => {
  const step = blankStep();
  step.text = text;
  step.guess = {
    hands: 'waiting',
    minutes: 15,
    equipment: 'pressure',
    hands_guessed: true,
    minutes_guessed: true,
    equipment_guessed: true
  };
  step.guessFor = text;
  return step;
};

describe('a step’s timing as the editor shows it', () => {
  it('shows the server’s guess as guessed', () => {
    const shown = shownTiming(guessed());
    expect(shown).toMatchObject({ hands: 'waiting', minutes: 15, equipment: 'pressure' });
    expect(shown.mark).toBe('guessed');
    expect(shown.pending).toBe(false);
    expect(handsWords(shown)).toBe('Waiting · 15 min');
    expect(equipmentWords(shown)).toBe('Pressure cooker');
  });

  it('knows nothing yet for a new step or one whose words changed, and says so', () => {
    expect(shownTiming(blankStep()).pending).toBe(true);
    const step = guessed();
    step.text = 'Boil the dal.';
    const shown = shownTiming(step);
    expect(shown.pending).toBe(true);
    expect(shown.hands).toBeNull();
    expect(handsWords(shown)).toBe('');
  });

  it('shows no equipment tag for Nothing, as the mockup does', () => {
    const step = guessed('Chop the onion.');
    step.guess = { ...step.guess!, hands: 'hands', minutes: 8, equipment: 'none' };
    expect(equipmentWords(shownTiming(step))).toBe('');
  });

  it('takes all three as the person’s on the first change, and keeps them when the words change', () => {
    const step = guessed();
    takeAsYours(step);
    expect(step.timing).toEqual({ hands: 'waiting', minutes: 15, equipment: 'pressure' });
    step.timing.minutes = 20;
    step.text = 'Boil the dal.';
    const shown = shownTiming(step);
    expect(shown.mark).toBe('set by you');
    expect(shown).toMatchObject({ hands: 'waiting', minutes: 20, equipment: 'pressure' });
    expect(shown.pending).toBe(false);
  });

  it('keeps only what the person set when nothing is guessed yet (B1 review r1 M3)', () => {
    const step = blankStep();
    step.text = 'Pressure cook the dal for 4 whistles.';
    takeAsYours(step);
    step.timing.minutes = 20;
    expect(step.timing).toEqual({ hands: null, minutes: 20, equipment: null });
    const shown = shownTiming(step);
    expect(shown.mark).toBe('partly guessed');
    expect(shown.pending).toBe(true);
  });

  it('keeps a value set by hand and leaves the unknown ones to the guess after the words change', () => {
    const step = guessed();
    step.timing = { hands: null, minutes: 30, equipment: null };
    step.text = 'Boil the dal.';
    takeAsYours(step);
    expect(step.timing).toEqual({ hands: null, minutes: 30, equipment: null });
  });

  it('puts the guess back with Guess again', () => {
    const step = guessed();
    takeAsYours(step);
    step.timing.minutes = 99;
    guessAgain(step);
    expect(shownTiming(step)).toMatchObject({ minutes: 15, mark: 'guessed' });
  });

  it('says partly guessed when only some were set by hand elsewhere', () => {
    const step = guessed();
    step.timing = { hands: null, minutes: 30, equipment: null };
    expect(shownTiming(step).mark).toBe('partly guessed');
  });

  it('reads whole minutes from 1 to 14,400 only', () => {
    expect(minutesFrom(' 12 ')).toBe(12);
    for (const bad of ['', '0', '14401', '1.5', '-3', 'ten', '1e3']) {
      expect(minutesFrom(bad)).toBeNull();
    }
  });

  it('keeps what the server says was set by hand when a recipe is opened', async () => {
    const { RecipeDraft } = await import('./draft.svelte.js');
    const draft = new RecipeDraft();
    const recipe = {
      id: 1,
      version: 1,
      name: 'Sambar',
      lines: [],
      tags: [],
      nutrition: {},
      steps: [
        {
          id: 1,
          kind: 'step',
          text: 'Chop the onion.',
          timing: {
            hands: 'hands',
            minutes: 8,
            equipment: 'none',
            hands_guessed: false,
            minutes_guessed: false,
            equipment_guessed: true
          }
        }
      ]
    } as unknown as RecipeOut;
    draft.load(recipe);
    expect(draft.steps[0]!.timing).toEqual({ hands: 'hands', minutes: 8, equipment: null });
    const built = draft.build();
    expect(built.body.steps[0]!.timing).toEqual({ hands: 'hands', minutes: 8, equipment: null });
  });
});
