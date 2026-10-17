// Foods ("ingredients" on screen): one food is one thing you buy and cook with (spec
// section 6, Foods and units). These shapes are the screen's own; they'll follow the
// 0.2 API once it's written.

export interface SaleUnit {
  /** "Packet", "Bag", "Loaf". */
  name: string;
  /** In the food's base unit: grams, millilitres or a count. */
  amount: number;
  /** The size the pantry shows amounts in. One per food. */
  usual: boolean;
  /** e.g. "added when shopping". */
  note?: string;
}

export interface Place {
  id: number;
  name: string;
}

export interface Shop {
  id: number;
  name: string;
}

export interface Food {
  id: number;
  name: string;
  otherNames: string[];
  base: 'g' | 'ml' | 'count';
  /** What one of a count food is called ("slice"), when it isn't the food itself. */
  countName?: string;
  saleUnits: SaleUnit[];
  /** Weight of 1 cup, as typed ("200 g"). */
  cupWeight: string;
  /** Running low at, as typed ("½ packet"). */
  runningLow: string;
  placeId: number | null;
  shopId: number | null;
  staple: boolean;
  /** Foods that can stand in for this one ("can use instead"). */
  standInIds: number[];
  /** A food this one might be the same as ("Maybe the same"). */
  maybeSameAsId?: number;
}

export type FoodFilter = 'all' | 'staples' | 'maybe';

/** Lower case, without accents or spare spaces, for matching names. */
function fold(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLocaleLowerCase()
    .trim()
    .replace(/\s+/g, ' ');
}

/** Search by any name: the food's own name or any of its other names. */
export function matchesSearch(food: Food, query: string): boolean {
  const q = fold(query);
  if (!q) return true;
  return [food.name, ...food.otherNames].some((name) => fold(name).includes(q));
}

export function matchesFilter(food: Food, filter: FoodFilter): boolean {
  if (filter === 'staples') return food.staple;
  if (filter === 'maybe') return food.maybeSameAsId !== undefined;
  return true;
}

/** The foods to list, in name order. */
export function listFoods(foods: readonly Food[], query: string, filter: FoodFilter): Food[] {
  return foods
    .filter((food) => matchesFilter(food, filter) && matchesSearch(food, query))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function formatBase(amount: number, base: Food['base']): string {
  if (base === 'count') return String(amount);
  if (amount >= 1000 && amount % 100 === 0) return `${amount / 1000} ${base === 'g' ? 'kg' : 'L'}`;
  return `${amount} ${base}`;
}

/** How the pantry counts it, in a few words: "Packets · 500 g", "Slices", "Staple". */
export function countedAs(food: Food): string {
  if (food.staple) return 'Staple';
  const usual = food.saleUnits.find((unit) => unit.usual);
  if (food.base === 'count') {
    return food.countName ? capitalise(plural(food.countName)) : 'Count';
  }
  if (usual) return `${capitalise(plural(usual.name))} · ${formatBase(usual.amount, food.base)}`;
  return food.base === 'g' ? 'Weight' : 'Volume';
}

/** "Packet = 500 g", "Loaf = 20 slices". */
export function describeSaleUnit(unit: SaleUnit, food: Food): string {
  if (food.base === 'count') {
    const what = food.countName ?? food.name.toLocaleLowerCase();
    return `${capitalise(unit.name)} = ${unit.amount} ${unit.amount === 1 ? what : plural(what)}`;
  }
  return `${capitalise(unit.name)} = ${formatBase(unit.amount, food.base)}`;
}

function plural(word: string): string {
  if (/(s|x|ch|sh)$/i.test(word)) return word + 'es';
  if (/[^aeiou]y$/i.test(word)) return word.slice(0, -1) + 'ies';
  return word + 's';
}

function capitalise(word: string): string {
  return word.charAt(0).toLocaleUpperCase() + word.slice(1);
}
