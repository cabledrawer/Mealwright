import { describe, expect, it } from 'vitest';
import type { TubLeft } from './client/plan';
import { tubsForDay, tubsListed } from './planTubs';

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
  member_id: null,
  use_by: useBy
});

describe('tubsForDay never offers a tub before it is cooked (F230, spec F50)', () => {
  const batch = (id: number, cookedOn: string): TubLeft => ({
    ...tub(id, 'fridge', '2026-11-30'),
    cooked_on: cookedOn
  });
  // The Sat 14 batch (Khichdi, Dal Tadka) is not cooked yet on Fri 13.
  it('leaves out a tub for a day before its cook day', () => {
    const list = [batch(1, '2026-11-14'), batch(2, '2026-11-12')];
    expect(tubsForDay(list, '2026-11-13').tubs.map((t) => t.id)).toEqual([2]);
    expect(tubsForDay(list, '2026-11-14').tubs.map((t) => t.id)).toEqual([1, 2]);
  });

  it('does not count a tub not cooked yet as "past its use-by"', () => {
    const early = { ...batch(1, '2026-11-14'), use_by: '2026-11-15' };
    expect(tubsForDay([early], '2026-11-13').pastUseBy).toBe(0);
  });

  it('on the cook day offers it only at a meal after the cooking', () => {
    const list = [batch(1, '2026-11-14')];
    const at = (slotId: number) =>
      tubsForDay(list, '2026-11-14', { slotId, slotIds: [1, 2, 3], cookSlotOf: () => 2 }).tubs;
    expect(at(1)).toEqual([]);
    expect(at(2)).toEqual([]); // the cooking meal itself
    expect(at(3).map((t) => t.id)).toEqual([1]);
  });

  it('offers it on a day after the cook day at any meal, and when the cook meal is not known', () => {
    const list = [batch(1, '2026-11-14')];
    const meal = { slotId: 1, slotIds: [1, 2], cookSlotOf: () => 2 };
    expect(tubsForDay(list, '2026-11-15', meal).tubs).toHaveLength(1);
    expect(tubsForDay(list, '2026-11-14', { ...meal, cookSlotOf: () => null }).tubs).toHaveLength(
      1
    );
  });

  it('asks for the cook meal on the day the tub counts from (a batch cooked early has none)', () => {
    const asked: string[] = [];
    const meal = {
      slotId: 1,
      slotIds: [1, 2],
      cookSlotOf: (_batch: number, on: string) => {
        asked.push(on);
        return null;
      }
    };
    expect(tubsForDay([batch(1, '2026-11-12')], '2026-11-12', meal).tubs).toHaveLength(1);
    expect(asked).toEqual(['2026-11-12']);
  });
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

describe('tubsListed', () => {
  const many = [
    ...Array.from({ length: 14 }, (_, i) => tub(100 + i, 'freezer', `2027-01-${10 + i}`)),
    tub(1, 'fridge', '2026-11-12'),
    tub(2, 'fridge', '2026-11-13')
  ];
  const ordered = tubsForDay(many, '2026-11-09').tubs;

  it('lists everything when it fits', () => {
    expect(tubsListed(ordered.slice(0, 12), false)).toEqual({
      shown: ordered.slice(0, 12),
      hidden: 0
    });
  });

  it('never hides a fridge tub behind a long freezer list, and counts what waits', () => {
    const { shown, hidden } = tubsListed(ordered, false);
    expect(shown.length).toBe(12);
    expect(shown.map((t) => t.id)).toContain(1);
    expect(shown.map((t) => t.id)).toContain(2);
    expect(shown.filter((t) => t.place_kind === 'freezer').map((t) => t.id)).toEqual(
      ordered
        .filter((t) => t.place_kind === 'freezer')
        .slice(0, 10)
        .map((t) => t.id)
    );
    expect(hidden).toBe(4);
  });

  it('lists all of them once expanded', () => {
    expect(tubsListed(ordered, true)).toEqual({ shown: ordered, hidden: 0 });
  });
});
