// The list built from the plan and the "Check you have these" card (0.6 PR 5; docs/dev/api-0.2.md
// section 6.3b). Online only: the server works the sums out. The list itself, with the lines the
// plan made, comes down the ordinary way (GET /shopping/changes) and works offline as before.

import { api } from '#lib/api.js';

export interface Staple {
  food: { id: number; name: string };
  /** The recipes that use it, A to Z. */
  used_in: string[];
}

export interface PlanCard {
  /** How far ahead the list looks: the household's setting. */
  days: number;
  /** Lines of the main list the plan made. */
  from_plan: number;
  changed: boolean;
  staples: Staple[];
}

/** Bring the main list up to date with the plan and the pantry; give back the card. */
export const fromPlan = () => api<PlanCard>('POST', '/shopping/from-plan');
export const gotIt = (foodId: number) => api<PlanCard>('PUT', `/shopping/staples/${foodId}/got-it`);
export const notGotIt = (foodId: number) =>
  api<PlanCard>('DELETE', `/shopping/staples/${foodId}/got-it`);

/** "Sambar", "Sambar and Dosa", "Sambar, Dosa and Upma", "Sambar, Dosa and 2 more". */
export function usedIn(names: string[]): string {
  if (names.length <= 1) return names[0] ?? '';
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  if (names.length === 3) return `${names[0]}, ${names[1]} and ${names[2]}`;
  return `${names[0]}, ${names[1]} and ${names.length - 2} more`;
}

/** The card's second line (mockups Shop, Desktop-Shop), adjusted to the look-ahead. */
export function staplesLine(days: number | null): string {
  if (days === null) return 'Staples your planned recipes use';
  if (days === 7) return 'Staples this week’s recipes use';
  if (days === 1) return 'Staples today’s recipes use';
  return `Staples the next ${days} days’ recipes use`;
}
