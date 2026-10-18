// Changes still waiting on this phone for whoever was last signed in here, and how the app
// words them when signing in (sync protocol 11.5, section 16 decision 4) and signing out
// (section 12).

import { lastSignedIn, type SignedIn } from './device';
import { phoneExists } from './phone';
import { readQueue } from './store';

export interface Held {
  /** Whose changes they are. */
  who: SignedIn;
  count: number;
}

/** Waiting changes of the person last signed in here; null when there are none. */
export async function heldChanges(): Promise<Held | null> {
  try {
    if (!(await phoneExists())) return null;
    const who = await lastSignedIn();
    if (!who) return null;
    const count = (await readQueue()).filter((e) => e.login_id === who.id).length;
    return count ? { who, count } : null;
  } catch {
    return null;
  }
}

const changes = (n: number) => `${n} ${n === 1 ? 'change' : 'changes'}`;

/** The sign-in ran out; the same person is signing back in. */
export const keptText = (n: number) =>
  `Please sign in again. Your ${changes(n)} ${n === 1 ? 'is' : 'are'} kept on this phone.`;

/** Someone else is about to sign in on a phone holding `name`'s changes. */
export const waitingForText = (name: string, n: number) =>
  `${name}'s ${changes(n)} ${n === 1 ? 'is' : 'are'} waiting on this phone. Sign in as ${name} to send ${n === 1 ? 'it' : 'them'}.`;

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
