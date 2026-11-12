import { describe, expect, it } from 'vitest';
import {
  changedText,
  deviceName,
  lastUsedText,
  lengthHint,
  othersText,
  passwordChangedText,
  signedOutElseText,
  tokensStopText,
  placeDetail,
  type MySignIn,
  type SignInPlace
} from './mySignIn';

const NOW = new Date('2026-11-11T12:00:00Z');
const ago = (minutes: number) => new Date(NOW.getTime() - minutes * 60_000).toISOString();

const place = (extra: Partial<SignInPlace>): SignInPlace => ({
  id: 1,
  device: 'iPad · Safari',
  last_used_at: ago(0),
  remember: false,
  this_device: false,
  ...extra
});

describe('when a device was last used', () => {
  it('reads as a person would say it', () => {
    expect(lastUsedText(ago(1), NOW)).toBe('Now');
    expect(lastUsedText(ago(5), NOW)).toBe('5 minutes ago');
    expect(lastUsedText(ago(60), NOW)).toBe('1 hour ago');
    expect(lastUsedText(ago(150), NOW)).toBe('2 hours ago');
    expect(lastUsedText(ago(60 * 24), NOW)).toBe('Yesterday');
    expect(lastUsedText(ago(60 * 24 * 3), NOW)).toBe('3 days ago');
    expect(lastUsedText('2026-10-12T10:00:00Z', NOW)).toBe('12 Oct');
  });

  it('this device is always "Now", and remembering says so', () => {
    expect(
      placeDetail(place({ this_device: true, last_used_at: ago(90), remember: true }), NOW)
    ).toBe('Now · remembered for 30 days');
    expect(placeDetail(place({ last_used_at: ago(120) }), NOW)).toBe('2 hours ago');
  });
});

describe('the words around the password', () => {
  const signIn = (sessions: SignInPlace[], changed: string | null = null): MySignIn => ({
    has_password: true,
    password_changed_at: changed,
    sessions
  });

  it('a browser it doesn’t know is an unknown device', () => {
    expect(deviceName(place({ device: null }))).toBe('Unknown device');
  });

  it('names the other devices once each', () => {
    const here = place({ id: 1, device: 'iPhone · Safari', this_device: true });
    expect(othersText(signIn([here]))).toBe('');
    expect(othersText(signIn([here, place({ id: 2 })]))).toBe(
      'iPad · Safari will need the new password'
    );
    expect(
      othersText(
        signIn([
          here,
          place({ id: 2 }),
          place({ id: 3 }),
          place({ id: 4, device: 'PC · Chrome' }),
          place({ id: 5, device: null })
        ])
      )
    ).toBe('iPad · Safari, PC · Chrome and Unknown device will need the new password');
  });

  it('says when it last changed, only once it has', () => {
    expect(changedText(signIn([]))).toBe('');
    expect(changedText(signIn([], '2026-10-02T10:00:00Z'))).toBe('Last changed 2 Oct');
  });

  it('counts characters, not code units, towards 12', () => {
    expect(lengthHint('kitchen!')).toBe(
      '8 of 12 characters. A short sentence is easiest to remember.'
    );
    expect(lengthHint('🍅🍅🍅🍅🍅🍅🍅🍅🍅🍅🍅')).toMatch(/^11 of 12/);
    expect(lengthHint('a long sentence')).toBe('Long enough.');
  });
});

describe('what happens to an admin’s API tokens (proposed, for cabledrawer)', () => {
  it('says so to admins only', () => {
    expect(tokensStopText(true)).toBe(' Your API tokens stop too.');
    expect(tokensStopText(false)).toBe('');
  });

  it('adds it to what a password change and Sign out everywhere else say', () => {
    expect(passwordChangedText(true, false)).toBe(
      'Password changed. Your other devices are signed out.'
    );
    expect(passwordChangedText(true, true)).toBe(
      'Password changed. Your other devices are signed out. Your API tokens have stopped.'
    );
    expect(passwordChangedText(false, true)).toBe('Password changed.');
    expect(signedOutElseText(false)).toBe('Signed out everywhere else.');
    expect(signedOutElseText(true)).toBe(
      'Signed out everywhere else. Your API tokens have stopped.'
    );
  });
});
