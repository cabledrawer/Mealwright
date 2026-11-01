import { describe, expect, it } from 'vitest';
import { sentenceCount, sentences, splitStep, stepRuns } from './importSteps';

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

describe('the method in runs (F112)', () => {
  it('numbers the steps through the method and never counts a heading', () => {
    const runs = stepRuns([
      { kind: 'step', text: 'a' },
      { kind: 'heading', text: 'For the dosa' },
      { kind: 'step', text: 'b' },
      { kind: 'step', text: 'c' },
      { kind: 'heading', text: 'To serve' },
      { kind: 'step', text: 'd' }
    ]);
    expect(runs.map((r) => [r.heading?.text ?? null, r.start, r.steps.length])).toEqual([
      [null, 1, 1],
      ['For the dosa', 2, 2],
      ['To serve', 4, 1]
    ]);
  });

  it('keeps each item’s place in the full list, for the split buttons', () => {
    const runs = stepRuns([
      { kind: 'heading', text: 'H' },
      { kind: 'step', text: 'a' },
      { kind: 'step', text: 'b' }
    ]);
    expect(runs[0]!.heading!.at).toBe(0);
    expect(runs[0]!.steps.map((s) => s.at)).toEqual([1, 2]);
  });

  it('has a run for a heading with nothing under it', () => {
    expect(stepRuns([{ kind: 'heading', text: 'H' }])).toEqual([
      { heading: { text: 'H', at: 0 }, start: 1, steps: [] }
    ]);
  });
});
