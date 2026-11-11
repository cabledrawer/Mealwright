import { describe, expect, it } from 'vitest';
import { connection, initial, safeNext, signInPath } from './session.svelte';

describe('safeNext', () => {
  it('returns to pages of the app', () => {
    expect(safeNext('/plan')).toBe('/plan');
    expect(safeNext('/recipes/12?scale=2')).toBe('/recipes/12?scale=2');
  });

  it('never leaves the app', () => {
    for (const bad of ['https://evil.example', '//evil.example', '/\\evil.example', 'plan', '']) {
      expect(safeNext(bad), bad).toBe('/');
    }
    expect(safeNext(null)).toBe('/');
    expect(safeNext(undefined)).toBe('/');
  });

  it('never goes to the API or back to signing in', () => {
    expect(safeNext('/api/v1/me')).toBe('/');
    expect(safeNext('/sign-in')).toBe('/');
    expect(safeNext('/sign-in?next=/plan')).toBe('/');
    expect(safeNext('/setup')).toBe('/');
    expect(safeNext('/apis-of-the-world')).toBe('/apis-of-the-world');
  });
});

describe('signInPath', () => {
  it('remembers where the person was heading', () => {
    expect(signInPath('/pantry')).toBe('/sign-in?next=%2Fpantry');
    expect(signInPath('/')).toBe('/sign-in');
  });
});

describe('initial', () => {
  it('is the first letter, as a capital', () => {
    expect(initial('tess')).toBe('T');
    expect(initial('  Remy ')).toBe('R');
    expect(initial('Ésha')).toBe('É');
    expect(initial('')).toBe('?');
  });
});

describe('connection', () => {
  it('is secure on https:// and localhost, whatever the setting', () => {
    expect(connection(true, false)).toBe('secure');
    expect(connection(true, true)).toBe('secure');
  });

  it('on plain http:// depends on what the admin allowed', () => {
    expect(connection(false, true)).toBe('plain-allowed');
    expect(connection(false, false)).toBe('plain-refused');
  });
});
