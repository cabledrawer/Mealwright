import { describe, expect, it } from 'vitest';
import type { DraftBrief } from './client/drafts';
import {
  allChecked,
  daysWords,
  fromWords,
  needYou,
  phoneSource,
  progressShare,
  progressWords,
  shortProgress
} from './draftWords';

const draft = (over: Partial<DraftBrief> = {}): DraftBrief => ({
  id: 1,
  name: 'Chettinad kuzhambu',
  source: { kind: 'link', site: 'bbcgoodfood.com' },
  started_by: 'Tess',
  started_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
  expires_at: '2026-11-06T10:00:00Z',
  days_left: 13,
  lines_total: 9,
  lines_checked: 6,
  ...over
});

describe('the words on the Drafts screen (the mockups’ own)', () => {
  it('says where it came from and who started it', () => {
    expect(phoneSource(draft())).toBe('From bbcgoodfood.com · started by Tess');
    expect(phoneSource(draft({ source: { kind: 'text', site: null }, started_by: 'Wren' }))).toBe(
      'Pasted text · started by Wren'
    );
    expect(fromWords(draft())).toBe('bbcgoodfood.com');
    expect(fromWords(draft({ source: { kind: 'text', site: null } }))).toBe('Pasted text');
  });

  it('counts the days left', () => {
    expect(daysWords(13)).toBe('13 days left');
    expect(daysWords(1)).toBe('1 day left');
    expect(daysWords(13, false)).toBe('13 days');
  });

  it('says how far the checking has got', () => {
    expect(progressWords(draft())).toBe('6 of 9 ingredients checked · 3 need you');
    expect(shortProgress(draft())).toBe('6 of 9 · 3 need you');
    expect(progressWords(draft({ lines_checked: 8 }))).toBe(
      '8 of 9 ingredients checked · 1 needs you'
    );
    expect(progressWords(draft({ lines_checked: 9 }))).toBe('All checked · ready to save');
    expect(shortProgress(draft({ lines_checked: 9 }))).toBe('All checked · ready to save');
    expect(progressWords(draft({ lines_total: 0, lines_checked: 0 }))).toBe('No ingredients found');
    expect(progressShare(draft())).toBe(67);
    expect(progressShare(draft({ lines_total: 0, lines_checked: 0 }))).toBe(0);
  });

  it('is ready to save only when every ingredient is checked, and there are some', () => {
    expect(allChecked(draft())).toBe(false);
    expect(allChecked(draft({ lines_checked: 9 }))).toBe(true);
    expect(allChecked(draft({ lines_total: 0, lines_checked: 0 }))).toBe(false);
    expect(needYou(draft())).toBe(3);
  });
});
