// The words on Settings › Backups & your data (0.9, D1; mockups Dark-YourData09-Phone and
// Dark-DeleteAll09-Phone). The mockup's words, and the ones it doesn't show (proposed, for
// cabledrawer): docs/dev/words.md, section 72.

import type { BackupEvery, Backups } from '#lib/client/yourData.js';
import { dayMonthOf, weekdayOf } from './dates.js';
import { UNDO_SPAN } from '#lib/undoWords.js';
import { NBSP } from './words.js';

export const EVERY_WORDS: Record<BackupEvery, string> = {
  daily: 'Daily, 03:00',
  twice_daily: 'Twice a day, 03:00 and 15:00',
  weekly: 'Weekly, Mondays 03:00'
};

export const keepWords = (keep: number): string => (keep === 1 ? 'Last 1' : `Last ${keep}`);

/** A file's size the way people read it: "2.1 MB", "640 KB", "900 bytes". */
export function sizeWords(bytes: number): string {
  if (bytes < 1000) return `${bytes}${NBSP}bytes`;
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)}${NBSP}KB`;
  if (bytes < 1_000_000_000) return `${(bytes / 1_000_000).toFixed(1)}${NBSP}MB`;
  return `${(bytes / 1_000_000_000).toFixed(1)}${NBSP}GB`;
}

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
export function momentWords(iso: string, now: Date = new Date(), zone?: string | null): string {
  const at = dayAndClock(new Date(iso), zone);
  const daysAgo = dayAndClock(now, zone).day - at.day;
  const date = new Date(at.day * 86_400_000);
  if (daysAgo === 0) return `Today ${at.clock}`;
  if (daysAgo === 1) return `Yesterday ${at.clock}`;
  if (daysAgo > 1 && daysAgo < 7) return `${weekdayOf(date)} ${at.clock}`;
  return `${dayMonthOf(date, 'UTC')} ${at.clock}`;
}

/** The "Last backup" row's line: "Today 03:00 · 2.1 MB · all fine". */
export function lastBackupWords(backups: Backups, now: Date = new Date()): string {
  if (!backups.last) return backups.problem ? 'None yet' : 'None yet · the first is made soon';
  const size = sizeWords(backups.last.size);
  const parts = [
    momentWords(backups.last.at, now),
    backups.last.photos ? `${size} with photos` : size
  ];
  if (!backups.problem) parts.push('all fine');
  return parts.join(' · ');
}

/** The last try failed: what to show under the row. */
export function problemWords(backups: Backups, now: Date = new Date()): string | null {
  if (!backups.problem) return null;
  const when = backups.problem_at ? ` (${momentWords(backups.problem_at, now)})` : '';
  return `The last backup failed${when}: ${backups.problem}`;
}

export const SAME_DISK =
  'Backups sit on the same disk as Mealwright. If that disk dies, they go too: copy the backups folder somewhere else as well (another disk, your NAS).';

/** Under the card (mockup Dark-YourData095-Phone). */
export const SAFETY_COPY_NOTE = 'The safety copy made before each upgrade follows the same choice.';

/** The Include photos row's small line: the mockup's "Recipe photos, 410 MB. Without them a
 * backup is about 2 MB, but photos can't be restored from it." With no photo yet, "No recipe
 * photos yet." in place of the first sentence (proposed, for cabledrawer). */
export function includePhotosWords(photosSize: number | null, databaseSize: number | null): string {
  // A member is told no sizes (only an admin is): the line says only what matters
  // (proposed, for cabledrawer).
  if (photosSize === null || databaseSize === null)
    return 'Without them, photos can’t be restored from a backup.';
  const first =
    photosSize > 0 ? `Recipe photos, ${sizeWords(photosSize)}.` : 'No recipe photos yet.';
  return `${first} Without them a backup is about ${sizeWords(databaseSize)}, but photos can’t be restored from it.`;
}

export const EXPORT_LEAD = 'One file with all recipes, plans, lists, pantry, people and settings.';

/** The password box on Export everything. The mockup (Dark-YourData09-Phone) said "Password
 * (optional)"; cabledrawer 20 Nov (F257): "Password for the export file", so a sign-in password
 * isn't typed there by mistake. */
export const EXPORT_PASSWORD_LABEL = 'Password for the export file';

export const EXPORT_PASSWORD_HINT =
  'With a password, the file is encrypted. Without it you can’t open the file, so keep it safe.';

/** Proposed, for cabledrawer: the rule and that the password can't be recovered. */
export const EXPORT_PASSWORD_RULE =
  'Use 8 to 1,024 characters. Mealwright doesn’t keep the password and can’t recover it.';

/** Proposed, for cabledrawer: while the file is being made and when it can't be. */
export const EXPORT_MAKING = 'Making the file…';
export const EXPORT_PASSWORD_LENGTH = 'Use a password of 8 to 1,024 characters.';

/** The password's length counts as the server counts it (Unicode NFC). */
export function exportPasswordOk(password: string): boolean {
  const length = [...password.normalize('NFC')].length;
  return length >= 8 && length <= 1024;
}

export const UNDO_REACH = `Undo reaches back ${UNDO_SPAN}.`;

export const ADMINS_ONLY = 'Only the household’s admin can change these.';

/** The words to type on Delete everything. */
export const DELETE_WORDS = 'delete everything';

/** Typed the words, give or take capitals and spaces (the server reads them the same way). */
export const wordsMatch = (typed: string): boolean =>
  typed.split(/\s+/).filter(Boolean).join(' ').toLowerCase() === DELETE_WORDS;

// D3 (cabledrawer 13 Nov): an admin who signs in only with single sign-on confirms Delete everything
// with a fresh sign-in at the sign-in server instead of a password. Proposed, for cabledrawer.
export const CONFIRM_SSO_LINE =
  'You sign in with single sign-on, so confirm at your sign-in server instead of with a password. It asks you to sign in again.';
export const CONFIRM_SSO_BUTTON = 'Confirm at your sign-in server';
export const CONFIRMING_SSO = 'Going to your sign-in server…';
export const CONFIRMED_SSO = 'Confirmed at your sign-in server. Delete within 10 minutes.';

// R6 (cabledrawer 17 Nov: ask for the admin's password, or the single sign-on confirm step, before
// lowering Keep so that backups go). All proposed, for cabledrawer.
export const deletesBackupsWords = (n: number): string =>
  n === 1 ? 'This deletes the oldest backup.' : `This deletes the ${n} oldest backups.`;
export const KEEP_FEWER_BUTTON = 'Keep fewer backups';
export const KEEP_FEWER_BUSY = 'Deleting…';
export const KEEP_FEWER_CANCEL = 'Cancel';
export const CONFIRMED_SSO_KEEP =
  'Confirmed at your sign-in server. Keep fewer backups within 10 minutes.';
// Back up now at a full folder pushes the oldest one out (R6, security review round 1). Proposed,
// for cabledrawer.
export const REPLACES_OLDEST = 'This replaces the oldest backup.';
export const BACK_UP_NOW_CONFIRM = 'Back up now';
export const CONFIRMED_SSO_BACKUP = 'Confirmed at your sign-in server. Back up within 10 minutes.';
// F257 (cabledrawer 20 Nov: "Your password" only in a pop-up when it's needed). The pop-up's
// titles and the busy words of Back up now are proposed, for cabledrawer.
export const YOUR_PASSWORD = 'Your password';
export const KEEP_FEWER_TITLE = 'Keep fewer backups?';
export const BACK_UP_NOW_TITLE = 'Back up now?';
export const BACKING_UP = 'Backing up…';
