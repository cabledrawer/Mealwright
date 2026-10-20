import { describe, expect, it } from 'vitest';
import { PANES_MIN_AREA, SIDEBAR, SIDEBAR_COLLAPSED, panesFit } from './recipePanes.svelte';
import tokens from './styles/tokens.css?raw';

// Where the desktop's three panes fit (nav · list · reading pane): the sidebar is 248 px open
// and 72 px collapsed, and the list and the reading pane need 776 px beside it.
describe('where the three panes fit', () => {
  it('needs 776 px beside the sidebar', () => {
    expect(PANES_MIN_AREA).toBe(776);
  });

  it('fits from 1024 px with the sidebar open, not below', () => {
    expect(panesFit(1024, false)).toBe(true);
    expect(panesFit(1023, false)).toBe(false);
    expect(panesFit(1440, false)).toBe(true);
    expect(panesFit(2560, false)).toBe(true);
  });

  it('fits from 848 px with the sidebar collapsed, not below', () => {
    expect(panesFit(848, true)).toBe(true);
    expect(panesFit(847, true)).toBe(false);
  });

  it('never fits on a phone, which has no sidebar', () => {
    for (const width of [320, 390, 767]) {
      expect(panesFit(width, true)).toBe(false);
      expect(panesFit(width, false)).toBe(false);
    }
  });

  it('leaves a tablet held upright (768 to 834 px) with one page at a time', () => {
    for (const width of [768, 810, 820, 834]) expect(panesFit(width, false)).toBe(false);
  });
});

// The sidebar's widths are written twice: in the stylesheet (what is drawn) and in recipePanes.svelte.ts
// (what decides whether the panes fit). They must not drift apart.
describe('the sidebar widths used for the panes', () => {
  const token = (name: string) => {
    const found = new RegExp(`${name}:\\s*(\\d+)px`).exec(tokens);
    expect(found, `${name} in tokens.css`).not.toBeNull();
    return Number(found![1]);
  };

  it('are the stylesheet’s own', () => {
    expect(SIDEBAR).toBe(token('--sidebar-width'));
    expect(SIDEBAR_COLLAPSED).toBe(token('--sidebar-collapsed-width'));
  });
});
