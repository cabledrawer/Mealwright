// A time in minutes, in words (F114, cabledrawer 31 Oct): "45 min" up to an hour, then hours and
// minutes ("1 h", "2 h 5 min", "12 h 25 min"). The one place a time in minutes is turned into
// text; every list, card and page uses it. A no-break space keeps a number with its unit.
const NBSP = ' ';

export function timeWords(minutes: number): string {
  const total = Math.round(minutes);
  if (total < 60) return `${total}${NBSP}min`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest === 0 ? `${hours}${NBSP}h` : `${hours}${NBSP}h${NBSP}${rest}${NBSP}min`;
}
