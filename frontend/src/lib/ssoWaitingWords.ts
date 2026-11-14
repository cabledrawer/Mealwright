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
