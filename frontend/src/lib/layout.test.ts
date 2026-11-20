import { describe, expect, it } from 'vitest';
import { DESKTOP_QUERY, PHONE_QUERY, isPhone } from './layout';

describe('the breakpoint (FE29)', () => {
  it('is one line: phone below 768 px, computer from 768 px', () => {
    expect(PHONE_QUERY).toBe('(max-width: 767px)');
    expect(DESKTOP_QUERY).toBe('(min-width: 768px)');
  });
  it('answers for the current screen', () => {
    expect(isPhone()).toBe(matchMedia(PHONE_QUERY).matches);
  });
});
