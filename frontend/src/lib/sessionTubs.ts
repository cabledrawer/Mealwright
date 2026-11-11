// The line under a recipe in the one Cooked it of a Batch cook session: where its tubs go.

/** "4 tubs · 2 Freezer, 2 Fridge", "3 tubs · 3 Fridge" (the places the tubs are in; "in meals" for
 * a tub with no place: proposed, for cabledrawer). null when the recipe makes no tub: nothing is said
 * ("Eaten today · no tubs" was dropped, cabledrawer 11 Nov). */
export function tubsLine(tubs: { place: string | null; count: number }[]): string | null {
  const count = tubs.reduce((n, t) => n + t.count, 0);
  if (count === 0) return null;
  const places = tubs
    .map((t) => (t.place ? `${t.count} ${t.place}` : null))
    .filter((p): p is string => p !== null);
  const loose = tubs.filter((t) => !t.place).reduce((n, t) => n + t.count, 0);
  const where = [...places, ...(loose ? [`${loose} in meals`] : [])].join(', ');
  return `${count} ${count === 1 ? 'tub' : 'tubs'} · ${where}`;
}
