// Your own sign-in (Settings › Your sign-in and Change password, PR A2): your password's date,
// where you're signed in, and signing out one device or everywhere else.
import { api } from '#lib/api.js';
import { dayMonthOf } from './dates.js';
import { plural } from './words.js';

/** One device where you're signed in. */
export interface SignInPlace {
  id: number;
  /** "iPhone · Safari"; null when the server didn't recognise the browser. */
  device: string | null;
  last_used_at: string;
  remember: boolean;
  this_device: boolean;
}

export interface MySignIn {
  has_password: boolean;
  password_changed_at: string | null;
  /** This device first, then the most recently used. */
  sessions: SignInPlace[];
}

export const MIN_PASSWORD = 12;

export const getMySignIn = () => api<MySignIn>('GET', '/me/sign-in');

export const changePassword = (current: string, next: string, signOutOthers: boolean) =>
  api<MySignIn>('PUT', '/me/password', {
    current_password: current,
    new_password: next,
    sign_out_others: signOutOthers
  });

export const signOutDevice = (id: number) => api<MySignIn>('DELETE', `/me/sessions/${id}`);

export const signOutEverywhereElse = () => api<MySignIn>('DELETE', '/me/sessions/others');

/** A device's name in the list: "iPhone · Safari", or "Unknown device". */
export const deviceName = (place: SignInPlace): string => place.device ?? 'Unknown device';

const DAY = 24 * 60 * 60 * 1000;

/** "Now", "5 minutes ago", "2 hours ago", "Yesterday", "3 days ago", "12 Oct". */
export function lastUsedText(at: string, now: Date = new Date()): string {
  const then = new Date(at);
  const gone = Math.max(0, now.getTime() - then.getTime());
  const minutes = Math.floor(gone / 60_000);
  if (minutes < 2) return 'Now';
  if (minutes < 60) return `${minutes} minutes ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${plural(hours, '', 's')} ago`;
  const days = Math.floor(gone / DAY);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return dayMonth(then);
}

/** "2 Oct" (in this device's time zone). */
export function dayMonth(at: Date): string {
  return dayMonthOf(at);
}

/** The line under a device's name: "Now · remembered for 30 days", "2 hours ago". */
export function placeDetail(place: SignInPlace, now: Date = new Date()): string {
  const used = place.this_device ? 'Now' : lastUsedText(place.last_used_at, now);
  return place.remember ? `${used} · remembered for 30 days` : used;
}

/** Under "Change password": "Last changed 2 Oct", or nothing before the first change. */
export function changedText(signIn: MySignIn): string {
  return signIn.password_changed_at
    ? `Last changed ${dayMonth(new Date(signIn.password_changed_at))}`
    : '';
}

/** "iPad and PC · Chrome will need the new password", for the sign-out-others switch. */
export function othersText(signIn: MySignIn): string {
  const names = signIn.sessions.filter((s) => !s.this_device).map(deviceName);
  if (names.length === 0) return '';
  const unique = [...new Set(names)];
  const list =
    unique.length === 1
      ? unique[0]
      : `${unique.slice(0, -1).join(', ')} and ${unique[unique.length - 1]}`;
  return `${list} will need the new password`;
}

/**
 * An admin's API tokens end with "sign out my other devices", "Sign out everywhere else" and a
 * password reset: a token is a sign-in too (O2 review r1; proposed, for cabledrawer).
 */
export const tokensStopText = (admin: boolean): string =>
  admin ? ' Your API tokens stop too.' : '';

/** What shows after Change password: the other devices, and an admin's tokens, when signed out. */
export function passwordChangedText(signedOutOthers: boolean, admin: boolean): string {
  if (!signedOutOthers) return 'Password changed.';
  return `Password changed. Your other devices are signed out.${admin ? ' Your API tokens have stopped.' : ''}`;
}

/** What shows after Sign out everywhere else. */
export const signedOutElseText = (admin: boolean): string =>
  `Signed out everywhere else.${admin ? ' Your API tokens have stopped.' : ''}`;

/** The live hint under New password: "8 of 12 characters. A short sentence…". */
export function lengthHint(typed: string): string {
  const count = [...typed].length;
  if (count >= MIN_PASSWORD) return 'Long enough.';
  return `${count} of ${MIN_PASSWORD} characters. A short sentence is easiest to remember.`;
}
