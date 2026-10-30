import { describe, expect, it } from 'vitest';
import { sentenceCount, sentences, splitStep } from './importSteps';

const LONG =
  'Beat the butter and sugar until pale. Add the eggs one at a time, beating well. Fold in the flour and baking powder. Divide between the tins. Level the tops.';

describe('splitting a long step', () => {
  it('finds the sentences', () => {
    expect(sentences(LONG)).toHaveLength(5);
    expect(sentenceCount(LONG)).toBe(5);
  });

  it('does not break inside numbers, abbreviations or lower-case continuations', () => {
    expect(sentences('Bake at 1.5 tsp. Of salt for 20 mins. Then rest. Serve. Enjoy.')).toEqual([
      'Bake at 1.5 tsp. Of salt for 20 mins.',
      'Then rest.',
      'Serve.',
      'Enjoy.'
    ]);
    expect(sentences('Stir well, then add 2 tbsp. sugar and mix.')).toHaveLength(1);
  });

  it('splits a long step into pieces of two sentences', () => {
    expect(splitStep(LONG)).toEqual([
      'Beat the butter and sugar until pale. Add the eggs one at a time, beating well.',
      'Fold in the flour and baking powder. Divide between the tins.',
      'Level the tops.'
    ]);
  });

  it('leaves a short step alone', () => {
    expect(splitStep('Boil the dal. Add the rest. Stir.')).toBeNull();
    expect(splitStep('Boil the dal.')).toBeNull();
  });
});
