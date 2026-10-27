import { describe, expect, it } from 'vitest';
import { staplesLine, usedIn } from './plan';

describe('the staples card’s words (docs/dev/words.md 21)', () => {
  it('names the recipes that use a staple', () => {
    expect(usedIn([])).toBe('');
    expect(usedIn(['Sambar'])).toBe('Sambar');
    expect(usedIn(['Dosa', 'Sambar'])).toBe('Dosa and Sambar');
    expect(usedIn(['Dosa', 'Sambar', 'Upma'])).toBe('Dosa, Sambar and Upma');
    expect(usedIn(['Dosa', 'Sambar', 'Upma', 'Idli', 'Pongal'])).toBe('Dosa, Sambar and 3 more');
  });

  it('adjusts the second line to the look-ahead', () => {
    expect(staplesLine(7)).toBe('Staples this week’s recipes use');
    expect(staplesLine(1)).toBe('Staples today’s recipes use');
    expect(staplesLine(10)).toBe('Staples the next 10 days’ recipes use');
    expect(staplesLine(null)).toBe('Staples your planned recipes use');
  });
});
