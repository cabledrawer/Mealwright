import { afterEach, describe, expect, it } from 'vitest';
import { takeLinkSecret } from './linkSecret';

describe('takeLinkSecret', () => {
  const before = location.pathname + location.search;

  afterEach(() => {
    history.replaceState(history.state, '', before);
  });

  it('takes the secret after the # and clears it from the address bar', () => {
    history.replaceState(history.state, '', `${before}#Xp4-secret_9`);
    expect(takeLinkSecret()).toBe('Xp4-secret_9');
    expect(location.hash).toBe('');
    expect(location.href).not.toContain('Xp4-secret_9');
    expect(location.pathname + location.search).toBe(before);
  });

  it('is empty without a #, and leaves the address alone', () => {
    history.replaceState(history.state, '', before);
    expect(takeLinkSecret()).toBe('');
    expect(location.pathname + location.search).toBe(before);
  });
});
