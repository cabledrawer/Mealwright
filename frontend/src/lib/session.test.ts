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

  it('refuses control characters, backslashes and their encoded forms (release pass)', () => {
    const bad = [
      '/\tevil.example',
      '/\t/evil.example',
      '/\n/evil.example',
      '/\r/evil.example',
      '/\x00/evil.example',
      '/\x1f/evil.example',
      '/\x7f/evil.example',
      '\t//evil.example',
      ' //evil.example',
      '/\\',
      '/\\/evil.example',
      '/plan\\..\\..\\evil',
      '//',
      '///evil.example',
      '/%09/',
      '/%09/evil.example',
      '/%0a/evil.example',
      '/%0D/evil.example',
      '/%7f',
      '/%5C',
      '/%5c/evil.example',
      '/%2F/evil.example',
      '/%2f%2fevil.example',
      '/%E0%A4%A',
      'https:evil.example',
      'https://evil.example/',
      'javascript:alert(1)',
      'JavaScript:alert(1)',
      ' javascript:alert(1)',
      'data:text/html,hi',
      '/plan/../api/v1/me',
      '/%61pi/v1/me'
    ];
    for (const value of bad) expect(safeNext(value), JSON.stringify(value)).toBe('/');
  });

  it('gives back the address it checked, not the raw text', () => {
    expect(safeNext('/plan/./week')).toBe('/plan/week');
    expect(safeNext('/recipes/12?scale=2#steps')).toBe('/recipes/12?scale=2#steps');
    expect(safeNext('/recipes?q=t%C3%A9')).toBe('/recipes?q=t%C3%A9');
    expect(safeNext('/settings#people')).toBe('/settings#people');
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
    expect(initial('  Wren ')).toBe('W');
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
