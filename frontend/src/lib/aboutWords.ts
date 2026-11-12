// The words of Settings → About's update parts (mockup Dark-About09-Phone; plan row X1). Every
// sentence here was accepted by cabledrawer on 12 Nov (docs/dev/words.md, "About").

import type { CheckOutcome, LastCheck } from './client/updates';
import { tagForm } from './version';

/** After this many whole months About says how old the version is (cabledrawer 12 Nov). */
export const OLD_AFTER_MONTHS = 3;

const dayMonthYear = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC'
});

/** "Released 12 Nov 2026". */
export function releasedWords(iso: string): string {
  return `Released ${dayMonthYear.format(new Date(`${iso}T12:00:00Z`))}`;
}

/** Whole months from `released` to `today` (both "2026-11-12"): 12 Nov to 11 Feb is 2. */
export function monthsBetween(released: string, today: string): number {
  const [y1, m1, d1] = released.split('-').map(Number) as [number, number, number];
  const [y2, m2, d2] = today.split('-').map(Number) as [number, number, number];
  const months = (y2 - y1) * 12 + (m2 - m1) - (d2 < d1 ? 1 : 0);
  return Math.max(0, months);
}

/** The note once the version is OLD_AFTER_MONTHS old, or null before then. */
export function ageWords(released: string, today: string): string | null {
  const months = monthsBetween(released, today);
  if (months < OLD_AFTER_MONTHS) return null;
  if (months < 24) return `This version is ${months} months old.`;
  return `This version is ${Math.floor(months / 12)} years old.`;
}

/** The releases page as it's shown: "github.com/…/mealwright/releases". */
export function shortLink(url: string): string {
  try {
    const { host, pathname } = new URL(url);
    const parts = pathname.split('/').filter(Boolean);
    return parts.length > 2 ? `${host}/…/${parts.slice(-2).join('/')}` : `${host}${pathname}`;
  } catch {
    return url;
  }
}

/** Today in this device's own day ("2026-11-12"). */
export function todayHere(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export const READY_TITLE = 'New version ready.';
export const READY_TEXT =
  'Close every Mealwright tab and window, then open it again to finish updating.';

export const UPDATES_HEADING = 'Updates (admins)';
export const CHECK_NOW = 'Check now';
export const CHECKING = 'Checking…';
export const CHECK_NOW_DETAIL =
  'One request to GitHub’s public release list; nothing about you is sent';
export const DAILY = 'Daily check';
export const UPDATE_TAG = 'Update';
/** The badge on Settings → About for an admin (the brief's words). */
export const UPDATE_AVAILABLE = 'Update available';

/** "just now", "5 minutes ago", "3 hours ago", "2 days ago". */
export function agoWords(at: string, now: Date = new Date()): string {
  const minutes = Math.floor((now.getTime() - new Date(at).getTime()) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return minutes === 1 ? '1 minute ago' : `${minutes} minutes ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? '1 hour ago' : `${hours} hours ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? '1 day ago' : `${days} days ago`;
}

/** What the first row of the Updates card says for the last answer. */
export function lastWords(
  last: LastCheck,
  now: Date = new Date()
): { title: string; detail: string; outcome: CheckOutcome } {
  const checked = `Checked ${agoWords(last.checked_at, now)}`;
  switch (last.outcome) {
    case 'newer':
      return {
        title: `Mealwright ${(last.latest ?? '').replace(/^v/, '')} is out`,
        detail: `${checked} · see what’s new`,
        outcome: last.outcome
      };
    case 'up_to_date':
      return { title: 'You have the newest version', detail: checked, outcome: last.outcome };
    case 'failed':
      return {
        title: 'Couldn’t check for updates',
        detail: `${checked}. Try again later.`,
        outcome: last.outcome
      };
  }
}

/** The Daily check row's detail and value. */
export function dailyWords(on: boolean): { detail: string; value: string } {
  return on
    ? { detail: 'Once a day · change in Privacy', value: 'On' }
    : { detail: 'Turn on in Privacy', value: 'Off' };
}

/** "Mealwright 0.9.0" under the logo (the version as the server says it, in tag form). */
export function versionHeading(version: string): string {
  return `Mealwright ${tagForm(version).replace(/^v/, '')}`;
}
