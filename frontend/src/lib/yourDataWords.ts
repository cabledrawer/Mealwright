// The words on Settings → Your data (0.9, D1; mockups Dark-YourData09-Phone and
// Dark-DeleteAll09-Phone). The mockup's words, and the ones it doesn't show (proposed, for
// cabledrawer): docs/dev/words.md, section 72.

import type { BackupEvery, Backups } from '#lib/client/yourData.js';

export const EVERY_WORDS: Record<BackupEvery, string> = {
  daily: 'Daily, 03:00',
  'twice-daily': 'Twice a day, 03:00 and 15:00',
  weekly: 'Weekly, Mondays 03:00'
};

export const keepWords = (keep: number): string => (keep === 1 ? 'Last 1' : `Last ${keep}`);

const NBSP = '\u00a0'; // between a number and its unit, so they never part

/** A file's size the way people read it: "2.1 MB", "640 KB", "900 bytes". */
export function sizeWords(bytes: number): string {
  if (bytes < 1000) return `${bytes}${NBSP}bytes`;
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)}${NBSP}KB`;
  if (bytes < 1_000_000_000) return `${(bytes / 1_000_000).toFixed(1)}${NBSP}MB`;
  return `${(bytes / 1_000_000_000).toFixed(1)}${NBSP}GB`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** A moment's calendar day (as a number of days) and clock, in `zone`, or this device's own
 * time when it has none (or one this browser doesn't know). */
function dayAndClock(at: Date, zone?: string | null): { day: number; clock: string } {
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23'
  };
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat(
      'en-GB',
      zone ? { ...options, timeZone: zone } : options
    ).formatToParts(at);
  } catch {
    parts = new Intl.DateTimeFormat('en-GB', options).formatToParts(at);
  }
  const of = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return {
    day: Date.UTC(of('year'), of('month') - 1, of('day')) / 86_400_000,
    clock: `${String(of('hour')).padStart(2, '0')}:${String(of('minute')).padStart(2, '0')}`
  };
}

/**
 * When, the way the rest of the app says it: "Today 03:00", "Yesterday 15:00", a weekday for
 * the last 6 days ("Mon 03:00"), then "12 Nov 03:00". In `zone` (the household's time zone, for
 * "Link used"; 16b review R-L4), or this device's own time without one (Your data).
 */
export function whenWords(iso: string, now: Date = new Date(), zone?: string | null): string {
  const at = dayAndClock(new Date(iso), zone);
  const daysAgo = dayAndClock(now, zone).day - at.day;
  const date = new Date(at.day * 86_400_000);
  if (daysAgo === 0) return `Today ${at.clock}`;
  if (daysAgo === 1) return `Yesterday ${at.clock}`;
  if (daysAgo > 1 && daysAgo < 7) return `${DAYS[date.getUTCDay()]} ${at.clock}`;
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${at.clock}`;
}

/** The "Last backup" row's line: "Today 03:00 · 2.1 MB · all fine". */
export function lastBackupWords(backups: Backups, now: Date = new Date()): string {
  if (!backups.last) return backups.problem ? 'None yet' : 'None yet · the first is made soon';
  const parts = [whenWords(backups.last.at, now), sizeWords(backups.last.size)];
  if (!backups.problem) parts.push('all fine');
  return parts.join(' · ');
}

/** The last try failed: what to show under the row. */
export function problemWords(backups: Backups, now: Date = new Date()): string | null {
  if (!backups.problem) return null;
  const when = backups.problem_at ? ` (${whenWords(backups.problem_at, now)})` : '';
  return `The last backup failed${when}: ${backups.problem}`;
}

export const SAME_DISK =
  'Backups sit on the same disk as Mealwright. If that disk dies, they go too: copy the backups folder somewhere else as well (another disk, your NAS).';

export const PHOTOS_NOTE =
  'A backup holds the database: every recipe, plan, list, pantry item and setting. Recipe photos are files beside it, in the photos folder; copy that folder too.';

export const EXPORT_LEAD = 'One file with all recipes, plans, lists, pantry, people and settings.';

export const UNDO_REACH = 'Undo reaches back 7 days.';

export const ADMINS_ONLY = 'Only the household’s admin can change these.';

/** The words to type on Delete everything. */
export const DELETE_WORDS = 'delete everything';

/** Typed the words, give or take capitals and spaces (the server reads them the same way). */
export const wordsMatch = (typed: string): boolean =>
  typed.split(/\s+/).filter(Boolean).join(' ').toLowerCase() === DELETE_WORDS;
