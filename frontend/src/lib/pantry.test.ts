import { describe, expect, it } from 'vitest';
import { group, lot, samplePantry } from './testing/fakePantry';
import { withGroups, withoutLot } from './pantry.svelte';

describe('putting the server’s answer on screen', () => {
  it('replaces the food’s group in that place', () => {
    const { pantry } = samplePantry();
    const fresh = group(20, 'Spinach', '100 g', [lot('100 g', '2026-10-17', 0)]);
    withGroups(pantry, [fresh]);
    const fridge = pantry.places[0]!;
    expect(fridge.groups.find((g) => g.food.id === 20)?.stock.display).toBe('100 g');
    expect(fridge.groups).toHaveLength(3);
  });

  it('takes away a group that is now empty', () => {
    const { pantry } = samplePantry();
    const empty = { ...group(20, 'Spinach', '0 g', []), stock: { amount: 0, display: '0 g' } };
    withGroups(pantry, [empty]);
    expect(pantry.places[0]!.groups.map((g) => g.food.name)).toEqual(['Paneer', 'Yoghurt']);
    expect(pantry.places[0]!.items).toBe(2);
  });

  it('adds a group to a place that didn’t have that food', () => {
    const { pantry } = samplePantry();
    const moved = {
      ...group(21, 'Paneer', '200 g · 1 pack', [lot('200 g · 1 pack', '2027-01-17', 92)]),
      place: { id: 2, name: 'Freezer', kind: 'freezer' as const }
    };
    withGroups(pantry, [moved]);
    expect(pantry.places[1]!.groups.map((g) => g.food.name)).toContain('Paneer');
  });

  it('a used packet leaves the screen at once, and an empty food with it', () => {
    const { pantry, spinach } = samplePantry();
    withoutLot(pantry, spinach.id);
    expect(pantry.places[0]!.groups.map((g) => g.food.name)).toEqual(['Paneer', 'Yoghurt']);
  });

  it('a place’s count stays the rows shown, tubs included (F202)', () => {
    const { pantry } = samplePantry();
    const freezer = pantry.places[1]!;
    freezer.tubs = [
      {
        batch_id: 4,
        tub_id: 9,
        recipe_name: 'Lemon rice',
        colour: null,
        tubs: 1,
        words: '1 tub',
        use_by: '2026-10-18',
        days_left: 1,
        use_soon: true
      }
    ];
    freezer.items = 2;
    // The packet is used up: the tub is still shown, so the card says 1, never 0 above it.
    withoutLot(pantry, freezer.groups[0]!.lots[0]!.id);
    expect(freezer.groups).toHaveLength(0);
    expect(freezer.items).toBe(1);
    // An answer that puts a packet back counts both rows.
    withGroups(pantry, [
      { ...group(30, 'Frozen peas', '450 g', [lot('450 g', '2027-01-15', 90)]), place: freezer }
    ]);
    expect(freezer.items).toBe(2);
  });
});
