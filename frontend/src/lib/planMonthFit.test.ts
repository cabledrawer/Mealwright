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
    // 3 + 22 + 3 chips (76) + 26 for "+N more" + 3 = 130; two chips need 104, one needs 78
    expect(chipsThatFit(130, 5)).toBe(3);
    expect(chipsThatFit(129, 5)).toBe(2);
    expect(chipsThatFit(104, 5)).toBe(2);
    expect(chipsThatFit(103, 5)).toBe(1);
    expect(chipsThatFit(78, 5)).toBe(1);
    expect(chipsThatFit(77, 5)).toBe(0);
  });

  it('needs no "+N more" row when everything fits', () => {
    // three chips and nothing else: 3 + 22 + 76 + 3 = 104
    expect(chipsThatFit(104, 3)).toBe(3);
    // one short: three do not fit, so "+N more" is needed, and two chips with it need 104
    expect(chipsThatFit(103, 3)).toBe(1);
  });

  it('never shows more than three, and grows with the text size', () => {
    expect(chipsThatFit(500, 9)).toBe(3);
    expect(chipsThatFit(130, 5, 2)).toBe(0);
    expect(chipsThatFit(260, 5, 2)).toBe(3);
  });
});
