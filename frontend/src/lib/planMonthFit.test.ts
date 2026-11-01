import { describe, expect, it } from 'vitest';
import { chipsThatFit } from './planMonthFit';

describe('chipsThatFit (F47)', () => {
  it('shows what is there when the day is not measured yet', () => {
    expect(chipsThatFit(0, 5)).toBe(3);
    expect(chipsThatFit(0, 2)).toBe(2);
    expect(chipsThatFit(0, 0)).toBe(0);
  });

  it('shows up to three, then "+N more", in a roomy day', () => {
    expect(chipsThatFit(160, 5)).toBe(3);
    expect(chipsThatFit(160, 4)).toBe(3);
    expect(chipsThatFit(160, 3)).toBe(3);
    expect(chipsThatFit(160, 1)).toBe(1);
  });

  it('shows fewer in a short day, and keeps room for "+N more"', () => {
    // 3 + 20 + 3 chips (76) + 26 for "+N more" + 3 = 128; two chips need 102, one needs 76
    expect(chipsThatFit(128, 5)).toBe(3);
    expect(chipsThatFit(127, 5)).toBe(2);
    expect(chipsThatFit(102, 5)).toBe(2);
    expect(chipsThatFit(101, 5)).toBe(1);
    expect(chipsThatFit(76, 5)).toBe(1);
    expect(chipsThatFit(75, 5)).toBe(0);
  });

  it('needs no "+N more" row when everything fits', () => {
    // three chips and nothing else: 3 + 20 + 76 + 3 = 102
    expect(chipsThatFit(102, 3)).toBe(3);
    expect(chipsThatFit(101, 3)).toBe(2);
  });

  it('never shows more than three, and grows with the text size', () => {
    expect(chipsThatFit(500, 9)).toBe(3);
    expect(chipsThatFit(128, 5, 2)).toBe(0);
    expect(chipsThatFit(256, 5, 2)).toBe(3);
  });
});
