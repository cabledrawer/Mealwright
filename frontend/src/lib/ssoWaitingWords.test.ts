// "Who is this?" words (0.9.5 Pe3/M2, mockup Dark-HouseholdWaiting095-Phone).
import { describe, expect, it } from 'vitest';
import type { Person, WaitingSignIn } from '#lib/client/people.js';
import { person } from '#lib/testing/fakePeople.js';
import {
  atWords,
  linkButton,
  linkToButton,
  linkable,
  linkedParts,
  pickDetail,
  signInsFor,
  signedInDetail,
  waitingLine,
  waitingTitle,
  whoLine,
  whoTitle
} from './ssoWaitingWords';

const NOW = new Date('2026-11-16T21:00:00Z');
const LORNA_S: WaitingSignIn = {
  id: 7,
  username: 'lorna.s',
  signed_in_at: '2026-11-16T20:10:00Z',
  role: 'member'
};

const login = (username: string, extra: Partial<NonNullable<Person['login']>> = {}) => ({
  username,
  role: 'member' as const,
  shared: false,
  has_password: true,
  signs_in: true,
  link_pending: false,
  link_used_at: null,
  reset_pending: false,
  ...extra
});

describe('"Who is this?" words', () => {
  it('says how many wait, and when each signed in, as the mockup does', () => {
    expect(waitingTitle(1)).toBe('1 sign-in waiting');
    expect(waitingTitle(3)).toBe('3 sign-ins waiting');
    expect(waitingLine(LORNA_S, NOW, 'Europe/London')).toBe(
      'lorna.s signed in with single sign-on at 20:10 and doesn’t match anyone here.'
    );
    expect(whoTitle(LORNA_S)).toBe('Who is lorna.s?');
    expect(whoLine(LORNA_S, NOW, 'Europe/London')).toBe(
      'Signed in with single sign-on today at 20:10. Their username doesn’t match anyone here, so Mealwright let nobody in until you say who it is.'
    );
  });

  it('says the day when it was not today, in the household’s time zone', () => {
    const later = new Date('2026-11-17T09:00:00Z');
    expect(atWords(LORNA_S.signed_in_at, later, 'Europe/London')).toBe('yesterday at 20:10');
    expect(waitingLine(LORNA_S, later, 'Europe/London')).toContain('yesterday at 20:10');
    expect(atWords(LORNA_S.signed_in_at, NOW, 'Asia/Kolkata')).toBe('today at 01:40');
  });

  it('offers only people a sign-in can be linked to', () => {
    const sam = person(1, 'Sam', { is_me: true, login: login('sam', { role: 'admin' }) });
    const lorna = person(2, 'Lorna', { login: login('lorna') });
    const noor = person(3, 'Noor');
    const tablet = person(4, 'Tablet', { login: login('tablet', { shared: true }) });
    const linked = person(5, 'Pat', { login: login('pat', { sso_linked: true }) });
    const everyone = [sam, lorna, noor, tablet, linked];
    expect(linkable(everyone, LORNA_S).map((p) => p.name)).toEqual(['Lorna', 'Noor']);
    const anAdmin = { ...LORNA_S, role: 'admin' as const };
    expect(linkable(everyone, anAdmin).map((p) => p.name)).toEqual(['Sam', 'Lorna', 'Noor']);
    expect(pickDetail(lorna)).toBe('username lorna');
    expect(pickDetail(noor)).toBe('no login');
  });

  it('the main button follows the pick', () => {
    expect(linkButton(person(2, 'Lorna'))).toBe('Link to Lorna');
    expect(linkButton('new')).toBe('Add a new person');
    expect(linkButton(null)).toBe('Choose who it is');
  });
});

describe('The Person page’s single sign-on words', () => {
  it('says who they are linked to, as the mockup does', () => {
    expect(linkedParts('lorna.s')).toEqual(['Linked to ', 'lorna.s', ' on your sign-in server']);
    expect(linkedParts(null).join('')).toBe('Linked to an account on your sign-in server');
  });

  it('offers an admin only sign-ins the groups make an admin', () => {
    const member = person(2, 'Noor', {
      login: {
        username: 'noor',
        role: 'member',
        shared: false,
        has_password: false,
        signs_in: true,
        link_pending: false,
        link_used_at: null,
        reset_pending: false
      }
    });
    const admin: Person = { ...member, login: { ...member.login!, role: 'admin' } };
    const asAdmin: WaitingSignIn = { ...LORNA_S, id: 8, role: 'admin' };
    expect(signInsFor(member, [LORNA_S, asAdmin])).toEqual([LORNA_S, asAdmin]);
    expect(signInsFor(admin, [LORNA_S, asAdmin])).toEqual([asAdmin]);
    expect(signInsFor(person(3, 'Sam'), [LORNA_S])).toEqual([LORNA_S]);
  });

  it('says when each signed in, and the button follows the pick', () => {
    expect(signedInDetail(LORNA_S, NOW, 'UTC')).toBe('signed in today at 20:10');
    expect(linkToButton(null)).toBe('Choose a sign-in');
    expect(linkToButton(LORNA_S)).toBe('Link to lorna.s');
  });
});
