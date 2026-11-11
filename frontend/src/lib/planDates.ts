// Dates on the Plan: weeks, months and the words for them. Dates are the household's
// ("2026-10-17"); nothing here reads this device's clock or time zone, so a day is a day
// wherever the phone is. `startsOn` is the household's week start: 1 Monday … 7 Sunday.

import { addDays } from './dates';

export { addDays };

const noon = (iso: string) => new Date(`${iso}T12:00:00Z`);

/** The day of the week, 1 Monday … 7 Sunday. */
export function weekdayOf(iso: string): number {
  const day = noon(iso).getUTCDay();
  return day === 0 ? 7 : day;
}

/** The first day of the week this date is in. */
export function weekStart(iso: string, startsOn: number): string {
  const back = (weekdayOf(iso) - startsOn + 7) % 7;
  return addDays(iso, -back);
}

/** Seven days from `start`. */
export function weekDays(start: string): string[] {
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

/** The first of the month a date is in. */
export const monthStart = (iso: string) => `${iso.slice(0, 7)}-01`;

/** The first of the month after the one this date is in. */
export function nextMonth(iso: string): string {
  const [y, m] = iso.split('-').map(Number) as [number, number];
  return m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, '0')}-01`;
}

/** The first of the month before the one this date is in. */
export function prevMonth(iso: string): string {
  const [y, m] = iso.split('-').map(Number) as [number, number];
  return m === 1 ? `${y - 1}-12-01` : `${y}-${String(m - 1).padStart(2, '0')}-01`;
}

/** Every day of the month grid: whole weeks, from the week start on or before the 1st. */
export function monthGrid(anyDay: string, startsOn: number): string[] {
  const first = monthStart(anyDay);
  const last = addDays(nextMonth(anyDay), -1);
  const from = weekStart(first, startsOn);
  const to = addDays(weekStart(last, startsOn), 6);
  const days: string[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) days.push(d);
  return days;
}

const dayNumber = (iso: string) => Number(iso.slice(8, 10));
const long = new Intl.DateTimeFormat('en-GB', { month: 'long', timeZone: 'UTC' });
const weekdayShort = new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'UTC' });
const weekdayLong = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' });

/** "12 – 18 October", "28 October – 3 November", or with the year when it isn't this one. */
export function weekWords(start: string, thisYear: string): string {
  const end = addDays(start, 6);
  const month = (iso: string) => long.format(noon(iso));
  const year = (iso: string) => (iso.slice(0, 4) === thisYear ? '' : ` ${iso.slice(0, 4)}`);
  if (start.slice(0, 7) === end.slice(0, 7)) {
    return `${dayNumber(start)} – ${dayNumber(end)} ${month(end)}${year(end)}`;
  }
  return `${dayNumber(start)} ${month(start)}${year(start)} – ${dayNumber(end)} ${month(end)}${year(end)}`;
}

/** "October 2026". */
export const monthWords = (iso: string) => `${long.format(noon(iso))} ${iso.slice(0, 4)}`;

const monthAbbrev = new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: 'UTC' });

/** "Nov". */
export const monthShort = (iso: string) => monthAbbrev.format(noon(iso));

/** "Mon". */
export const dayShort = (iso: string) => weekdayShort.format(noon(iso));

/** "Monday". */
export const dayLong = (iso: string) => weekdayLong.format(noon(iso));

/** "Mon 19": a day on a card or a button. */
export const dayWords = (iso: string) => `${dayShort(iso)} ${dayNumber(iso)}`;

/** "Monday 19 October": for a screen reader, a heading. */
export const dayFull = (iso: string) =>
  `${dayLong(iso)} ${dayNumber(iso)} ${long.format(noon(iso))}`;

export const dayOfMonth = dayNumber;
