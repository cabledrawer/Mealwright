import { describe, expect, it } from 'vitest';
import { forgetLoaded, rememberToForget } from './forgetWhenLoaded';

describe('forgetWhenLoaded', () => {
  it('does nothing for a memory that was never loaded', () => {
    expect(() => forgetLoaded('never-loaded')).not.toThrow();
  });

  it('forgets what was added when it was loaded', () => {
    let held = 'a household’s data';
    rememberToForget('test-memory', () => (held = ''));
    forgetLoaded('test-memory');
    expect(held).toBe('');
  });

  it('forgets the Privacy memory without the shell loading it', async () => {
    const { privacy } = await import('./privacy.svelte');
    privacy.loaded = true;
    forgetLoaded('privacy');
    expect(privacy.loaded).toBe(false);
  });
});
