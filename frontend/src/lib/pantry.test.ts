import { describe, expect, it } from 'vitest';
import { group, lot, samplePantry } from './testing/fakePantry';
import { withGroups, withoutLot } from './pantry.svelte';

describe("putting the server's answer on screen", () => {
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
      ...group(21, 'Paneer', '1 pack · 200 g', [lot('1 pack · 200 g', '2027-01-17', 92)]),
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
});
