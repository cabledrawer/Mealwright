// The Finish setup ring (cabledrawer 13 Nov, option A): filled in proportion to the steps done.

import { describe, expect, it } from 'vitest';
import { peopleWhoCount, ringArc, ringWords, SETUP_STEPS, stepsDone } from './finishRing.js';

describe('the Finish setup ring', () => {
  it('has five steps, and says "N of 5" from the count', () => {
    expect(SETUP_STEPS).toHaveLength(5);
    expect(ringWords(0)).toBe('0 of 5');
    expect(ringWords(2)).toBe('2 of 5');
    expect(ringWords(4)).toBe('4 of 5');
    expect(ringWords(1, 3)).toBe('1 of 3');
  });

  it('draws no arc at 0 of 5 (a round cap would show a stray dot)', () => {
    expect(ringArc(0)).toBeNull();
  });

  it('runs 144 degrees clockwise from the top at 2 of 5', () => {
    // sin 144 = 0.588, cos 144 = -0.809: x = 12 + 8.5 * 0.588, y = 12 + 8.5 * 0.809.
    expect(ringArc(2)).toBe('M12 3.5A8.5 8.5 0 0 1 17.00 18.88');
  });

  it('runs the long way round (large-arc flag) once past half, at 4 of 5', () => {
    // sin 288 = -0.951, cos 288 = 0.309: x = 12 - 8.5 * 0.951, y = 12 - 8.5 * 0.309.
    expect(ringArc(4)).toBe('M12 3.5A8.5 8.5 0 1 1 3.92 9.37');
  });

  it('is the whole ring at all five, and never past it', () => {
    expect(ringArc(5)).toBe('M12 3.5A8.5 8.5 0 0 1 12 20.5A8.5 8.5 0 0 1 12 3.5');
    expect(ringArc(9)).toBe(ringArc(5));
  });

  it('counts the account, a household of more than one and a shop; what is unread counts as not done', () => {
    expect(stepsDone({ people: null, shops: null })).toBe(1);
    expect(stepsDone({ people: 1, shops: 0 })).toBe(1);
    expect(stepsDone({ people: 3, shops: 0 })).toBe(2);
    expect(stepsDone({ people: 1, shops: 2 })).toBe(2);
    expect(stepsDone({ people: 2, shops: 1 })).toBe(3);
  });

  it('does not count a shared login as a person who eats', () => {
    const lorna = { login: { shared: false } };
    const tablet = { login: { shared: true } };
    const sam = { login: null };
    expect(peopleWhoCount([lorna, tablet])).toBe(1);
    expect(peopleWhoCount([lorna, sam, tablet])).toBe(2);
    expect(stepsDone({ people: peopleWhoCount([lorna, tablet]), shops: 0 })).toBe(1);
  });
});
