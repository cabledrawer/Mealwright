// Changes still waiting on this phone for whoever was last signed in here, and how the app
// words them when signing in (sync protocol 11.5, section 16 decision 4) and signing out
// (section 12).
//
// A phone database that can't be read is never "nothing waiting": the readers here say
// UNREADABLE, and the app then wipes nothing, writes nothing over `meta`, and says so.

import { readSignedIn, type SignedIn } from './device';
import { phoneExists, readPhone, UNREADABLE, type QueueEntry, type Unreadable } from './phone';
import { signOutPending } from './signOutPending';

export { UNREADABLE, type Unreadable } from './phone';

export interface Held {
  /** Whose changes they are. */
  who: SignedIn;
  count: number;
  /**
   * Exactly which changes (their action IDs). "Carry on and lose them" loses only these: a
   * change queued since, in another tab, is never lost without its own warning.
   */
  ids: string[];
}

const readQueueHere = () => readPhone((db) => db.getAll('queue') as Promise<QueueEntry[]>);

/**
 * Waiting changes of the person last signed in here; null when there are none. UNREADABLE
 * when the phone database couldn't be read: not the same as none.
 */
export async function heldChanges(): Promise<Held | null | Unreadable> {
  // Signed out (perhaps offline): this browser has been wiped.
  if (signOutPending()) return null;
  try {
    if (!(await phoneExists())) return null;
    const who = await readSignedIn();
    if (!who) return null;
    const theirs = (await readQueueHere()).filter((e) => e.login_id === who.id);
    return theirs.length
      ? { who, count: theirs.length, ids: theirs.map((e) => e.action.id) }
      : null;
  } catch {
    return UNREADABLE;
  }
}

/**
 * How many of `loginId`'s changes are waiting in the phone database (signing out, section
 * 12). UNREADABLE when it couldn't be read: not the same as none.
 */
export async function storedWaiting(loginId: number): Promise<number | Unreadable> {
  try {
    if (!(await phoneExists())) return 0;
    return (await readQueueHere()).filter((e) => e.login_id === loginId).length;
  } catch {
    return UNREADABLE;
  }
}

const changes = (n: number) => `${n} ${n === 1 ? 'change' : 'changes'}`;

/** "phone" with the bottom tabs, "computer" with the sidebar (by layout, as everywhere). */
export type Device = 'phone' | 'computer';

/** The sign-in ran out; the same person is signing back in. */
export const keptText = (n: number, device: Device = 'phone') =>
  `Please sign in again. Your ${changes(n)} ${n === 1 ? 'is' : 'are'} kept on this ${device}.`;

/** Someone else is about to sign in on a device holding `name`'s changes. */
export const waitingForText = (name: string, n: number, device: Device = 'phone') =>
  `${name}'s ${changes(n)} ${n === 1 ? 'is' : 'are'} waiting on this ${device}. Sign in as ${name} to send ${n === 1 ? 'it' : 'them'}.`;

/**
 * The phone database couldn't be read, so whether anyone's changes are waiting isn't known:
 * nothing is wiped, and nobody new is let in over it.
 */
export const cantCheckText = (device: Device = 'phone') =>
  `This ${device} couldn't check for changes waiting to be sent. Nothing has been deleted.`;

/** The server answered, but didn't end the session (section 12). */
export const unfinishedText = (device: Device = 'phone') =>
  `Couldn't finish signing out on this ${device}.`;

/** The warning before a different login carries on. */
export const loseOthersText = (name: string, n: number) =>
  `${name}'s ${changes(n)} ${n === 1 ? "hasn't" : "haven't"} been sent yet. If you carry on, ${n === 1 ? "it's" : "they're"} lost.`;

/** The warning before signing out (section 12). */
export const loseOnSignOutText = (n: number) =>
  `${changes(n)} ${n === 1 ? "hasn't" : "haven't"} been sent yet. If you sign out now, ${n === 1 ? "it's" : "they're"} lost.`;

/** Added to that warning when "Try sending now" didn't get them all through. */
export const STILL_CANT_REACH = "Still can't reach your server.";

/** The same username as `who`, as the server compares them (trimmed, any case). */
export function sameUsername(typed: string, who: SignedIn): boolean {
  return typed.trim().toLowerCase() === who.username.trim().toLowerCase();
}

/**
 * The username the app just turned away because another login's changes are waiting here
 * (the (app) layout): the sign-in page fills it in once, so the warning names the right
 * person. Kept in memory only, never stored.
 */
let turnedAway = '';

export function turnAway(username: string): void {
  turnedAway = username;
}

/** The username turned away, once ('' when none). */
export function takeTurnedAway(): string {
  const username = turnedAway;
  turnedAway = '';
  return username;
}
