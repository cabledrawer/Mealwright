import { describe, expect, it } from 'vitest';
import { baseText, packText, pantryGets } from './format';

describe('amount words', () => {
  it('uses kg and L from 1000', () => {
    expect(baseText(400, 'weight')).toBe('400\u00a0g');
    expect(baseText(1000, 'weight')).toBe('1\u00a0kg');
    expect(baseText(1500, 'volume')).toBe('1.5\u00a0L');
    expect(baseText(6, 'count')).toBe('6');
  });
  it('words packs', () => {
    expect(packText(2, 200, 'weight')).toBe('2\u00a0×\u00a0200\u00a0g');
    expect(pantryGets(1, 400, 'weight')).toBe('Pantry gets 1 pack · 400\u00a0g.');
    expect(pantryGets(2, 200, 'weight')).toBe('Pantry gets 2 packs · 400\u00a0g.');
  });
});
