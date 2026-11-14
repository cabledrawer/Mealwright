// The words for people on Settings → Household (0.9 A1): portions, the line under a name, and
// the avatar's initial.

import { describe, expect, it } from 'vitest';
import { initial, personLine, portionWords, type Person } from './people';

const joss = (extra: Partial<Person> = {}): Person => ({
  id: 3,
  name: 'Joss',
  colour: 'amber',
  portion_quarters: 2,
  login: null,
  is_me: false,
  created_at: '2026-11-03T10:00:00Z',
  created_by_name: 'Tess',
  ...extra
});

const login = (extra: Partial<NonNullable<Person['login']>> = {}) => ({
  username: 'joss',
  role: 'member' as const,
  shared: false,
  has_password: true,
  signs_in: true,
  link_pending: false,
  link_used_at: null,
  ...extra
});

describe('portionWords', () => {
  it('says quarters as fractions, singular up to one portion', () => {
    expect(portionWords(1)).toBe('¼ portion');
    expect(portionWords(2)).toBe('½ portion');
    expect(portionWords(3)).toBe('¾ portion');
    expect(portionWords(4)).toBe('1 portion');
    expect(portionWords(6)).toBe('1½ portions');
    expect(portionWords(8)).toBe('2 portions');
  });
});

describe('personLine', () => {
  it('says profile only, a pending link, signing in and a shared login', () => {
    expect(personLine(joss())).toBe('Profile only · ½ portion');
    expect(
      personLine(
        joss({ login: login({ has_password: false, signs_in: false, link_pending: true }) })
      )
    ).toBe('Member · sign-in link sent · ½ portion');
    expect(personLine(joss({ portion_quarters: 4, login: login({ role: 'admin' }) }))).toBe(
      'Admin · signs in · 1 portion'
    );
    expect(personLine(joss({ login: login({ shared: true }) }))).toBe('Shared login · Member');
  });

  it('says signs in for a single sign-on login too, which has no password', () => {
    const sso = login({ has_password: false, signs_in: true });
    expect(personLine(joss({ portion_quarters: 4, login: sso }))).toBe(
      'Member · signs in · 1 portion'
    );
  });
});

describe('initial', () => {
  it('is the first letter, in capitals, and copes with an empty name', () => {
    expect(initial(' joss')).toBe('J');
    expect(initial('Émile')).toBe('É');
    expect(initial('')).toBe('?');
  });
});
