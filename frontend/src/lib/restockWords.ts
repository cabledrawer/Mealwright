// A staple's restock date in plain words (0.7 K5, spec section 6 "Restock dates"). The server
// says the household's own day ("2026-10-12") and how many days ago that was, so nothing here
// depends on this device's clock or time zone.

import { dayMonthWords, isRealDay } from './dates.js';

const full = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC'
});

/** How long ago, in the biggest whole step: "today", "yesterday", "5 days ago", "3 weeks ago". */
export function agoWords(days: number): string {
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30) return plural(Math.floor(days / 7), 'week');
  if (days < 365) return plural(Math.floor(days / 30), 'month');
  return plural(Math.floor(days / 365), 'year');
}

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? '' : 's'} ago`;
}

/** The pantry chip's line: "Restocked 12 Oct" ("Restocked today" on the day). */
export function chipWords(on: string, daysAgo: number): string {
  return daysAgo <= 0 ? 'Restocked today' : `Restocked ${dayMonthWords(on)}`;
}

/** The Ingredients column: "Restocked 3 weeks ago". */
export function columnWords(daysAgo: number): string {
  return `Restocked ${agoWords(daysAgo)}`;
}

/** The whole date, for hover and tap: "12 Oct 2026". */
export function fullDateWords(on: string): string {
  if (!isRealDay(on)) return '';
  return full.format(new Date(`${on}T12:00:00Z`));
}
