import { afterEach, describe, expect, it } from 'vitest';
import './tokens.css';

// WCAG AA in both themes (UX principle 9): every text colour against every
// background it's used on. 4.5:1 for normal text, 3:1 for large text and focus rings.

type Pair = [text: string, background: string, minimum: number];

const PAIRS: Pair[] = [
  ['--color-text', '--color-ground', 4.5],
  ['--color-text', '--color-surface', 4.5],
  ['--color-text', '--color-chrome', 4.5],
  ['--color-text', '--color-fill', 4.5],
  ['--color-text', '--color-segment-active', 4.5],
  ['--color-text-muted', '--color-ground', 4.5],
  ['--color-text-muted', '--color-surface', 4.5],
  ['--color-text-muted', '--color-chrome', 4.5],
  ['--color-text-muted', '--color-fill', 4.5],
  ['--color-text-muted', '--color-fill-strong', 4.5],
  ['--color-text-soft', '--color-chrome', 4.5],
  ['--color-text-soft', '--color-fill', 4.5],
  ['--color-accent', '--color-ground', 4.5],
  ['--color-accent', '--color-surface', 4.5],
  ['--color-accent', '--color-chrome', 4.5],
  ['--color-accent-hover', '--color-surface', 4.5],
  ['--color-accent-on-soft', '--color-accent-soft', 4.5],
  ['--color-avatar-text', '--color-avatar', 4.5],
  ['--color-inverse-text', '--color-inverse', 4.5],
  ['--color-tubs', '--color-surface', 3], // big numbers (30–36 px, extra bold)
  ['--color-use-soon', '--color-surface', 3], // big numbers
  ['--color-use-soon-text', '--color-chrome', 4.5],
  ['--color-tub-chip-text', '--color-tub-chip', 4.5],
  ['--color-use-soon-text', '--color-use-soon-chip', 4.5],
  ['--color-badge-text', '--color-badge-accent', 4.5],
  ['--color-badge-text', '--color-badge-warn', 4.5],
  ['--color-text', '--color-field', 4.5],
  ['--color-label', '--color-ground', 4.5],
  ['--color-label', '--color-surface', 4.5],
  ['--color-accent', '--color-field', 4.5], // "Show" in the password field
  ['--color-note-text', '--color-note', 4.5],
  ['--color-warning-text', '--color-warning', 4.5],
  ['--color-danger-text', '--color-danger', 4.5], // the red Remove button
  ['--color-swipe-text', '--color-swipe-used', 4.5], // the green Used… button
  ['--color-swipe-text', '--color-swipe-move', 4.5], // the blue Move… button
  ['--color-warning-text', '--color-surface', 4.5], // "Remove from list" in the amount box
  ['--color-field-border', '--color-field', 3], // a text box's edge (WCAG 1.4.11)
  ['--color-field-border', '--color-ground', 3],
  ['--color-field-border', '--color-surface', 3],
  ['--color-focus', '--color-ground', 3],
  ['--color-focus', '--color-chrome', 3],
  ['--color-toast-action', '--color-inverse', 4.5], // "Try again" in the toast
  ['--color-text', '--color-chip', 4.5],
  ['--color-accent', '--color-surface', 4.5], // "+ Add" chips
  ['--color-maybe-chip-text', '--color-maybe-chip', 4.5],
  ['--color-maybe-chip-text', '--color-maybe-button', 4.5],
  ['--color-maybe-text', '--color-maybe-row', 4.5],
  ['--color-text', '--color-maybe-row', 4.5],
  ['--color-text-muted', '--color-maybe-row', 4.5],
  ['--color-accent-on-soft', '--color-accent-soft', 4.5], // the open food's row
  ['--color-text-soft', '--color-accent-soft', 4.5],
  ['--color-use-soon-heading', '--color-use-soon-chip', 4.5],
  ['--color-text', '--color-use-soon-chip', 4.5],
  ['--color-text', '--color-staple-chip', 4.5],
  ['--color-text-muted', '--color-staples-panel', 4.5],
  ['--color-text-muted', '--color-segment-track', 4.5],
  ['--color-text', '--color-segment-active', 4.5],
  ['--color-use-soon-text', '--color-surface', 4.5], // "running low", date chips
  ['--color-accent-on-soft', '--color-accent-soft', 4.5], // the chosen ¼ ½ ¾ Full
  ['--color-on-list', '--color-surface', 4.5], // "On list" on the recipe page
  ['--color-on-list-dot', '--color-surface', 3],
  ['--color-use-soon-text', '--color-fill', 4.5], // "1 missing" on its bar
  // The recipe editor
  ['--color-photo-text', '--color-photo', 4.5], // "Uploading photo…"
  ['--color-text', '--color-changed', 4.5], // Wren's version: what they changed
  ['--color-text-muted', '--color-changed', 4.5],
  ['--color-warning-text', '--color-surface', 4.5], // a box's message
  ['--color-warning-text', '--color-ground', 4.5],
  ['--color-text', '--color-warning', 4.5], // the "Couldn't save" bar's button text
  ['--color-tub-chip-text', '--color-surface', 4.5] // "Not linked"
];

function rgb(value: string): [number, number, number] {
  const probe = document.createElement('div');
  probe.style.color = value;
  document.body.append(probe);
  const match = getComputedStyle(probe).color.match(/\d+(\.\d+)?/g)!;
  probe.remove();
  return [Number(match[0]), Number(match[1]), Number(match[2])];
}

function luminance([r, g, b]: [number, number, number]): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: string, b: string): number {
  const [la, lb] = [luminance(rgb(a)), luminance(rgb(b))].sort((x, y) => y - x) as [number, number];
  return (la + 0.05) / (lb + 0.05);
}

afterEach(() => document.documentElement.removeAttribute('data-theme'));

for (const mode of ['light', 'dark'] as const) {
  describe(`${mode} theme`, () => {
    it.each(PAIRS)('%s on %s is at least %d:1', (text, background, minimum) => {
      document.documentElement.setAttribute('data-theme', mode);
      const styles = getComputedStyle(document.documentElement);
      const fg = styles.getPropertyValue(text).trim();
      const bg = styles.getPropertyValue(background).trim();
      expect(fg, text).not.toBe('');
      expect(bg, background).not.toBe('');
      expect(contrast(fg, bg)).toBeGreaterThanOrEqual(minimum);
    });
  });
}
