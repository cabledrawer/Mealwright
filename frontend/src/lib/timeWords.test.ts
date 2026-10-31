import { describe, expect, it } from 'vitest';
import { timeWords } from './timeWords';

describe('timeWords', () => {
  it('keeps minutes up to the hour', () => {
    expect(timeWords(1)).toBe('1 min');
    expect(timeWords(50)).toBe('50 min');
    expect(timeWords(59)).toBe('59 min');
  });
  it('says 60 as one hour', () => {
    expect(timeWords(60)).toBe('1 h');
  });
  it('shows hours and minutes over the hour', () => {
    expect(timeWords(125)).toBe('2 h 5 min');
    expect(timeWords(745)).toBe('12 h 25 min');
    expect(timeWords(1440)).toBe('24 h');
  });
});
