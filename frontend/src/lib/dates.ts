// Use-by dates in plain words. Dates are the household's local dates ("2026-10-20");
// the server says how many days are left, worked out in the household's time zone, so
// nothing here depends on this device's clock or time zone.

function noonUtc(iso: string): Date {
  return new Date(`${iso}T12:00:00Z`);
}

/** The date `days` after `iso`. */
export function addDays(iso: string, days: number): string {
  const d = noonUtc(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The words when a typed date is odd or out of range (F220; accepted, cabledrawer 11 Nov). */
export const BAD_DATE = 'That date doesn’t look right. Pick another.';

/** A real day, written "2026-10-20", in a sane range. A date box can hand back a stray
 * six-digit year or a year 6; those are never a day to keep or to format (F220). */
export function isSaneDay(iso: unknown): iso is string {
  if (!isRealDay(iso)) return false;
  const year = Number(iso.slice(0, 4));
  return year >= 2000 && year <= 2100;
}

/** Any real day written "2026-10-20", whatever its year: what the formatters need so they
 * never throw. A stored date outside the date boxes' range still shows (FX4 review r1). */
export function isRealDay(iso: unknown): iso is string {
  if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false;
  const d = new Date(`${iso}T12:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === iso;
}

const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'UTC' });
const dayMonth = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC'
});

/** "Today", "Tomorrow", "Mon" (this week), "12 Nov"; "Date passed" when it's gone. */
export function dateWords(iso: string | null, daysLeft: number | null): string {
  if (!iso || daysLeft === null || !isRealDay(iso)) return '';
  if (daysLeft < 0) return 'Date passed';
  if (daysLeft === 0) return 'Today';
  if (daysLeft === 1) return 'Tomorrow';
  if (daysLeft < 7) return weekday.format(noonUtc(iso));
  return dayMonth.format(noonUtc(iso));
}

/** A date as day and month: "22 Oct". */
export function dayMonthWords(iso: string): string {
  if (!isRealDay(iso)) return '';
  return dayMonth.format(noonUtc(iso));
}

/** A chosen date on a chip: "Sat 24 Oct". */
export function pickedDateWords(iso: string): string {
  if (!isRealDay(iso)) return '';
  const date = noonUtc(iso);
  return `${weekday.format(date)} ${dayMonth.format(date)}`;
}

/** The short date in the phone Use soon card ("Today", "Tomorrow", "Tue", "12 Nov"): the
 * same words as the Today chip, with a capital, since it starts the date after "Lemon ·".
 * Mid-sentence wording ("use by today", "added today") stays lower-case. */
export function compactDateWords(iso: string | null, daysLeft: number | null): string {
  return dateWords(iso, daysLeft);
}

/** "use by Mon", "use by today", "Date passed". */
export function useByWords(iso: string | null, daysLeft: number | null): string {
  const words = dateWords(iso, daysLeft);
  if (!words) return 'no use-by date';
  if (words === 'Date passed') return 'Date passed';
  return `use by ${words === 'Today' || words === 'Tomorrow' ? words.toLowerCase() : words}`;
}

/** "bought today", "bought yesterday", "bought Mon", "bought 20 Oct": on a row with no use-by (0.5).
 * A lot found at home, typed in or counted in a stocktake says "found at home today", and so on
 * (F201). */
export function boughtWords(
  iso: string,
  today: string,
  how: 'bought' | 'found' = 'bought'
): string {
  return addedWords(iso, today).replace(/^added/, how === 'found' ? 'found at home' : 'bought');
}

/** "added today", "added Mon", "added 3 Oct", from the household's today. */
export function addedWords(iso: string, today: string): string {
  const days = Math.round((noonUtc(today).getTime() - noonUtc(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'added today';
  if (days === 1) return 'added yesterday';
  if (days < 7) return `added ${weekday.format(noonUtc(iso))}`;
  return `added ${dayMonth.format(noonUtc(iso))}`;
}

// --- Use by and Best before (0.8, cabledrawer 7 Nov) ------------------------------------------------

export type DateKind = 'use_by' | 'best_before';

/** How the date reads on a row: red for a passed Use by, grey for a passed Best before, the
 * soon colour for a Use by that is close, else plain. */
export type DateTone = 'late' | 'bb' | 'soon' | 'plain';

export interface WhenWords {
  /** What the date says: "Use by Sun", "best before 12 Nov", or "Date passed" for either kind. */
  text: string;
  tone: DateTone;
  passed: boolean;
}

const lowerDay = (words: string) =>
  words === 'Today' || words === 'Tomorrow' ? words.toLowerCase() : words;

/**
 * The date on a packet in plain words. A passed date, Use by or Best before, just says "Date
 * passed" (cabledrawer 15 Nov): red for Use by, grey for Best before. `capital` starts "Use by Sun" with a capital (phone rows, Use soon); a row
 * in a desktop column writes "use by Sun".
 */
export function whenWords(
  kind: DateKind,
  iso: string | null,
  daysLeft: number | null,
  options: { capital?: boolean; soon?: boolean } = {}
): WhenWords {
  if (!iso || daysLeft === null) return { text: '', tone: 'plain', passed: false };
  if (daysLeft < 0) {
    return { text: 'Date passed', tone: kind === 'use_by' ? 'late' : 'bb', passed: true };
  }
  const label = kind === 'use_by' ? 'use by' : 'best before';
  const start = options.capital ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : label;
  return {
    text: `${start} ${lowerDay(dateWords(iso, daysLeft))}`,
    tone: options.soon ? 'soon' : 'plain',
    passed: false
  };
}
