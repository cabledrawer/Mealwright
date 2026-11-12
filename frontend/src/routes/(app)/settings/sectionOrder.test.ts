// The Settings sections follow the spec's order, from one array (U1).

import { describe, expect, it } from 'vitest';
import { GROUPS, SECTION_ORDER } from './sectionOrder.js';

// Spec section 6 and BUILD-PLAN 0.9.0: the nine named sections in this order. Your kitchen and
// Recent changes (0.8) are extra and sit among the kitchen sections.
const SPEC = [
  'Appearance',
  'Amounts',
  'Household',
  'Meal slots',
  'Shops & places',
  'Privacy',
  'Sign-in',
  'Your data',
  'About'
];

describe('Settings section order', () => {
  it('has the spec sections in the spec order', () => {
    const named = SECTION_ORDER.map((s) => s.label).filter((label) => SPEC.includes(label));
    expect(named).toEqual(SPEC);
  });

  it('has each section once, and every group is one the phone draws', () => {
    const ids = SECTION_ORDER.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    const groups = GROUPS.map((g) => g.name);
    for (const s of SECTION_ORDER) expect(groups).toContain(s.group);
  });
});
