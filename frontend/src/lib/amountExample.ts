// The grey example in the "Amount" box, to suit the unit chosen next to it: "200" is
// sensible for grams but odd for eggs.

const EXAMPLES: Record<string, string> = { g: '200', kg: '1', ml: '250', l: '1' };

/**
 * `unit` is what's chosen in the Unit box. `isSize` is true for a way the food is sold
 * (packet, tub, dozen); anything else that isn't g, kg, ml or l counts items.
 */
export function amountExample(unit: string, isSize: boolean): string {
  if (isSize) return '1';
  return EXAMPLES[unit.toLowerCase()] ?? '6';
}
