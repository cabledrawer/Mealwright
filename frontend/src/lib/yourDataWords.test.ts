import { describe, expect, it } from 'vitest';
import type { Backups } from '#lib/client/yourData.js';
import {
  EVERY_WORDS,
  keepWords,
  lastBackupWords,
  problemWords,
  sizeWords,
  whenWords,
  wordsMatch
} from './yourDataWords';

const NOW = new Date(2026, 10, 13, 10, 0); // Fri 13 Nov 2026, 10:00 on this device
const at = (day: number, hour: number) => new Date(2026, 10, day, hour, 0).toISOString();

const backups = (extra: Partial<Backups> = {}): Backups => ({
  every: 'daily',
  keep: 7,
  last: { at: at(13, 3), size: 2_140_000 },
  problem: null,
  problem_at: null,
  count: 3,
  folder: '/data/backups',
  ...extra
});

describe('Your data words', () => {
  it('says how often as the mockup does', () => {
    expect(EVERY_WORDS.daily).toBe('Daily, 03:00');
    expect(keepWords(7)).toBe('Last 7');
  });

  it('says sizes the way people read them, with a no-break space', () => {
    expect(sizeWords(900)).toBe('900 bytes');
    expect(sizeWords(640_400)).toBe('640 KB');
    expect(sizeWords(2_140_000)).toBe('2.1 MB');
    expect(sizeWords(3_200_000_000)).toBe('3.2 GB');
  });

  it('says when as Today, Yesterday, a weekday, then a date', () => {
    expect(whenWords(at(13, 3), NOW)).toBe('Today 03:00');
    expect(whenWords(at(12, 15), NOW)).toBe('Yesterday 15:00');
    expect(whenWords(at(9, 3), NOW)).toBe('Mon 03:00');
    expect(whenWords(at(2, 3), NOW)).toBe('2 Nov 03:00');
  });

  it('the Last backup line: when, how big, and all fine', () => {
    expect(lastBackupWords(backups(), NOW)).toBe('Today 03:00 · 2.1 MB · all fine');
    expect(lastBackupWords(backups({ last: null }), NOW)).toBe('None yet · the first is made soon');
    expect(problemWords(backups(), NOW)).toBeNull();
  });

  it('a failed backup: no "all fine", and the reason', () => {
    const failed = backups({ problem: 'The disk is full.', problem_at: at(13, 9) });
    expect(lastBackupWords(failed, NOW)).toBe('Today 03:00 · 2.1 MB');
    expect(problemWords(failed, NOW)).toBe(
      'The last backup failed (Today 09:00): The disk is full.'
    );
  });

  it('reads the typed words as the server does: capitals and spaces don’t matter', () => {
    expect(wordsMatch('delete everything')).toBe(true);
    expect(wordsMatch('  Delete   Everything ')).toBe(true);
    expect(wordsMatch('delete every')).toBe(false);
    expect(wordsMatch('delete everything!')).toBe(false);
    expect(wordsMatch('')).toBe(false);
  });
});
