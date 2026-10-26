import { describe, expect, it } from 'vitest';
import {
  dayFull,
  monthGrid,
  monthWords,
  nextMonth,
  prevMonth,
  weekDays,
  weekStart,
  weekWords,
  weekdayOf
} from './planDates';

describe('weeks', () => {
  it('knows the weekday, 1 Monday … 7 Sunday', () => {
    expect(weekdayOf('2026-10-26')).toBe(1);
    expect(weekdayOf('2026-11-01')).toBe(7);
  });

  it('starts the week on the household’s day', () => {
    expect(weekStart('2026-10-29', 1)).toBe('2026-10-26');
    expect(weekStart('2026-10-26', 1)).toBe('2026-10-26');
    expect(weekStart('2026-11-01', 1)).toBe('2026-10-26');
    expect(weekStart('2026-10-29', 7)).toBe('2026-10-25');
    expect(weekStart('2026-10-25', 7)).toBe('2026-10-25');
    expect(weekStart('2026-10-29', 4)).toBe('2026-10-29');
  });

  it('lists seven days across a month and a year end', () => {
    expect(weekDays('2026-12-28')).toEqual([
      '2026-12-28',
      '2026-12-29',
      '2026-12-30',
      '2026-12-31',
      '2027-01-01',
      '2027-01-02',
      '2027-01-03'
    ]);
  });

  it('words the week', () => {
    expect(weekWords('2026-10-12', '2026')).toBe('12 – 18 October');
    expect(weekWords('2026-10-26', '2026')).toBe('26 October – 1 November');
    expect(weekWords('2026-12-28', '2026')).toBe('28 December – 3 January 2027');
    expect(weekWords('2025-10-13', '2026')).toBe('13 – 19 October 2025');
  });
});

describe('months', () => {
  it('moves between months across a year', () => {
    expect(nextMonth('2026-12-15')).toBe('2027-01-01');
    expect(prevMonth('2027-01-15')).toBe('2026-12-01');
    expect(nextMonth('2026-02-28')).toBe('2026-03-01');
    expect(prevMonth('2026-03-31')).toBe('2026-02-01');
  });

  it('draws whole weeks, from the week start before the 1st', () => {
    const grid = monthGrid('2026-10-17', 1);
    expect(grid[0]).toBe('2026-09-28');
    expect(grid.at(-1)).toBe('2026-11-01');
    expect(grid.length % 7).toBe(0);
    expect(monthGrid('2026-02-10', 1)).toHaveLength(35); // 1 Feb 2026 is a Sunday: from Mon 26 Jan to Sun 1 Mar
  });

  it('starts on Sunday when the household says so', () => {
    expect(monthGrid('2026-10-17', 7)[0]).toBe('2026-09-27');
  });

  it('words a month and a day', () => {
    expect(monthWords('2026-10-17')).toBe('October 2026');
    expect(dayFull('2026-10-19')).toBe('Monday 19 October');
  });
});
