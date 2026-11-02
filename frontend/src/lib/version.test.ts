import { describe, expect, it } from 'vitest';
import { VERSION, VERSION_WORDS } from './version.js';

describe('the build’s own version', () => {
  it('is a version number, written in when the app was built', () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+/);
    expect(VERSION_WORDS).toBe(`Mealwright ${VERSION}`);
  });
});
