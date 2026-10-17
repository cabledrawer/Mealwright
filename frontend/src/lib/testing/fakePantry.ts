// For tests only: a small pantry, as GET /pantry would answer (contract 6.4).

import type { Group, Lot, Pantry, UseSoonLot } from '$lib/client/types';

let next = 500;

export function lot(
  display: string,
  useBy: string | null,
  daysLeft: number | null,
  extra: Partial<Lot> = {}
): Lot {
  return {
    id: next++,
    stock: { amount: 0, display, short: display.split(' · ')[0] },
    use_by: useBy,
    days_left: daysLeft,
    use_soon: daysLeft !== null && daysLeft <= 2,
    added_on: '2026-10-12',
    frozen_on: null,
    size_id: null,
    open: false,
    ...extra
  };
}

export function group(
  id: number,
  name: string,
  display: string,
  lots: Lot[],
  extra: Partial<Group> = {}
): Group {
  const dated = lots.filter((l) => l.use_by).sort((a, b) => a.days_left! - b.days_left!);
  return {
    food: { id, name, counted_as: 'weight' },
    place: { id: 1, name: 'Fridge', kind: 'fridge' },
    stock: { amount: 0, display },
    lots_count: lots.length,
    dates_count: new Set(lots.map((l) => l.use_by)).size,
    use_by: dated[0]?.use_by ?? null,
    days_left: dated[0]?.days_left ?? null,
    use_soon: !!dated[0] && dated[0].days_left! <= 2,
    running_low: false,
    lots,
    ...extra
  };
}

export function samplePantry() {
  const spinach = lot('200 g', '2026-10-17', 0);
  const paneer = [lot('1 pack · 200 g', '2026-10-19', 2), lot('1 pack · 200 g', '2026-10-21', 4)];
  const yoghurt = lot('½ tub · about 250 g', '2026-10-21', 4, {
    open: true,
    stock: {
      amount: 250,
      display: '½ tub · about 250 g',
      as_sold: { count: 0.5, size: { id: 9, name: 'tub', plural: 'tubs', amount: 500 } }
    }
  });
  const pantry: Pantry = {
    today: '2026-10-17',
    counts: { items: 6, tubs: 0, use_soon: 2, running_low: 1 },
    places: [
      {
        id: 1,
        name: 'Fridge',
        kind: 'fridge',
        items: 3,
        groups: [
          group(20, 'Spinach', '200 g', [spinach]),
          group(21, 'Paneer', '2 packs · 400 g', paneer),
          group(24, 'Yoghurt', '½ tub · about 250 g', [yoghurt])
        ]
      },
      {
        id: 2,
        name: 'Freezer',
        kind: 'freezer',
        items: 1,
        groups: [group(30, 'Frozen peas', '450 g', [lot('450 g', '2027-01-15', 90)])]
      },
      {
        id: 3,
        name: 'Cupboard',
        kind: 'cupboard',
        items: 2,
        groups: [
          group(7, 'Toor dal', '1½ packets · about 750 g', [
            lot('1½ packets · about 750 g', null, null)
          ]),
          group(41, 'Basmati rice', '300 g', [lot('300 g', null, null)], { running_low: true })
        ]
      },
      { id: 4, name: 'Spice rack', kind: 'cupboard', items: 0, groups: [] }
    ],
    staples: [
      { id: 60, name: 'Salt' },
      { id: 61, name: 'Turmeric' }
    ]
  };
  // Each group knows its place, as the server says.
  for (const place of pantry.places) {
    for (const g of place.groups) g.place = { id: place.id, name: place.name, kind: place.kind };
  }
  const fridge = { id: 1, name: 'Fridge', kind: 'fridge' as const };
  const useSoon: UseSoonLot[] = [
    {
      id: spinach.id,
      food: { id: 20, name: 'Spinach' },
      place: fridge,
      stock: spinach.stock,
      use_by: spinach.use_by,
      days_left: 0,
      position: 1,
      of: 1
    },
    {
      id: paneer[0]!.id,
      food: { id: 21, name: 'Paneer' },
      place: fridge,
      stock: paneer[0]!.stock,
      use_by: paneer[0]!.use_by,
      days_left: 2,
      position: 1,
      of: 2
    }
  ];
  return { pantry, useSoon, spinach, paneer, yoghurt };
}
