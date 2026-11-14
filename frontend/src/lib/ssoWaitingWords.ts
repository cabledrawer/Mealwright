// "Who is this?" on Settings → Household (0.9.5 Pe3/M2; mockup Dark-HouseholdWaiting095-Phone):
// a single sign-on sign-in that matches nobody waits until an admin says who it is (cabledrawer
// 13 Nov). The mockup's words; the ones it doesn't show are proposed, for cabledrawer
// (docs/dev/words.md, section 81).

import { whenWords } from '#lib/yourDataWords.js';
import type { Person, WaitingSignIn } from '#lib/client/people.js';

/** "1 sign-in waiting", "3 sign-ins waiting". */
export const waitingTitle = (count: number): string =>
  count === 1 ? '1 sign-in waiting' : `${count} sign-ins waiting`;

/** "today at 20:10", "yesterday at 09:00", "Mon at 20:10", "12 Nov at 20:10": in the
 *  household's time zone, like every time in the app. */
export function atWords(iso: string, now: Date, zone: string | null): string {
  const when = whenWords(iso, now, zone);
  const clock = when.slice(when.lastIndexOf(' ') + 1);
  const day = when.slice(0, when.lastIndexOf(' '));
  const said = day === 'Today' || day === 'Yesterday' ? day.toLowerCase() : day;
  return `${said} at ${clock}`;
}

/** The banner's line: "lorna.s signed in with single sign-on at 20:10 and doesn't match
 *  anyone here." (today's time on its own, as the mockup has it). */
export function waitingLine(waiting: WaitingSignIn, now: Date, zone: string | null): string {
  const at = atWords(waiting.signed_in_at, now, zone).replace(/^today /, '');
  return `${waiting.username} signed in with single sign-on ${at} and doesn’t match anyone here.`;
}

/** The sheet's title: "Who is lorna.s?". */
export const whoTitle = (waiting: WaitingSignIn): string => `Who is ${waiting.username}?`;

/** The sheet's line under its title. */
export function whoLine(waiting: WaitingSignIn, now: Date, zone: string | null): string {
  const at = atWords(waiting.signed_in_at, now, zone);
  return `Signed in with single sign-on ${at}. Their username doesn’t match anyone here, so Mealwright let nobody in until you say who it is.`;
}

/**
 * The people a waiting sign-in can be linked to: anyone without a shared login or a link to
 * another account at the sign-in server already; an admin only for a sign-in the sign-in
 * server's groups make an admin (the server says the same).
 */
export function linkable(people: Person[], waiting: WaitingSignIn): Person[] {
  return people.filter((person) => {
    const login = person.login;
    if (!login) return true;
    if (login.shared || login.sso_linked) return false;
    return login.role !== 'admin' || waiting.role === 'admin';
  });
}

/** "username lorna" or "no login", at the right of each person to pick. */
export const pickDetail = (person: Person): string =>
  person.login ? `username ${person.login.username}` : 'no login';

export const NEW_PERSON = 'A new person';
export const REFUSE = 'Not someone I know: refuse';

/** The main button follows the pick: "Link to Lorna"; "Add a new person" and "Choose who it
 *  is" are proposed, for cabledrawer. */
export function linkButton(picked: Person | 'new' | null): string {
  if (picked === null) return 'Choose who it is';
  if (picked === 'new') return 'Add a new person';
  return `Link to ${picked.name}`;
}

// The Person page's "Single sign-on" row (mockup Dark-Person095-Phone), for an admin while
// single sign-on is set up.

export const SSO_ROW = 'Single sign-on';
export const UNLINK = 'Unlink';
export const LINK_BY_HAND = 'Link…';
export const NOT_LINKED_LINE =
  'Not linked. Linked automatically when the sign-in server’s username is the same as here; otherwise link by hand.';

/** "Linked to lorna.s on your sign-in server", the username in bold. Linked before Mealwright
 *  kept the sign-in server's username (proposed, for cabledrawer): "Linked to an account on your
 *  sign-in server". */
export function linkedParts(username: string | null | undefined): [string, string | null, string] {
  return username
    ? ['Linked to ', username, ' on your sign-in server']
    : ['Linked to an account on your sign-in server', null, ''];
}

/** The sheet Link… opens (proposed, for cabledrawer): the sign-ins waiting, to pick this person's. */
export const linkSheetTitle = (name: string): string => `Link ${name} to a sign-in`;
export const linkSheetLine = (name: string): string =>
  `These sign-ins with single sign-on are waiting for an admin. Pick the one that is ${name}.`;
export const nobodyWaiting = (name: string): string =>
  `Nobody is waiting. Ask ${name} to sign in with single sign-on: their sign-in then waits here for you to link it.`;

/** The waiting sign-ins this person can be linked to: an admin only to one the sign-in
 *  server's groups make an admin (the server says the same). */
export function signInsFor(person: Person, waiting: WaitingSignIn[]): WaitingSignIn[] {
  return waiting.filter((w) => linkable([person], w).length === 1);
}

/** "signed in today at 20:10", at the right of each sign-in to pick. */
export const signedInDetail = (waiting: WaitingSignIn, now: Date, zone: string | null): string =>
  `signed in ${atWords(waiting.signed_in_at, now, zone)}`;

/** The sheet's main button: "Link to lorna.s", or "Choose a sign-in" before a pick. */
export const linkToButton = (picked: WaitingSignIn | null): string =>
  picked ? `Link to ${picked.username}` : 'Choose a sign-in';

export const CLOSE = 'Close';
