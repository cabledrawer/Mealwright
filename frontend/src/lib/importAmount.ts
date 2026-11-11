// Reading the amount someone types into a line on the Check screen ("2", "½", "1½", "1 1/2",
// "0,5"). The unit has its own box, so this is only the number. Empty is no amount.

const FRACTIONS: Record<string, number> = {
  '¼': 0.25,
  '½': 0.5,
  '¾': 0.75,
  '⅓': 1 / 3,
  '⅔': 2 / 3
};

/** The most an amount box takes; the server's own limit is higher. */
const MOST = 100_000;

/** `{ amount }` (null for an empty box), or null when the box holds something that isn't a
 *  number above nothing. */
export function readAmount(text: string): { amount: number | null } | null {
  const typed = text.trim();
  if (typed === '') return { amount: null };
  if (typed.length > 20) return null;
  // A plain fraction is tried first, and a whole number needs a space before a fraction written
  // with a slash: "10/3" is ten thirds, never 1 and 0/3 (RF4 I11).
  const match = typed.match(
    /^(?:(?<plain>\d+\/\d+)|(?<whole>\d+(?:[.,]\d+)?)?(?:\s*(?<glyph>[¼½¾⅓⅔])|\s+(?<slash>\d+\/\d+))?)$/u
  );
  if (!match?.groups) return null;
  const { plain, whole, glyph, slash } = match.groups;
  const part = plain ?? glyph ?? slash;
  if (!whole && !part) return null;
  let amount = whole ? Number(whole.replace(',', '.')) : 0;
  if (part) {
    if (part in FRACTIONS) amount += FRACTIONS[part]!;
    else {
      const [top, bottom] = part.split('/').map(Number) as [number, number];
      if (!bottom) return null;
      amount += top / bottom;
    }
  }
  if (!(amount > 0) || amount > MOST) return null;
  return { amount: Math.round(amount * 1000) / 1000 };
}
