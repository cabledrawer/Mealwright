import { describe, expect, it } from 'vitest';
import { NBSP, nothingMatches, plural } from './words';

describe('words helpers (FE32)', () => {
  it('has one no-break space, written as an escape', () => {
    expect(NBSP).toBe('\u00a0');
    expect(NBSP).not.toBe(' ');
  });
  it('picks singular only for exactly one', () => {
    expect(plural(1, 'tub', 'tubs')).toBe('tub');
    expect([0, 2, 5, 1.5].map((n) => plural(n, 'tub', 'tubs'))).toEqual(Array(4).fill('tubs'));
  });
});

describe('nothingMatches (FE7)', () => {
  it('says what was typed, trimmed, in the one pattern', () => {
    expect(nothingMatches('recipe', ' dal ')).toBe('No recipe matches “dal”.');
    expect(nothingMatches('ingredient', 'zzz')).toBe('No ingredient matches “zzz”.');
  });
});
