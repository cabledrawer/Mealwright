// The one list of Settings' sections, in the spec's order (spec section 6, "Settings (drawn 17
// Oct)"; cabledrawer, BUILD-PLAN 0.9.0: Appearance, Amounts, Household, Meal slots, Shops & places,
// Privacy, Sign-in, Your data, About). The computer's list of sections and the order the
// sections are drawn in follow this array; the phone's list follows it within each group. Your
// kitchen and Recent changes (0.8) sit with the kitchen sections. A section a later PR adds
// (none planned) slots in with one line here.

/** The phone's groups (mockup Dark-Settings09-Phone: You, Kitchen, Household, Mealwright). */
export type GroupName = 'You' | 'Kitchen' | 'Household' | 'Mealwright';

export const SECTION_ORDER = [
  { id: 'appearance', label: 'Appearance', group: 'You' },
  { id: 'amounts', label: 'Amounts', group: 'You' },
  { id: 'household', label: 'Household', group: 'Household' },
  { id: 'meal-slots', label: 'Meal slots', group: 'Kitchen' },
  { id: 'shops-places', label: 'Shops & places', group: 'Kitchen' },
  { id: 'your-kitchen', label: 'Your kitchen', group: 'Kitchen' },
  { id: 'recent-changes', label: 'Recent changes', group: 'Kitchen' },
  { id: 'privacy', label: 'Privacy', group: 'Household' },
  { id: 'sign-in', label: 'Sign-in', group: 'You' },
  { id: 'your-data', label: 'Your data', group: 'Household' },
  { id: 'about', label: 'About', group: 'Mealwright' }
] as const satisfies readonly { id: string; label: string; group: GroupName }[];

export type SectionId = (typeof SECTION_ORDER)[number]['id'];

/** The phone's groups in the order they are drawn, with each one's accessible name. */
export const GROUPS: { name: GroupName; label: string }[] = [
  { name: 'You', label: 'Your settings' },
  { name: 'Kitchen', label: 'Kitchen settings' },
  { name: 'Household', label: 'Household settings' },
  { name: 'Mealwright', label: 'Mealwright' }
];
