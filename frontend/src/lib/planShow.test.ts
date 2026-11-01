import { afterEach, describe, expect, it, vi } from 'vitest';
import { defaultShow, keepShow, readShow, SHOW_KEY } from './planShow';

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('the Plan switch', () => {
  it('opens on Eat on a phone and on Both on a computer', () => {
    expect(defaultShow(true)).toBe('eat');
    expect(defaultShow(false)).toBe('both');
    expect(readShow(true)).toBe('eat');
    expect(readShow(false)).toBe('both');
  });

  it('keeps the choice on this device, whatever the width', () => {
    keepShow('cook');
    expect(localStorage.getItem(SHOW_KEY)).toBe('cook');
    expect(readShow(true)).toBe('cook');
    expect(readShow(false)).toBe('cook');
  });

  it('ignores a kept value it does not know', () => {
    localStorage.setItem(SHOW_KEY, 'everything');
    expect(readShow(true)).toBe('eat');
    expect(readShow(false)).toBe('both');
  });

  it('falls back to the layout’s own when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readShow(true)).toBe('eat');
    expect(readShow(false)).toBe('both');
    expect(() => keepShow('eat')).not.toThrow();
  });
});
