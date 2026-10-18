// Searching the Pantry shows one list, whatever tab or column is showing: every food that
// matches, each with the place it is in, and "also called thuvaram paruppu" when the match
// was on one of its other names. The server does the matching (the same way Ingredients
// does, so every name counts) and says which name matched in the ingredients list; this
// puts the two together.

import type { FoodRow, Group, PantryPlace, Place } from './client/types';

export interface Found {
  group: Group;
  place: Place;
  /** "also called thuvaram paruppu", when the match was on another name. */
  also: string | null;
}

/** "also called thuvaram paruppu": set when the name that matched isn't the food's own. */
export function alsoCalled(name: string, matched: string | null | undefined): string | null {
  const other = matched?.trim();
  if (!other || other.toLocaleLowerCase() === name.toLocaleLowerCase()) return null;
  return `also called ${other}`;
}

/**
 * The foods in the places shown, as one list. Best matches first (the order Ingredients
 * uses), then by place. A food in two places is in the list twice, once for each place.
 */
export function searchResults(places: PantryPlace[], foods: FoodRow[]): Found[] {
  const rank = new Map<number, number>();
  const matched = new Map<number, string | null>();
  foods.forEach((food, i) => {
    rank.set(food.id, i);
    matched.set(food.id, food.matched_name);
  });
  const found: (Found & { rank: number; at: number })[] = [];
  places.forEach((place, at) => {
    for (const group of place.groups) {
      found.push({
        group,
        place,
        also: alsoCalled(group.food.name, matched.get(group.food.id)),
        rank: rank.get(group.food.id) ?? Number.MAX_SAFE_INTEGER,
        at
      });
    }
  });
  found.sort(
    (a, b) => a.rank - b.rank || a.group.food.name.localeCompare(b.group.food.name) || a.at - b.at
  );
  return found.map(({ group, place, also }) => ({ group, place, also }));
}
