import { afterEach, describe, expect, it, vi } from 'vitest';
import { CookPrefs, PER_STEP_KEY } from './cookPrefs.svelte';

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.removeItem(PER_STEP_KEY);
});

describe('Cook mode’s per-step ingredients switch', () => {
  it('is off by default', () => {
    expect(new CookPrefs().perStep).toBe(false);
  });

  it('is remembered on this device once switched on, and off again', () => {
    const prefs = new CookPrefs();
    prefs.setPerStep(true);
    expect(new CookPrefs().perStep).toBe(true);
    prefs.setPerStep(false);
    expect(new CookPrefs().perStep).toBe(false);
  });

  it('falls back to off when storage can’t be read, and still switches for now when it can’t be written', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const prefs = new CookPrefs();
    expect(prefs.perStep).toBe(false);
    prefs.setPerStep(true);
    expect(prefs.perStep).toBe(true);
  });
});
