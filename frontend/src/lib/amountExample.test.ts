import { describe, expect, it } from 'vitest';
import { amountExample } from './amountExample';

describe('the example in the Amount box', () => {
  it('suits the unit', () => {
    expect(amountExample('g', false)).toBe('200');
    expect(amountExample('kg', false)).toBe('1');
    expect(amountExample('ml', false)).toBe('250');
    expect(amountExample('l', false)).toBe('1');
  });

  it('is a small number of items for eggs and the like', () => {
    expect(amountExample('items', false)).toBe('6');
    expect(amountExample('eggs', false)).toBe('6');
  });

  it('is 1 for a size such as a packet or a dozen', () => {
    expect(amountExample('packet', true)).toBe('1');
    expect(amountExample('dozen', true)).toBe('1');
  });
});
