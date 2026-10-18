import { describe, expect, it } from 'vitest';
import { addDays, addedWords, compactDateWords, dateWords, useByWords } from './dates';

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
