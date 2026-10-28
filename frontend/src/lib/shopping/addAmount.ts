// "Add an item" with an amount in front: "1 l milk" is Milk, 1 litre (F63, cabledrawer 28 Oct), so
// the add joins an existing 1 L line as 0.5's rule does. This only cuts the typed text into
// "1 l" and "milk"; the number and unit are read by the same reader as the amount box
// (amountText.parseAmount through amountEdit.toBaseAmount), and it all works offline.

/** The number as parseAmount reads it: 1, 1.5, 1,5, ½, 1½, 1/2, 1 1/2. */
const NUMBER = String.raw`(?:\d+(?:[.,]\d+)?\s*(?:[¼½¾]|\d+\/\d+)?|[¼½¾]|\d+\/\d+)`;

/** Units a phone can read without knowing the ingredient (amountEdit.ts: g, kg, ml, l). */
const UNITS = String.raw`(?:g|gr|gram|grams|kg|kgs|kilo|kilos|kilogram|kilograms|ml|mls|millilitres?|milliliters?|l|ltr|litres?|liters?)`;

const ONLY_UNIT = new RegExp(`^${UNITS}\\.?$`, 'iu');
const LEADING = new RegExp(`^(${NUMBER})\\s*(${UNITS})?\\.?\\s+(\\S.*)$`, 'iu');

export interface TypedAmount {
  /** What goes to the reader: "1 l", "3". */
  amountText: string;
  /** What is left to search for: "milk". */
  name: string;
}

/** A number (with a unit) in front of a name, or null when the text has none. */
export function splitAmount(text: string): TypedAmount | null {
  const match = LEADING.exec(text.trim());
  if (!match) return null;
  const [, number, unit, name] = match;
  if (!unit && ONLY_UNIT.test(name!.trim())) return null; // "250 g": an amount, no name
  return {
    amountText: unit ? `${number!.trim()} ${normalUnit(unit)}` : number!.trim(),
    name: name!.trim()
  };
}

/** The spellings above as the reader's own g, kg, ml and l. */
function normalUnit(unit: string): string {
  const u = unit.toLowerCase();
  if (u.startsWith('k')) return 'kg';
  if (u.startsWith('m')) return 'ml';
  if (u.startsWith('l')) return 'l';
  return 'g';
}
