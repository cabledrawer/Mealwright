import { describe, expect, it } from 'vitest';
import { sumWaits, timePlusWait, timeWithWait, timeWords, waitLength } from './timeWords';

describe('timeWords', () => {
  it('keeps minutes up to the hour', () => {
    expect(timeWords(1)).toBe('1 min');
    expect(timeWords(50)).toBe('50 min');
    expect(timeWords(59)).toBe('59 min');
  });
  it('says 60 as one hour', () => {
    expect(timeWords(60)).toBe('1 h');
  });
  it('shows hours and minutes over the hour', () => {
    expect(timeWords(125)).toBe('2 h 5 min');
    expect(timeWords(745)).toBe('12 h 25 min');
    expect(timeWords(1440)).toBe('24 h');
  });
});

const N = '\u00a0';
const marinate = { kind: 'marinate', min_minutes: 240, max_minutes: 720, overnight: true };

describe('steps that wait', () => {
  it('says the length of a wait', () => {
    expect(waitLength(marinate)).toBe(`4${N}h – overnight`);
    expect(waitLength({ ...marinate, min_minutes: 720 })).toBe('overnight');
    expect(
      waitLength({ kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false })
    ).toBe(`8${N}h – 12${N}h`);
    expect(waitLength({ kind: 'soak', min_minutes: 90, max_minutes: 90, overnight: false })).toBe(
      `1${N}h${N}30${N}min`
    );
  });
  it('splits a time into active time and the wait', () => {
    expect(timeWithWait(45, marinate)).toBe(
      `45${N}min active · plus 4${N}h – overnight marinating`
    );
    expect(timeWithWait(null, marinate)).toBe(`4${N}h – overnight marinating`);
    expect(timeWithWait(45, null)).toBe(`45${N}min`);
    expect(timeWithWait(null, undefined)).toBe('');
    expect(timeWithWait(45, { ...marinate, kind: 'wait' })).toContain('waiting');
  });
  it('has a short form for cards', () => {
    expect(timePlusWait(45, marinate)).toBe(`45${N}min + 4${N}h – overnight`);
    expect(timePlusWait(45, null)).toBe(`45${N}min`);
  });
  it('adds the steps waits up, as the server does', () => {
    expect(sumWaits([{ kind: 'step' }, { kind: 'heading' }])).toBeNull();
    const sum = sumWaits([
      { kind: 'step', wait: { kind: 'soak', min_minutes: 30, max_minutes: 30, overnight: false } },
      {
        kind: 'step',
        wait: { kind: 'marinate', min_minutes: 60, max_minutes: 120, overnight: false }
      }
    ]);
    expect(sum).toEqual({ kind: 'wait', min_minutes: 90, max_minutes: 150, overnight: false });
  });
});

describe('waitLength past the overnight mark (M1 fix 7)', () => {
  const wait = (min: number, max: number, overnight: boolean) => ({
    kind: 'marinate',
    min_minutes: min,
    max_minutes: max,
    overnight
  });
  const said = (w: ReturnType<typeof wait>) => waitLength(w).replace(/ /g, ' ');
  it('says what is stored when the range goes past 12 h', () => {
    expect(said(wait(720, 1440, true))).toBe('12 h – 24 h');
    expect(said(wait(900, 900, true))).toBe('15 h');
  });
  it('still says overnight at exactly 12 h', () => {
    expect(said(wait(720, 720, true))).toBe('overnight');
    expect(said(wait(240, 720, true))).toBe('4 h – overnight');
  });
  it('adds two overnight waits up as 24 h, not "overnight"', () => {
    const steps = [wait(720, 720, true), wait(720, 720, true)].map((w) => ({
      kind: 'step',
      wait: w
    }));
    expect(said(sumWaits(steps)!)).toBe('24 h');
  });
});
