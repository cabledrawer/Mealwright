import { afterEach, describe, expect, it, vi } from 'vitest';
import { CopyFeedback, COPIED_FOR_MS } from './copyFeedback.svelte';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('CopyFeedback', () => {
  it('says Copied for two seconds after a copy, then the normal word', async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const feedback = new CopyFeedback();
    expect(feedback.label('Copy')).toBe('Copy');
    expect(await feedback.copy('abc')).toBe(true);
    expect(writeText).toHaveBeenCalledWith('abc');
    expect(feedback.label('Copy')).toBe('Copied');
    vi.advanceTimersByTime(COPIED_FOR_MS - 1);
    expect(feedback.label('Copy')).toBe('Copied');
    vi.advanceTimersByTime(1);
    expect(feedback.label('Copy')).toBe('Copy');
  });

  it('a second copy starts the two seconds again', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    const feedback = new CopyFeedback();
    await feedback.copy('a');
    vi.advanceTimersByTime(1500);
    await feedback.copy('a');
    vi.advanceTimersByTime(1500);
    expect(feedback.copied).toBe(true);
    vi.advanceTimersByTime(500);
    expect(feedback.copied).toBe(false);
  });

  it('a refused copy is not "Copied"', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('no')) }
    });
    const feedback = new CopyFeedback();
    expect(await feedback.copy('abc')).toBe(false);
    expect(feedback.label('Copy')).toBe('Copy');
  });
});
