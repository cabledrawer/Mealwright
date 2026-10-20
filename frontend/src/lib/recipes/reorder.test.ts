import { describe, expect, it } from 'vitest';
import { move } from './reorder';

describe('move', () => {
  it('puts one entry in a new place', () => {
    const list = ['a', 'b', 'c', 'd'];
    move(list, 0, 2);
    expect(list).toEqual(['b', 'c', 'a', 'd']);
    move(list, 3, 0);
    expect(list).toEqual(['d', 'b', 'c', 'a']);
  });

  it('does nothing off the ends or to the same place', () => {
    const list = ['a', 'b'];
    move(list, 0, 0);
    move(list, 0, -1);
    move(list, 1, 2);
    expect(list).toEqual(['a', 'b']);
  });
});
