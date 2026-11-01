import { describe, expect, it } from 'vitest';
import type { TubLeft } from './client/plan';
import { tubsForDay } from './planTubs';

const tub = (id: number, place: TubLeft['place_kind'], useBy: string): TubLeft => ({
  id,
  batch_id: id,
  number: 1,
  tub_count: 2,
  recipe_name: `Dish ${id}`,
  colour: null,
  cooked_on: '2026-10-01',
  amount_quarters: 4,
  place_id: null,
  place_kind: place,
  member_login_id: null,
  use_by: useBy
});

describe('tubsForDay (F52)', () => {
  it('lists the oldest freezer tub first, then the fridge tubs by use-by', () => {
    const offered = tubsForDay(
      [
        tub(1, 'fridge', '2026-11-12'),
        tub(2, 'freezer', '2027-02-01'),
        tub(3, 'freezer', '2027-01-05'),
        tub(4, 'fridge', '2026-11-10'),
        tub(5, 'freezer', '2027-01-05')
      ],
      '2026-11-09'
    );
    expect(offered.tubs.map((t) => t.id)).toEqual([3, 5, 2, 4, 1]);
    expect(offered.pastUseBy).toBe(0);
  });

  it('leaves out a fridge tub past its use-by on that day, and says how many', () => {
    const offered = tubsForDay(
      [
        tub(1, 'fridge', '2026-11-08'),
        tub(2, 'fridge', '2026-11-09'),
        tub(3, 'freezer', '2027-01-05')
      ],
      '2026-11-09'
    );
    expect(offered.tubs.map((t) => t.id)).toEqual([3, 2]); // use by that day is still fine
    expect(offered.pastUseBy).toBe(1);
  });

  it('leaves out a freezer tub whose use-by has passed, as the server would refuse it, without counting it', () => {
    const offered = tubsForDay([tub(1, 'freezer', '2026-11-01')], '2026-11-09');
    expect(offered.tubs).toEqual([]);
    expect(offered.pastUseBy).toBe(0);
  });

  it('does not change the list it is given', () => {
    const list = [tub(2, 'fridge', '2026-11-10'), tub(1, 'freezer', '2027-01-05')];
    tubsForDay(list, '2026-11-09');
    expect(list.map((t) => t.id)).toEqual([2, 1]);
  });
});
