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

const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'UTC' });
const dayMonth = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC'
});

/** "Today", "Tomorrow", "Mon" (this week), "12 Nov"; "Date passed" when it's gone. */
export function dateWords(iso: string | null, daysLeft: number | null): string {
  if (!iso || daysLeft === null) return '';
  if (daysLeft < 0) return 'Date passed';
  if (daysLeft === 0) return 'Today';
  if (daysLeft === 1) return 'Tomorrow';
  if (daysLeft < 7) return weekday.format(noonUtc(iso));
  return dayMonth.format(noonUtc(iso));
}

/** The short date in the phone Use soon card ("Today", "Tomorrow", "Tue", "12 Nov"): the
 * same words as the Today chip, with a capital, since it starts the date after "Lemon ·".
 * Mid-sentence wording ("use by today", "added today") stays lower-case. */
export function compactDateWords(iso: string | null, daysLeft: number | null): string {
  return dateWords(iso, daysLeft);
}

/** "use by Mon", "use by today", "use-by date passed". */
export function useByWords(iso: string | null, daysLeft: number | null): string {
  const words = dateWords(iso, daysLeft);
  if (!words) return 'no use-by date';
  if (words === 'Date passed') return 'use-by date passed';
  return `use by ${words === 'Today' || words === 'Tomorrow' ? words.toLowerCase() : words}`;
}

/** "added today", "added Mon", "added 3 Oct", from the household's today. */
export function addedWords(iso: string, today: string): string {
  const days = Math.round((noonUtc(today).getTime() - noonUtc(iso).getTime()) / 86_400_000);
  if (days <= 0) return 'added today';
  if (days === 1) return 'added yesterday';
  if (days < 7) return `added ${weekday.format(noonUtc(iso))}`;
  return `added ${dayMonth.format(noonUtc(iso))}`;
}
