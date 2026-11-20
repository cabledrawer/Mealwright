// The Settings items: four groups, each item once, the Household group for admins only (F252).

import { describe, expect, it } from 'vitest';
import {
  GROUPS,
  ITEMS,
  itemAt,
  itemAtRoute,
  itemForOldSection,
  itemsFor,
  labelOf
} from './items.js';

describe('Settings items', () => {
  it('has the four groups, and each one holds the items the decision names', () => {
    expect(GROUPS.map((g) => g.name)).toEqual(['You', 'Kitchen', 'Household', 'Mealwright']);
    const names = (group: string) => ITEMS.filter((i) => i.group === group).map((i) => i.label);
    expect(names('You')).toEqual(['Appearance', 'Amounts', 'Your sign-in']);
    expect(names('Kitchen')).toEqual(['Meal slots', 'Shops & places', 'Your kitchen']);
    expect(names('Household')).toEqual([
      'People',
      'Sign-in for everyone',
      'API tokens',
      'Outside connections',
      'Backups & your data'
    ]);
    expect(names('Mealwright')).toEqual(['Recent changes', 'About']);
  });

  it('has each item once, on its own address', () => {
    expect(new Set(ITEMS.map((i) => i.id)).size).toBe(ITEMS.length);
    expect(new Set(ITEMS.map((i) => i.path)).size).toBe(ITEMS.length);
  });

  it('FE25: each page lives at its id, its route folder is its id, and the id is a slug of its label', () => {
    // Three labels say more than their address, which stays short and as it was (proposed,
    // for cabledrawer).
    const shortened: Record<string, string> = {
      'sign-in': 'Your sign-in',
      'sign-in-everyone': 'Sign-in for everyone',
      'your-data': 'Backups & your data'
    };
    const slug = (label: string) =>
      label
        .toLowerCase()
        .replace(/&/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '');
    for (const item of ITEMS) {
      expect(item.path, item.id).toBe(`/settings/${item.id}`);
      expect(item.route, item.id).toBe(`/(app)/settings/${item.id}`);
      if (shortened[item.id]) expect(item.label).toBe(shortened[item.id]);
      else expect(slug(item.label), item.label).toBe(item.id);
    }
  });

  it('FE1: gives each item’s one name on screen', () => {
    expect(labelOf('outside-connections')).toBe('Outside connections');
    expect(labelOf('people')).toBe('People');
    expect(() => labelOf('privacy')).toThrow();
  });

  it('hides the whole Household group, and Meal slots, from a member, and nothing else', () => {
    const member = itemsFor(false);
    expect(member.map((i) => i.group)).not.toContain('Household');
    expect(member.map((i) => i.label)).not.toContain('Meal slots');
    expect(itemsFor(true)).toHaveLength(ITEMS.length);
    expect(member.map((i) => i.label)).toEqual([
      'Appearance',
      'Amounts',
      'Your sign-in',
      'Shops & places',
      'Your kitchen',
      'Recent changes',
      'About'
    ]);
  });

  it('finds the item a page belongs to, including pages under an item', () => {
    expect(itemAt('/settings/about')?.id).toBe('about');
    expect(itemAt('/settings/about/report')?.id).toBe('about');
    expect(itemAt('/settings/people/7')?.id).toBe('people');
    expect(itemAt('/settings/household/7')?.id).toBe('people'); // the old address (FE25)
    expect(itemAt('/settings/privacy')?.id).toBe('outside-connections');
    expect(itemAt('/settings/kitchen')?.id).toBe('your-kitchen');
    expect(itemAt('/settings/sso')?.id).toBe('sign-in-everyone');
    expect(itemAt('/settings/password')?.id).toBe('sign-in');
    expect(itemAt('/settings/your-data/restore')?.id).toBe('your-data');
    expect(itemAt('/settings')).toBeUndefined();
  });

  it('finds the item by the route of the page, whatever the address was spelt like', () => {
    expect(itemAtRoute('/(app)/settings/people')?.id).toBe('people');
    expect(itemAtRoute('/(app)/settings/people/[id]')?.id).toBe('people');
    expect(itemAtRoute('/(app)/settings/household/[id]')?.id).toBe('people');
    expect(itemAtRoute('/(app)/settings/your-data/restore')?.id).toBe('your-data');
    expect(itemAtRoute('/(app)/settings')).toBeUndefined();
    expect(itemAtRoute(null)).toBeUndefined();
  });

  it('maps every old section name to an item', () => {
    for (const old of [
      'appearance',
      'amounts',
      'household',
      'meal-slots',
      'shops-places',
      'your-kitchen',
      'recent-changes',
      'privacy',
      'sign-in',
      'your-data',
      'about'
    ])
      expect(itemForOldSection(old), old).toBeDefined();
    expect(itemForOldSection('household')?.label).toBe('People');
    expect(itemForOldSection('privacy')?.id).toBe('outside-connections');
    expect(itemForOldSection('kitchen')?.id).toBe('your-kitchen');
    // Only the item's own names: nothing inherited from an object counts.
    expect(itemForOldSection('constructor')).toBeUndefined();
    expect(itemForOldSection('__proto__')).toBeUndefined();
    expect(itemForOldSection('nonsense')).toBeUndefined();
  });
});
