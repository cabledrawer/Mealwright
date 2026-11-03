import { afterEach, describe, expect, it } from 'vitest';
import { CHECK_MODE_STORAGE_KEY, checkMode, isCheckMode } from './checkMode.svelte';

afterEach(() => {
  localStorage.removeItem(CHECK_MODE_STORAGE_KEY);
  checkMode.reload();
});

describe('the choice of how Check looks on the phone (F141)', () => {
  it('is Focus until it is changed', () => {
    localStorage.removeItem(CHECK_MODE_STORAGE_KEY);
    checkMode.reload();
    expect(checkMode.choice).toBe('focus');
  });

  it('keeps One at a time on this device, and Focus puts the default back', () => {
    checkMode.set('one');
    expect(localStorage.getItem(CHECK_MODE_STORAGE_KEY)).toBe('one');
    checkMode.choice = 'focus';
    checkMode.reload();
    expect(checkMode.choice).toBe('one');
    checkMode.set('focus');
    expect(localStorage.getItem(CHECK_MODE_STORAGE_KEY)).toBeNull();
    checkMode.reload();
    expect(checkMode.choice).toBe('focus');
  });

  it('reads anything else it finds as Focus', () => {
    localStorage.setItem(CHECK_MODE_STORAGE_KEY, 'everything');
    checkMode.reload();
    expect(checkMode.choice).toBe('focus');
    expect(isCheckMode('one')).toBe(true);
    expect(isCheckMode('all')).toBe(false);
  });
});
