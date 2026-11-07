import { describe, expect, it } from 'vitest';
import { tooLateToFreeze } from './tooLateToFreeze';

describe('tooLateToFreeze', () => {
  it('is false the day before and on the Use by day itself', () => {
    expect(tooLateToFreeze('use_by', 1)).toBe(false);
    expect(tooLateToFreeze('use_by', 0)).toBe(false);
  });

  it('is true from the day after a Use by date', () => {
    expect(tooLateToFreeze('use_by', -1)).toBe(true);
    expect(tooLateToFreeze('use_by', -30)).toBe(true);
  });

  it('is never true for Best before food, or with no date', () => {
    expect(tooLateToFreeze('best_before', -30)).toBe(false);
    expect(tooLateToFreeze('use_by', null)).toBe(false);
  });
});
