// Settings → Household (backend api/v1/people.py, 0.9 A1): the people of the household, their
// colours and portions, who signs in, and "Who's this?" on a shared login. Everyone can look;
// only an admin can change anything.

import { api } from '#lib/api.js';
import type { Change } from './types';

export const COLOURS = ['amber', 'green', 'violet', 'blue', 'peach'] as const;
export type Colour = (typeof COLOURS)[number];
export type Role = 'admin' | 'member';

export interface PersonLogin {
  username: string;
  role: Role;
  /** A login the household shares (a kitchen tablet): it asks "Who's this?". */
  shared: boolean;
  /** False until the person has used their sign-in link. */
  has_password: boolean;
  /** Signs in, by password or by single sign-on: false only while a sign-in link waits or has run out. */
  signs_in: boolean;
  /** An unused sign-in link that hasn't run out. */
  link_pending: boolean;
  /** When a sign-in or Reset password link last set the password (UTC), or null. */
  link_used_at: string | null;
  /** An unused Reset password link that hasn't run out. */
  reset_pending: boolean;
  /** Linked to an account at the household's sign-in server (0.9.5 Pe3/M2). */
  sso_linked?: boolean;
  /** That account's username at the sign-in server, once it has signed in here. */
  sso_username?: string | null;
}

export interface Person {
  id: number;
  name: string;
  colour: Colour | null;
  /** How much they eat, in quarter portions: 4 is one portion. */
  portion_quarters: number;
  login: PersonLogin | null;
  /** The signed-in login's own person. */
  is_me: boolean;
  created_at: string;
  created_by_name: string;
}

export interface People {
  people: Person[];
  /** False for a member: they see everyone and can't change anything. */
  can_change: boolean;
  /** The household switch: shared logins ask "Who's this?". */
  ask_whos_this: boolean;
  /** The change just made (for its Undo); null when nothing changed or on a plain look. */
  change?: Change | null;
  /** "Who is this?" (0.9.5 Pe3/M2): single sign-on sign-ins that match nobody, newest first.
   *  Empty for a member. */
  waiting?: WaitingSignIn[];
}

/** A single sign-on sign-in waiting for an admin to say who it is. */
export interface WaitingSignIn {
  id: number;
  /** Its username at the sign-in server. */
  username: string;
  /** Its last sign-in here (UTC). */
  signed_in_at: string;
  /** What the sign-in server's groups made it: only an "admin" one can be linked to an admin. */
  role: Role;
}

export interface PersonChange {
  name?: string;
  colour?: Colour | null;
  portion_quarters?: number;
  role?: Role;
  shared?: boolean;
}

export interface SignInLink {
  /** "/join#<secret>": shown once, never stored on the server. The secret follows a `#`, so
   *  opening the link never sends it to the server (cabledrawer 13 Nov). */
  path: string;
  expires_at: string;
}

export interface Pickable {
  id: number;
  name: string;
  colour: Colour | null;
}

export interface WhosThis {
  /** True on a shared login while the household has the switch on. */
  ask: boolean;
  /** Who was picked on this device, if anyone. */
  picked: number | null;
  people: Pickable[];
}

/** What the link page learns before the password is set: no name or username (cabledrawer 13 Nov). */
export interface JoinLink {
  /** "join": a sign-in link (a first password); "reset": a Reset password link. */
  kind: 'join' | 'reset';
  expires_at: string;
  min_password: number;
}

/** After the password is set: the username to sign in with. */
export interface Joined {
  username: string;
}

export const getPeople = () => api<People>('GET', '/people');

export const addPerson = (name: string, colour: Colour | null, portion_quarters: number) =>
  api<People>('POST', '/people', { name, colour, portion_quarters });

export const changePerson = (id: number, change: PersonChange) =>
  api<People>('PATCH', `/people/${id}`, change);

export const removePerson = (id: number) => api<People>('DELETE', `/people/${id}`);

export const giveLogin = (id: number, username: string, role: Role) =>
  api<SignInLink>('POST', `/people/${id}/login`, { username, role });

export const takeBackLogin = (id: number) => api<void>('DELETE', `/people/${id}/login`);

/** Reset password (Pe1): a one-time link, for 24 hours, where the person chooses a new one. */
export const resetPassword = (id: number) =>
  api<SignInLink>('POST', `/people/${id}/reset-password`);

/** Cancel a Reset password link someone made for you: your password stays as it is. */
export const cancelMyResetLink = () => api<void>('DELETE', '/me/reset-link');

export const setAskWhosThis = (on: boolean) => api<People>('PUT', '/people/ask-whos-this', { on });

/** "Who is this?": link a waiting sign-in to a person, or to a new person (null). */
export const linkSignIn = (id: number, member_id: number | null) =>
  api<People>('POST', `/people/sso-accounts/${id}/link`, { member_id });

/** "Not someone I know: refuse": it can't sign in until an admin links it after all. */
export const refuseSignIn = (id: number) => api<People>('POST', `/people/sso-accounts/${id}/refuse`);

export const getWhosThis = () => api<WhosThis>('GET', '/whos-this');

/** Null is "Just looking": nobody picked. */
export const pickWho = (member_id: number | null) =>
  api<WhosThis>('PUT', '/whos-this', { member_id });

// The link's secret goes in the body, never in an address (cabledrawer 13 Nov).
export const getJoinLink = (token: string) =>
  api<JoinLink>('POST', '/join/look', { token }, { signingIn: true });

export const join = (token: string, password: string) =>
  api<Joined>('POST', '/join', { token, password }, { signingIn: true });

/** "½ portion", "1 portion", "1½ portions" (cabledrawer 12 Nov). */
export function portionWords(quarters: number): string {
  const whole = Math.floor(quarters / 4);
  const part = ['', '¼', '½', '¾'][quarters % 4];
  const number = whole === 0 ? part : `${whole}${part}`;
  return `${number} ${quarters <= 4 ? 'portion' : 'portions'}`;
}

/** The chips under "Eats": ¼, ½, 1, 1½ and 2 portions. */
export const PORTION_CHOICES = [1, 2, 4, 6, 8] as const;

/** The first letter of a name, for the avatar. */
export const initial = (name: string): string =>
  (Array.from(name.trim())[0] ?? '?').toLocaleUpperCase();

/** The small line under a name on the Household screen (cabledrawer 12 Nov). */
export function personLine(person: Person): string {
  const login = person.login;
  const portion = portionWords(person.portion_quarters);
  if (!login) return `Profile only · ${portion}`;
  const role = login.role === 'admin' ? 'Admin' : 'Member';
  if (login.shared) return `Shared login · ${role}`;
  if (!login.signs_in) return `${role} · sign-in link sent · ${portion}`;
  return `${role} · signs in · ${portion}`;
}
