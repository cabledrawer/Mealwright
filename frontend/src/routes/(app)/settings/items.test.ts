// The Settings items: four groups, each item once, the Household group for admins only (F252).

import { describe, expect, it } from 'vitest';
import { GROUPS, ITEMS, itemAt, itemForOldSection, itemsFor } from './items.js';

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
    expect(itemAt('/settings/household/7')?.id).toBe('people');
    expect(itemAt('/settings/sso')?.id).toBe('sign-in-everyone');
    expect(itemAt('/settings/password')?.id).toBe('sign-in');
    expect(itemAt('/settings/your-data/restore')?.id).toBe('your-data');
    expect(itemAt('/settings')).toBeUndefined();
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
    expect(itemForOldSection('nonsense')).toBeUndefined();
  });
});
