import { describe, expect, it } from 'vitest';
import type { FoodRow } from './client/types';
import { alsoCalled, searchResults } from './pantrySearch';
import { samplePantry } from './testing/fakePantry';

const row = (id: number, name: string, matched: string | null): FoodRow => ({
  id,
  name,
  other_names: [],
  matched_name: matched,
  counted_as: 'weight',
  staple: false,
  counted_as_display: 'Grams',
  place: null,
  stand_ins: [],
  maybe_same: []
});

describe('"also called" in the pantry search', () => {
  it('names the other name that matched', () => {
    expect(alsoCalled('Toor dal', 'thuvaram paruppu')).toBe('also called thuvaram paruppu');
  });

  it('says nothing when the food’s own name matched, or nothing is known', () => {
    expect(alsoCalled('Toor dal', 'Toor dal')).toBeNull();
    expect(alsoCalled('Toor dal', 'toor DAL')).toBeNull();
    expect(alsoCalled('Toor dal', null)).toBeNull();
    expect(alsoCalled('Toor dal', undefined)).toBeNull();
    expect(alsoCalled('Toor dal', '  ')).toBeNull();
  });
});

describe('the pantry search as one list', () => {
  it('lists every food that is there, each with its place, whatever column it was in', () => {
    const { pantry } = samplePantry();
    const found = searchResults(pantry.places, []);
    expect(found.map((f) => `${f.group.food.name} · ${f.place.name}`).sort()).toEqual([
      'Basmati rice · Cupboard',
      'Frozen peas · Freezer',
      'Paneer · Fridge',
      'Spinach · Fridge',
      'Toor dal · Cupboard',
      'Yoghurt · Fridge'
    ]);
  });

  it('puts the best matches first, in the order the server ranked them', () => {
    const { pantry } = samplePantry();
    const found = searchResults(pantry.places, [
      row(41, 'Basmati rice', null),
      row(7, 'Toor dal', 'thuvaram paruppu'),
      row(21, 'Paneer', null)
    ]);
    expect(found.slice(0, 3).map((f) => f.group.food.name)).toEqual([
      'Basmati rice',
      'Toor dal',
      'Paneer'
    ]);
    // Foods the server didn't rank follow, by name.
    expect(found.slice(3).map((f) => f.group.food.name)).toEqual([
      'Frozen peas',
      'Spinach',
      'Yoghurt'
    ]);
  });

  it('adds "also called" only where the match was on another name', () => {
    const { pantry } = samplePantry();
    const found = searchResults(pantry.places, [
      row(7, 'Toor dal', 'thuvaram paruppu'),
      row(21, 'Paneer', 'Paneer')
    ]);
    expect(found.find((f) => f.group.food.id === 7)?.also).toBe('also called thuvaram paruppu');
    expect(found.find((f) => f.group.food.id === 21)?.also).toBeNull();
    expect(found.find((f) => f.group.food.id === 20)?.also).toBeNull();
  });

  it('lists a food once for each place it is in', () => {
    const { pantry } = samplePantry();
    const dal = pantry.places[2]!.groups[0]!;
    pantry.places[1]!.groups.push({ ...dal, place: pantry.places[1]! });
    const found = searchResults(pantry.places, [row(7, 'Toor dal', null)]);
    expect(found.filter((f) => f.group.food.id === 7).map((f) => f.place.name)).toEqual([
      'Freezer',
      'Cupboard'
    ]);
  });
});
