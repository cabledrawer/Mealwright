import { describe, expect, it } from 'vitest';
import { chipsThatFit } from './planMonthFit';

describe('chipsThatFit (F47)', () => {
  it('shows what is there when the day is not measured yet', () => {
    expect(chipsThatFit(0, 5)).toBe(3);
    expect(chipsThatFit(0, 2)).toBe(2);
    expect(chipsThatFit(0, 0)).toBe(0);
  });

  it('shows up to three, then "+N more", in a roomy day', () => {
    expect(chipsThatFit(130, 5)).toBe(3);
    expect(chipsThatFit(130, 4)).toBe(3);
    expect(chipsThatFit(130, 3)).toBe(3);
    expect(chipsThatFit(130, 1)).toBe(1);
  });

  it('shows fewer in a short day, and keeps room for "+N more"', () => {
    // 4 + 20 + 3 chips (58) + 17 for "+N more" + 4 = 103; two chips need 83, one needs 63
    expect(chipsThatFit(103, 5)).toBe(3);
    expect(chipsThatFit(102, 5)).toBe(2);
    expect(chipsThatFit(83, 5)).toBe(2);
    expect(chipsThatFit(82, 5)).toBe(1);
    expect(chipsThatFit(63, 5)).toBe(1);
    expect(chipsThatFit(62, 5)).toBe(0);
  });

  it('needs no "+N more" row when everything fits', () => {
    // three chips (58) and nothing else: 4 + 20 + 58 + 4 = 86
    expect(chipsThatFit(86, 3)).toBe(3);
    expect(chipsThatFit(85, 3)).toBe(2);
  });

  it('never shows more than three, and grows with the text size', () => {
    expect(chipsThatFit(500, 9)).toBe(3);
    expect(chipsThatFit(103, 5, 2)).toBe(0);
    expect(chipsThatFit(206, 5, 2)).toBe(3);
  });
});
