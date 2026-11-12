// The words on Settings › Sign-in › API tokens (0.9 O2; proposed, for cabledrawer).
import { describe, expect, it } from 'vitest';
import {
  endsWords,
  lastDay,
  longDate,
  tokenDetail,
  usedWords,
  type ApiToken
} from './apiTokens.js';

const token = (extra: Partial<ApiToken> = {}): ApiToken => ({
  id: 1,
  name: 'Home Assistant',
  scope: 'read',
  created_at: '2026-11-01T09:00:00Z',
  last_used_at: null,
  expires_on: null,
  ...extra
});

describe('API token words', () => {
  const now = new Date(2026, 10, 12, 15, 0); // 12 Nov 2026, 3 pm on this device

  it('says when it was last used', () => {
    expect(usedWords(null, now)).toBe('never used');
    expect(usedWords(new Date(2026, 10, 12, 14, 59).toISOString(), now)).toBe('used just now');
    expect(usedWords(new Date(2026, 10, 12, 14, 55).toISOString(), now)).toBe('used 5 min ago');
    expect(usedWords(new Date(2026, 10, 12, 8, 0).toISOString(), now)).toBe('used today');
    expect(usedWords(new Date(2026, 10, 11, 22, 0).toISOString(), now)).toBe('used yesterday');
    expect(usedWords(new Date(2026, 10, 2, 9, 0).toISOString(), now)).toBe('used 2 Nov');
  });

  it('says when it ends, and when it has ended', () => {
    expect(longDate('2026-12-31')).toBe('31 Dec 2026');
    expect(endsWords(token(), '2026-11-12')).toBe('never expires');
    expect(endsWords(token({ expires_on: '2026-12-31' }), '2026-11-12')).toBe(
      'expires 31 Dec 2026'
    );
    expect(endsWords(token({ expires_on: '2026-11-12' }), '2026-11-12')).toBe(
      'expires 12 Nov 2026'
    );
    expect(endsWords(token({ expires_on: '2026-11-02' }), '2026-11-12')).toBe('ended 2 Nov 2026');
  });

  it('reads like the drawing', () => {
    const used = new Date(2026, 10, 12, 14, 55).toISOString();
    expect(tokenDetail(token({ last_used_at: used }), '2026-11-12', now)).toBe(
      'Read-only · never expires · used 5 min ago'
    );
    const full = token({ scope: 'full', expires_on: '2026-12-31', last_used_at: used });
    expect(tokenDetail(full, '2026-11-12', now)).toBe(
      'Full access · expires 31 Dec 2026 · used 5 min ago'
    );
  });

  it('turns the Expires chip into the last day it works', () => {
    expect(lastDay('never', '2026-11-12', '')).toBeNull();
    expect(lastDay('month', '2026-11-12', '')).toBe('2026-12-12');
    expect(lastDay('year', '2026-11-12', '')).toBe('2027-11-12');
    expect(lastDay('pick', '2026-11-12', '2027-01-31')).toBe('2027-01-31');
  });
});
