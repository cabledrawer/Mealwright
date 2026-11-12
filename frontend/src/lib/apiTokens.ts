// Settings › Sign-in › API tokens (0.9 O2; the mockup Dark-ApiTokens09): an admin makes a
// token for another app, sees it once, and deletes tokens. The words are proposed, for cabledrawer.
import { api } from '#lib/api.js';
import { addDays, dayMonthWords, isRealDay } from '#lib/dates.js';

export type TokenScope = 'read' | 'full';

export interface ApiToken {
  id: number;
  name: string;
  scope: TokenScope;
  created_at: string;
  /** To the minute; null when it's never been used. */
  last_used_at: string | null;
  /** The last day it works; null when it never ends. */
  expires_on: string | null;
}

export interface ApiTokens {
  /** Newest first. */
  tokens: ApiToken[];
  /** Today in the household's time zone. */
  today: string;
}

export interface MadeToken {
  /** The token itself: shown once, never again. */
  token: string;
  made: ApiToken;
}

export const LONGEST_NAME = 60;

export const getApiTokens = () => api<ApiTokens>('GET', '/api-tokens');

export const makeApiToken = (name: string, scope: TokenScope, expiresOn: string | null) =>
  api<MadeToken>('POST', '/api-tokens', { name, scope, expires_on: expiresOn });

export const deleteApiToken = (id: number) => api<void>('DELETE', `/api-tokens/${id}`);

/** The Expires chips, as drawn. */
export type Ends = 'never' | 'month' | 'year' | 'pick';

export const ENDS: { value: Ends; label: string }[] = [
  { value: 'never', label: 'Never' },
  { value: 'month', label: '30 days' },
  { value: 'year', label: '1 year' },
  { value: 'pick', label: 'Pick a date' }
];

/** The last day a new token works, from the chip (and the picked date), or null: never. */
export function lastDay(ends: Ends, today: string, picked: string): string | null {
  if (ends === 'never') return null;
  if (ends === 'month') return addDays(today, 30);
  if (ends === 'year') return addDays(today, 365);
  return picked;
}

/** "31 Dec 2026". */
export function longDate(iso: string): string {
  if (!isRealDay(iso)) return '';
  return `${dayMonthWords(iso)} ${iso.slice(0, 4)}`;
}

/** This device's date for a moment, "2026-11-12". */
function localDay(at: Date): string {
  const month = String(at.getMonth() + 1).padStart(2, '0');
  const day = String(at.getDate()).padStart(2, '0');
  return `${at.getFullYear()}-${month}-${day}`;
}

/** "never used", "used just now", "used 5 min ago", "used today", "used yesterday", "used 2 Nov". */
export function usedWords(at: string | null, now: Date = new Date()): string {
  if (at === null) return 'never used';
  const then = new Date(at);
  const minutes = Math.floor(Math.max(0, now.getTime() - then.getTime()) / 60_000);
  if (minutes < 2) return 'used just now';
  if (minutes < 60) return `used ${minutes} min ago`;
  const day = localDay(then);
  const today = localDay(now);
  if (day === today) return 'used today';
  if (addDays(day, 1) === today) return 'used yesterday';
  return `used ${dayMonthWords(day)}`;
}

/** "never expires", "expires 31 Dec 2026", "ended 2 Nov 2026". */
export function endsWords(token: ApiToken, today: string): string {
  if (token.expires_on === null) return 'never expires';
  if (token.expires_on < today) return `ended ${longDate(token.expires_on)}`;
  return `expires ${longDate(token.expires_on)}`;
}

/** The line under a token's name: "Read-only · never expires · used 5 min ago". */
export function tokenDetail(token: ApiToken, today: string, now: Date = new Date()): string {
  const can = token.scope === 'full' ? 'Full access' : 'Read-only';
  return `${can} · ${endsWords(token, today)} · ${usedWords(token.last_used_at, now)}`;
}
