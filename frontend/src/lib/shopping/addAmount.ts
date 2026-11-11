// "Add an item" with an amount in front: "1 l milk" is Milk, 1 litre (F63, cabledrawer 28 Oct), so
// the add joins an existing 1 L line as 0.5's rule does. This only cuts the typed text into
// "1 l" and "milk"; the number and unit are read by the same reader as the amount box
// (amountText.parseAmount through amountEdit.toBaseAmount), and it all works offline.

import { parseAmount } from '#lib/amountText.js';
import { toBaseAmount, type Parsed } from './amountEdit.js';
import type { Chosen } from '#lib/newIngredient.svelte.js';
import type { CountedAs, Food } from '#lib/client/types.js';

/** The number as parseAmount reads it: 1, 1.5, 1,5, ½, 1½, 1/2, 1 1/2. */
const NUMBER = String.raw`(?:\d+\/\d+|\d+(?:[.,]\d+)?(?:\s*[¼½¾]|\s+\d+\/\d+)?|[¼½¾])`;

/** Units a phone can read without knowing the ingredient (amountEdit.ts: g, kg, ml, l). */
const UNITS = String.raw`(?:g|gr|gram|grams|kg|kgs|kilo|kilos|kilogram|kilograms|ml|mls|millilitres?|milliliters?|l|ltr|litres?|liters?)`;

/**
 * The ways an ingredient is sold, as the reader's own SIZE_WORDS name the containers (backend
 * ingredient_reader.py): "2 packets milk" is Milk, 2 packets (cabledrawer 30 Oct). Whether the
 * ingredient has a size of that name is decided when the amount is read for it, as for "2 packets"
 * typed in the amount box.
 */
const PACKS = String.raw`(?:packets?|packs?|tubs?|tins?|cans?|jars?|bags?|box(?:es)?|cartons?|bottles?|loaf|loaves|dozen|bunch(?:es)?|trays?|sachets?|tubes?|blocks?|pots?)`;

const ONLY_UNIT = new RegExp(`^(?:${UNITS}|${PACKS})\\.?$`, 'iu');
const LEADING = new RegExp(`^(${NUMBER})\\s*(${UNITS}|${PACKS})?\\.?\\s+(\\S.*)$`, 'iu');

/** The longest an ingredient's name may be (the server's limit, foods.py Name), plus room for
 * the amount in front of it. Longer text is no amount and a name the server would refuse. */
export const MAX_NAME = 100;
export const MAX_ADD_TEXT = MAX_NAME + 33;

export interface TypedAmount {
  /** What goes to the reader: "1 l", "3". */
  amountText: string;
  /** What is left to search for: "milk". */
  name: string;
  /** "0 g butter": the amount is nothing. The name is still searched (Butter), but nothing is
   * added until an amount above 0 is typed (cabledrawer 29 Oct). */
  zero?: true;
}

/** Said when the typed amount is 0 (cabledrawer 29 Oct). */
export const ZERO_AMOUNT = 'Type an amount above 0';

/** A number (with a unit) in front of a name, or null when the text has none. */
export function splitAmount(text: string): TypedAmount | null {
  if (text.length > MAX_ADD_TEXT) return null;
  const match = LEADING.exec(text.trim());
  if (!match) return null;
  const [, number, unit, written] = match;
  const name = unit ? written!.replace(/^of\s+(?=\S)/iu, '') : written; // "2 bags of ice"
  // "00 flour", "007": a number that starts with a zero and goes on is the start of a name.
  if (/^0\d/.test(number!.trim())) return null;
  if (!unit && ONLY_UNIT.test(name!.trim())) return null; // "250 g": an amount, no name
  // "0 g butter" is Butter with an amount of nothing, not a new item (cabledrawer 29 Oct).
  const zero = !(Number.parseFloat(number!.replace(',', '.')) > 0) && !/[¼½¾]|\//.test(number!);
  return {
    amountText: unit ? `${number!.trim()} ${normalUnit(unit)}` : number!.trim(),
    name: name!.trim(),
    ...(zero ? { zero: true as const } : {})
  };
}

/** The spellings above as the reader's own g, kg, ml and l. */
function normalUnit(unit: string): string {
  const u = unit.toLowerCase();
  if (new RegExp(`^${PACKS}$`, 'iu').test(u)) return u; // a way it's sold: kept as typed
  if (u.startsWith('k')) return 'kg';
  if (u.startsWith('m')) return 'ml';
  if (u.startsWith('l')) return 'l';
  return 'g';
}

/**
 * The amount as it will be read for this ingredient, for the match row: a bare 2 for garlic
 * weighed in grams is "2 g", not "2". The same reader as the amount box. Null when the
 * unit typed isn't one the ingredient has (the amount would be refused).
 */
export function readAs(
  amountText: string,
  food: Pick<Food, 'counted_as' | 'sizes' | 'count_word' | 'count_word_plural'>
): string | null {
  const asked = parseAmount(amountText, food);
  if (!asked) return null;
  // Only a unit this ingredient has is offered (F95): "2 packets" for milk with no packet size
  // would be refused on adding, so the row shows the name alone and the refusal says why.
  if ('problem' in toBaseAmount(amountText, food)) return null;
  const number = String(Math.round(asked.amount * 1000) / 1000);
  if (!asked.unit || asked.unit === 'count') return number;
  // Written as the app writes it: "1 L", and a packet size in the plural when it isn't one.
  const size = food.sizes.find((s) => s.name === asked.unit);
  const unit = asked.unit === 'l' ? 'L' : size && asked.amount !== 1 ? size.plural : asked.unit;
  return `${number} ${unit}`;
}

/**
 * How a new ingredient is counted, from the amount typed in front of its name (F83, cabledrawer 30
 * Oct): "1 l orange juice" is By volume, "250 g" By weight, a bare "3" One by one. A way it is
 * sold ("2 packets") says nothing, so null: the table's guess or By weight stays.
 */
export function countedAsFor(amountText: string): CountedAs | null {
  const unit = /([a-z]+)\s*$/iu.exec(amountText.trim())?.[1]?.toLowerCase();
  if (!unit) return 'count';
  if (unit === 'g' || unit === 'kg') return 'weight';
  if (unit === 'ml' || unit === 'l') return 'volume';
  return null;
}

/**
 * The typed amount for an ingredient that is being made right now ("2 packets milk" with the
 * packet size just added in the dialog). Those sizes aren't saved yet, so they have no real id:
 * the amount comes back as the plain total in grams, millilitres or items, with no size id.
 */
export function readForNew(
  amountText: string,
  chosen: Pick<Chosen, 'counted_as' | 'sizes'>
): Parsed {
  const read = toBaseAmount(amountText, {
    counted_as: chosen.counted_as,
    sizes: chosen.sizes.map((size, index) => ({
      id: -(index + 1),
      name: size.name.toLowerCase(),
      plural: `${size.name.toLowerCase()}s`,
      amount: size.amount * (size.unit === 'kg' || size.unit === 'l' ? 1000 : 1),
      display: '',
      usual: false,
      added_when_shopping: true
    })),
    count_word: null,
    count_word_plural: null
  });
  return 'problem' in read ? read : { amount: read.amount, sizeId: null };
}
