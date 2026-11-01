import { describe, expect, it, vi } from 'vitest';
import { CHIME_GAP, CHIME_PLAYS, CHIME_RING, playChime } from './chime';

function fakeAudio(state = 'running') {
  const tones: { hertz: number; start: number; stop: number }[] = [];
  const peaks: number[] = [];
  const resume = vi.fn(async () => {});
  const destination = {};
  const context = {
    currentTime: 10,
    state,
    destination,
    resume,
    createOscillator() {
      const tone = { hertz: 0, start: 0, stop: 0 };
      tones.push(tone);
      return {
        type: '',
        frequency: {
          set value(v: number) {
            tone.hertz = v;
          }
        },
        connect: () => undefined,
        start: (at: number) => void (tone.start = at),
        stop: (at: number) => void (tone.stop = at)
      };
    },
    createGain() {
      return {
        gain: {
          value: 1,
          setValueAtTime: () => undefined,
          linearRampToValueAtTime: (level: number) => void peaks.push(level),
          exponentialRampToValueAtTime: () => undefined
        },
        connect: () => undefined
      };
    }
  };
  return { context, tones, peaks, resume };
}

describe('the timer chime', () => {
  it('plays one short chime three times, made from sine waves in code', () => {
    const { context, tones } = fakeAudio();
    const starts = playChime(context);
    expect(CHIME_PLAYS).toBe(3);
    expect(starts).toHaveLength(3);
    // A fixed gap between the three, starting just after now.
    expect(starts[0]).toBeGreaterThan(10);
    expect(starts[1]! - starts[0]!).toBeCloseTo(CHIME_GAP);
    expect(starts[2]! - starts[1]!).toBeCloseTo(CHIME_GAP);
    // Two notes in each chime, every one ringing for under a second, and a chime ends before the next.
    expect(tones).toHaveLength(6);
    for (const tone of tones) expect(tone.stop - tone.start).toBeLessThan(1);
    expect(CHIME_RING).toBeLessThan(CHIME_GAP);
    expect(tones.slice(0, 2).map((t) => t.start)).toEqual([starts[0], starts[0]]);
  });

  it('is gentle: no note louder than a quarter of full volume', () => {
    const { context, peaks } = fakeAudio();
    playChime(context);
    expect(Math.max(...peaks)).toBeLessThanOrEqual(0.25);
  });

  it('wakes a sleeping audio context, and makes no sound where there is none', () => {
    const { context, resume } = fakeAudio('suspended');
    playChime(context);
    expect(resume).toHaveBeenCalled();
    expect(playChime(null)).toEqual([]);
  });
});
