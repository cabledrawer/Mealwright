import { describe, expect, it } from 'vitest';
import {
  addDays,
  addedWords,
  boughtWords,
  compactDateWords,
  dateWords,
  pickedDateWords,
  useByWords,
  whenWords
} from './dates';

describe('use-by dates in plain words', () => {
  // 17 Oct 2026 is a Saturday.
  it('reads today, tomorrow, this week and later', () => {
    expect(dateWords('2026-10-17', 0)).toBe('Today');
    expect(dateWords('2026-10-18', 1)).toBe('Tomorrow');
    expect(dateWords('2026-10-19', 2)).toBe('Mon');
    expect(dateWords('2026-10-23', 6)).toBe('Fri');
    expect(dateWords('2026-11-12', 26)).toBe('12 Nov');
    expect(dateWords('2026-10-15', -2)).toBe('Date passed');
    expect(dateWords(null, null)).toBe('');
  });

  it('the phone Use soon card keeps the capital on day names', () => {
    expect(compactDateWords('2026-10-19', 2)).toBe('Mon'); // not "mon"
    expect(compactDateWords('2026-11-12', 26)).toBe('12 Nov');
    // Today and tomorrow take a capital here, like the Today chip; mid-sentence they don't.
    expect(compactDateWords('2026-10-17', 0)).toBe('Today');
    expect(compactDateWords('2026-10-18', 1)).toBe('Tomorrow');
    expect(useByWords('2026-10-17', 0)).toBe('use by today');
    expect(useByWords('2026-10-18', 1)).toBe('use by tomorrow');
    expect(addedWords('2026-10-17', '2026-10-17')).toBe('added today');
    expect(compactDateWords(null, null)).toBe('');
  });

  it('writes a chosen date as weekday, day and month', () => {
    expect(pickedDateWords('2026-10-24')).toBe('Sat 24 Oct');
    expect(pickedDateWords('2027-01-05')).toBe('Tue 5 Jan');
  });

  it('makes "use by …" phrases', () => {
    expect(useByWords('2026-10-19', 2)).toBe('use by Mon');
    expect(useByWords('2026-10-17', 0)).toBe('use by today');
    expect(useByWords(null, null)).toBe('no use-by date');
  });

  it('adds days across months and the clock change', () => {
    expect(addDays('2026-10-17', 3)).toBe('2026-10-20');
    expect(addDays('2026-10-24', 7)).toBe('2026-10-31');
    expect(addDays('2026-10-30', 3)).toBe('2026-11-02');
  });

  it('says when something was added', () => {
    expect(addedWords('2026-10-17', '2026-10-17')).toBe('added today');
    expect(addedWords('2026-10-16', '2026-10-17')).toBe('added yesterday');
    expect(addedWords('2026-10-03', '2026-10-17')).toBe('added 3 Oct');
  });
});

describe('boughtWords (a pantry row with no use-by, cabledrawer 20 Oct)', () => {
  it('says when the stock went in, in the words of the mockup', () => {
    expect(boughtWords('2026-10-20', '2026-10-24')).toBe('bought Tue');
    expect(boughtWords('2026-10-24', '2026-10-24')).toBe('bought today');
    expect(boughtWords('2026-10-23', '2026-10-24')).toBe('bought yesterday');
    expect(boughtWords('2026-10-03', '2026-10-24')).toBe('bought 3 Oct');
  });
});

describe('Use by and Best before words (0.8, cabledrawer 7 Nov)', () => {
  it('a passed Use by says don’t eat, never probably fine, and how long ago', () => {
    const w = whenWords('use_by', '2026-10-14', -3);
    expect(w).toEqual({
      text: 'Use by passed: don’t eat',
      ago: 'Passed 3 days ago',
      tone: 'late',
      passed: true
    });
    expect(whenWords('use_by', '2026-10-16', -1).ago).toBe('Passed yesterday');
  });

  it('a passed Best before says probably fine', () => {
    const w = whenWords('best_before', '2026-10-14', -3);
    expect(w.text).toBe('Best before passed · probably fine');
    expect(w.tone).toBe('bb');
  });

  it('a date to come reads use by or best before, with or without a capital', () => {
    expect(whenWords('use_by', '2026-10-19', 2, { capital: true }).text).toBe('Use by Mon');
    expect(whenWords('use_by', '2026-10-19', 2).text).toBe('use by Mon');
    expect(whenWords('use_by', '2026-10-17', 0, { capital: true }).text).toBe('Use by today');
    expect(whenWords('best_before', '2026-11-12', 26).text).toBe('best before 12 Nov');
    expect(whenWords('use_by', '2026-10-19', 2, { soon: true }).tone).toBe('soon');
    expect(whenWords('use_by', null, null).text).toBe('');
  });
});
