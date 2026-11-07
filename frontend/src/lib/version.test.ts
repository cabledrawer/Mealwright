import { describe, expect, it } from 'vitest';
import { VERSION, VERSION_WORDS, tagForm } from './version.js';

describe('the build’s own version', () => {
  it('is a version number, written in when the app was built', () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+/);
    expect(VERSION_WORDS).toBe(`Mealwright ${tagForm(VERSION)}`);
  });
});

describe('the version on screen is the tag (cabledrawer 7 Nov)', () => {
  it('an alpha: 0.8.0a1 is v0.8.0-alpha.1', () => {
    expect(tagForm('0.8.0a1')).toBe('v0.8.0-alpha.1');
    expect(tagForm('0.8.0a12')).toBe('v0.8.0-alpha.12');
  });

  it('a beta: 0.8.0b1 is v0.8.0-beta.1', () => {
    expect(tagForm('0.8.0b1')).toBe('v0.8.0-beta.1');
  });

  it('a release candidate: 0.8.0rc1 is v0.8.0-rc.1', () => {
    expect(tagForm('0.8.0rc1')).toBe('v0.8.0-rc.1');
  });

  it('a final version: 0.8.0 is v0.8.0', () => {
    expect(tagForm('0.8.0')).toBe('v0.8.0');
    expect(tagForm('1.10.2')).toBe('v1.10.2');
  });

  it('anything else is shown as it is', () => {
    expect(tagForm('unknown')).toBe('unknown');
    expect(tagForm('test-build')).toBe('test-build');
  });
});
