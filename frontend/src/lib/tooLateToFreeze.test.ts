import { describe, expect, it } from 'vitest';
import { tooLateToFreeze, tubTooLateToFreeze } from './tooLateToFreeze';

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

describe('tubTooLateToFreeze (cabledrawer 8 Nov)', () => {
  it('works the day before and on the day itself, not from the day after', () => {
    expect(tubTooLateToFreeze('2026-11-03', '2026-11-02')).toBe(false);
    expect(tubTooLateToFreeze('2026-11-02', '2026-11-02')).toBe(false);
    expect(tubTooLateToFreeze('2026-11-01', '2026-11-02')).toBe(true);
  });

  it('is false while the household’s day is not known yet', () => {
    expect(tubTooLateToFreeze('2026-11-01', '')).toBe(false);
  });
});
