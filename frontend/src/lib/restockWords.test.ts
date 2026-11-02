import { describe, expect, it } from 'vitest';
import { agoWords, chipWords, columnWords, fullDateWords } from './restockWords.js';

describe('how long ago a staple was restocked', () => {
  it('uses the biggest whole step', () => {
    expect(agoWords(0)).toBe('today');
    expect(agoWords(1)).toBe('yesterday');
    expect(agoWords(2)).toBe('2 days ago');
    expect(agoWords(6)).toBe('6 days ago');
    expect(agoWords(7)).toBe('1 week ago');
    expect(agoWords(21)).toBe('3 weeks ago');
    expect(agoWords(29)).toBe('4 weeks ago');
    expect(agoWords(30)).toBe('1 month ago');
    expect(agoWords(75)).toBe('2 months ago');
    expect(agoWords(364)).toBe('12 months ago');
    expect(agoWords(365)).toBe('1 year ago');
    expect(agoWords(800)).toBe('2 years ago');
  });

  it('never says a negative time', () => {
    expect(agoWords(-3)).toBe('today');
  });

  it('puts it on the column as "Restocked 3 weeks ago"', () => {
    expect(columnWords(21)).toBe('Restocked 3 weeks ago');
    expect(columnWords(0)).toBe('Restocked today');
  });

  it('puts the date on the pantry chip as "Restocked 12 Oct"', () => {
    expect(chipWords('2026-10-12', 21)).toBe('Restocked 12 Oct');
    expect(chipWords('2026-11-02', 0)).toBe('Restocked today');
  });

  it('gives the whole date for hover and tap', () => {
    expect(fullDateWords('2026-10-12')).toBe('12 Oct 2026');
  });
});
