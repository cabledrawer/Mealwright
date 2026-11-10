import { describe, expect, it } from 'vitest';
import { baseText, packText, pantryGets, partText } from './format';

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
  it('says a part of an amount to two figures (F183: not 62.5 g)', () => {
    expect(partText(62.5, 'weight')).toBe('about\u00a063\u00a0g');
    expect(partText(125, 'weight')).toBe('about\u00a0130\u00a0g');
    expect(partText(100, 'weight')).toBe('100\u00a0g');
    expect(partText(300, 'volume')).toBe('300\u00a0ml');
    expect(partText(1.5, 'count')).toBe('1.5');
  });
});
