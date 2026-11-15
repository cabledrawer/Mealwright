import { describe, expect, it } from 'vitest';
import { putAwayState, putAwayWords } from './putAway';

const milk = { amount: 2000, display: '2 L' };
const noAmount = { amount: null, display: null };
const bought = { bought: { amount: 2000, display: '2 L' } };

describe('putAwayState', () => {
  it('a line with an amount went into the pantry, in the amount the server counted', () => {
    expect(putAwayState(milk, { staple: false }, bought, false, 'Fridge')).toEqual({
      kind: 'amount',
      place: 'Fridge',
      amount: '2 L'
    });
  });
  it('a staple is restocked, whatever its amount', () => {
    expect(putAwayState(milk, { staple: true }, bought, false, 'Cupboard')).toEqual({
      kind: 'staple'
    });
  });
  it('a line with no amount put nothing in', () => {
    expect(putAwayState(noAmount, { staple: false }, { bought: null }, false, 'Cupboard')).toEqual({
      kind: 'none'
    });
  });
  it('a tick the server has not answered yet uses the line’s amount', () => {
    expect(putAwayState(milk, { staple: false }, { bought: null }, true, 'Fridge')).toEqual({
      kind: 'amount',
      place: 'Fridge',
      amount: '2 L'
    });
    expect(putAwayState(milk, { staple: false }, undefined, true, null)).toMatchObject({
      kind: 'amount',
      place: null
    });
  });
  it('an amount added after the tick does not claim the pantry got it', () => {
    expect(putAwayState(milk, { staple: false }, { bought: null }, false, 'Fridge')).toEqual({
      kind: 'none'
    });
  });
});

describe('putAwayWords', () => {
  it('says it the way cabledrawer worded it (20 Oct)', () => {
    expect(putAwayWords({ kind: 'amount', place: 'Fridge', amount: '2 L' })).toBe(
      'In the Fridge · 2 L'
    );
    expect(putAwayWords({ kind: 'none' })).toBe('Not in the pantry yet. No amount.');
    expect(putAwayWords({ kind: 'staple' })).toBe('Restocked · staples aren’t counted');
  });
  it('still reads well before the place is known', () => {
    expect(putAwayWords({ kind: 'amount', place: null, amount: '2' })).toBe('In the pantry · 2');
  });
});
