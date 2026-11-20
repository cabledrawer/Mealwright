import { mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { SECTION_ICONS } from '../../routes/(app)/settings/sectionIcons.js';
import Icon, { ICON_SIZES, ICON_STROKES, type Name } from './Icon.svelte';

// The beta.3 icon pack (agreed 20 Nov): the drawings below are the agreed path data.
const mounted: ReturnType<typeof mount>[] = [];
afterEach(() => {
  for (const c of mounted.splice(0)) void unmount(c);
  document.body.innerHTML = '';
});

function inner(name: Name): string {
  const c = mount(Icon, { target: document.body, props: { name } });
  mounted.push(c);
  const svg = document.body.querySelector('svg')!;
  const html = svg.innerHTML.replace(/<!---->/g, '').replace(/\s+/g, ' ').trim();
  svg.remove();
  return html;
}

const CALENDAR =
  '<rect x="3" y="4.5" width="18" height="16.5" rx="2"></rect><path d="M3 9.5h18M8 2.5v4M16 2.5v4"></path><path d="M7.5 13.5h.01M12 13.5h.01M16.5 13.5h.01M7.5 17h.01M12 17h.01"></path>';

describe('the icon pack', () => {
  it('draws the agreed carrot for ingredients', () => {
    const html = inner('ingredients');
    expect(html).toContain('M4 20c1-4 4.5-9.5 7-12a2.5 2.5 0 0 1 3.5 3.5C12 14 7 18 4 20z');
    expect(html).toContain('M15 9l4.5-4.5M13.5 7.5l.8-4.3M16.5 10.5l4.3-.8');
    expect(html).toContain('M8 15.5l1.5 1M10.5 12.5l1.5 1');
  });
  it('draws stacked tubs for batch, and keeps the pan for cook', () => {
    expect(inner('batch')).toContain('<rect x="6" y="5" width="12" height="7" rx="2">');
    expect(inner('pan')).toContain('M4 11h13v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z');
  });
  it('draws plan and calendar as one calendar', () => {
    expect(inner('plan')).toBe(CALENDAR);
    expect(inner('calendar')).toBe(CALENDAR);
  });
  it('draws an open book for recipes', () => {
    const html = inner('recipes');
    expect(html).toContain('M3 5.5c3-1 6-1 9 1 3-2 6-2 9-1V19c-3-1-6-1-9 1-3-2-6-2-9-1z');
    expect(html).toContain('M12 6.5V20');
  });
  it('draws shopping full size and the pantry lid with 1 px corners', () => {
    expect(inner('shopping')).toContain('M4 8h16l-1.2 12.1a1 1 0 0 1-.9.9H6.2a1 1 0 0 1-.9-.9z');
    expect(inner('pantry')).toContain('<rect x="3" y="4" width="18" height="4" rx="1">');
  });
  it('leaves the old cog alone', () => {
    expect(inner('cog')).toContain('M9.9 5.1 L10.3 2.5 L13.7 2.5');
  });
});

describe('the Settings list pictures', () => {
  it('draws appearance as auto and privacy as the shield', () => {
    const auto = inner('auto');
    for (const d of SECTION_ICONS.appearance.filled ?? []) {
      expect(auto).toContain(d);
    }
    expect(SECTION_ICONS.appearance.filled).toEqual(['M12 4a8 8 0 0 1 0 16z']);
    expect(SECTION_ICONS.appearance.paths).toEqual(['M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0z']);
    expect(SECTION_ICONS.privacy.paths).toEqual([
      'M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z'
    ]);
    expect(inner('shield')).toContain(SECTION_ICONS.privacy.paths[0]);
  });
  it('draws your-kitchen as a hob', () => {
    expect(SECTION_ICONS['your-kitchen'].paths).toHaveLength(4);
  });
});

describe('the fixed sizes and strokes', () => {
  it('keeps short lists', () => {
    expect([...ICON_SIZES]).toEqual([14, 16, 18, 20, 24, 32]);
    expect([...ICON_STROKES]).toEqual([2, 2.4, 3]);
  });
});
