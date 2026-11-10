import { describe, expect, it } from 'vitest';
import { stepGroups } from './recipePage.svelte';

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
