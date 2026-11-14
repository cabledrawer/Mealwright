import { describe, expect, it, vi } from 'vitest';
import { printedOn, printing, watchPrinting } from './printing.svelte';

describe('printing', () => {
  it('says the day as "13 Nov"', () => {
    expect(printedOn(new Date(2026, 10, 13).getTime())).toBe('13 Nov');
    expect(printedOn(new Date(2026, 0, 5).getTime())).toBe('5 Jan');
  });

  it('follows beforeprint and afterprint, and stops when asked', () => {
    const media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal('matchMedia', () => media);
    const stop = watchPrinting();
    expect(printing.on).toBe(false);
    window.dispatchEvent(new Event('beforeprint'));
    expect(printing.on).toBe(true);
    window.dispatchEvent(new Event('afterprint'));
    expect(printing.on).toBe(false);
    window.dispatchEvent(new Event('beforeprint'));
    stop();
    expect(printing.on).toBe(false);
    window.dispatchEvent(new Event('beforeprint'));
    expect(printing.on).toBe(false);
    expect(media.removeEventListener).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('starts on when the media is already print', () => {
    const media = { matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal('matchMedia', () => media);
    const stop = watchPrinting();
    expect(printing.on).toBe(true);
    stop();
    vi.unstubAllGlobals();
  });
});
