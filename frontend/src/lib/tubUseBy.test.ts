import { describe, expect, it } from 'vitest';
import { eatOnUntil, eatOnUpTo, leftoverUseBy, tubUseBy } from './tubUseBy';

// F128 (cabledrawer 3 Nov): ""Eat it on…" in Today's review only offers meals up to the tub's use-by."
const LIFE = { fridgeDays: 3, freezerMonths: 3 };
const at = (day: string) => ({ day, slotId: 3, label: day });

describe('a new tub’s use-by, as the server counts it', () => {
  it('fridge: the household’s days after the meal’s day', () => {
    expect(tubUseBy('fridge', '2026-11-02', LIFE)).toBe('2026-11-05');
  });

  it('freezer: the household’s months after it, kept inside a shorter month', () => {
    expect(tubUseBy('freezer', '2026-11-02', LIFE)).toBe('2027-02-02');
    expect(tubUseBy('freezer', '2026-11-30', LIFE)).toBe('2027-02-28');
    expect(tubUseBy('freezer', '2026-10-31', { fridgeDays: 3, freezerMonths: 4 })).toBe(
      '2027-02-28'
    );
  });

  it('both, for "Any left over?"; nothing when the household’s tub life is not known', () => {
    expect(leftoverUseBy('2026-11-02', LIFE)).toEqual({
      useByFridge: '2026-11-05',
      useByFreezer: '2027-02-02'
    });
    expect(leftoverUseBy('2026-11-02', null)).toEqual({});
    expect(leftoverUseBy('2026-11-02', { fridgeDays: 3, freezerMonths: 0 })).toEqual({
      useByFridge: '2026-11-05'
    });
  });
});

describe('"Eat it on…" offers only meals up to the tub’s use-by (F128)', () => {
  const options = [at('2026-11-04'), at('2026-11-05'), at('2026-11-06'), at('2026-11-07')];

  it('the use-by day itself is offered, the day after is not', () => {
    expect(eatOnUpTo(options, '2026-11-05').map((o) => o.day)).toEqual([
      '2026-11-04',
      '2026-11-05'
    ]);
  });

  it('with no use-by known, nothing is offered (never a day the server will refuse)', () => {
    expect(eatOnUpTo(options, '')).toEqual([]);
  });
});

describe('how far "Eat it on…" looks', () => {
  it('to the later use-by (the freezer’s), or no limit when none is known', () => {
    expect(eatOnUntil({ useByFridge: '2026-11-05', useByFreezer: '2027-02-02' })).toBe(
      '2027-02-02'
    );
    expect(eatOnUntil({ useByFridge: '2026-11-05' })).toBe('2026-11-05');
    expect(eatOnUntil({})).toBeNull();
  });
});
