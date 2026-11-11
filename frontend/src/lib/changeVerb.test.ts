import { describe, expect, it } from 'vitest';
import { startsWithVerb } from './changeVerb';

const edit = (summary: string) => ({ kind: 'food_edited', summary });

describe('the kinds in Settings → Recent changes (F172)', () => {
  it('stock, plan, cooking and removals start with a verb', () => {
    for (const kind of [
      'used',
      'cooked',
      'stocktake',
      'plan_add',
      'plan_slot',
      'shop_removed',
      'shop_added',
      'shop_renamed',
      'place_removed',
      'place_added',
      'place_renamed',
      'shops_ordered',
      'places_ordered',
      'kitchen_changed',
      'batch_cook_switch',
      'pints_changed',
      'cook_step_changed'
    ]) {
      expect(startsWithVerb({ kind, summary: 'Cooked Sambar' })).toBe(true);
    }
  });
});

describe('startsWithVerb', () => {
  it('is true for the kinds that always start with a verb', () => {
    for (const kind of ['food_created', 'food_removed', 'merged', 'split', 'undo']) {
      expect(startsWithVerb({ kind, summary: 'Added Tahini' })).toBe(true);
    }
  });

  it('is true for a rename', () => {
    expect(startsWithVerb(edit('Renamed Rice to Basmati rice'))).toBe(true);
  });

  it('is true for adding and removing another name', () => {
    expect(startsWithVerb(edit('Added other name Chickpeas to Chana'))).toBe(true);
    expect(startsWithVerb(edit('Removed other name Chickpeas from Chana'))).toBe(true);
  });

  it('is true for forgetting a weight', () => {
    expect(startsWithVerb(edit('Forgot your weight of 1\u00a0cup of Rice'))).toBe(true);
    expect(startsWithVerb(edit('Forgot your weight of one Onion'))).toBe(true);
  });

  it('is false for edits that start with the ingredient', () => {
    expect(startsWithVerb(edit('Toor dal is now a staple'))).toBe(false);
    expect(startsWithVerb(edit('Toor dal runs low at ½ packet'))).toBe(false);
  });

  it('never goes by the ingredient’s name', () => {
    // Called "Added sugar" or "Renamed rice": the edit's wording starts with the name.
    expect(startsWithVerb(edit('Added sugar is now a staple'))).toBe(false);
    expect(startsWithVerb(edit('Renamed rice is now a staple'))).toBe(false);
    expect(startsWithVerb(edit('Renamed rice is no longer a staple'))).toBe(false);
    expect(startsWithVerb(edit('Renamed rice is now counted by weight'))).toBe(false);
    expect(startsWithVerb(edit('Renamed rice is now in Dry goods'))).toBe(false);
    expect(startsWithVerb(edit('Renamed rice runs low at 200 g'))).toBe(false);
    expect(startsWithVerb(edit('Added other name is now a staple'))).toBe(false);
    expect(startsWithVerb(edit('Removed other name now lives in Fridge'))).toBe(false);
    expect(startsWithVerb(edit('Forgot your weight of one rice has no usual shop'))).toBe(false);
    // And a real rename of such an ingredient still starts with its verb.
    expect(startsWithVerb(edit('Renamed Added sugar to Sugar'))).toBe(true);
  });
});
