// Small helpers for words that many screens build (FE32): the no-break space and singular or
// plural. One place, so the invisible character is never typed by hand.

/** A space that never breaks the line: between a number and its unit ("2 tubs", "500 g"). */
export const NBSP = '\u00a0';

/** `one` for exactly 1, otherwise `many`: plural(1, 'tub', 'tubs'), plural(3, 'tub', 'tubs').
 *  Say the number yourself, so each screen keeps its own wording around it. */
export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/** What a search that found nothing says, everywhere: `No recipe matches “dal”.` (FE7). */
export const nothingMatches = (what: string, query: string): string =>
  `No ${what} matches “${query.trim()}”.`;
