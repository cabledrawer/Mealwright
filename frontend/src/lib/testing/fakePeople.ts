// For tests only: a household's people, as GET /people answers (0.9 A1).

import type { People, Person } from '#lib/client/people.js';

export function person(id: number, name: string, extra: Partial<Person> = {}): Person {
  return {
    id,
    name,
    colour: null,
    portion_quarters: 4,
    login: null,
    is_me: false,
    created_at: '2026-11-03T10:00:00Z',
    created_by_name: 'Tess',
    ...extra
  };
}

export const TESS = person(1, 'Tess', {
  colour: 'green',
  is_me: true,
  login: {
    username: 'tess',
    role: 'admin',
    shared: false,
    has_password: true,
    signs_in: true,
    link_pending: false,
    link_used_at: null,
    reset_pending: false
  }
});

export const JOSS = person(3, 'Joss', { colour: 'amber', portion_quarters: 2 });

export function people(list: Person[] = [TESS, JOSS], extra: Partial<People> = {}): People {
  return { people: list, can_change: true, ask_whos_this: false, change: null, ...extra };
}

export const HOUSEHOLD = {
  name: 'Our kitchen',
  time_zone: 'Europe/London',
  cup_ml: 250,
  cup_ml_used: 250,
  pints: 'uk',
  cook_per_step: false,
  batch_cook: true,
  undo_days: 7,
  history_months: 12,
  use_soon_days: 3
};
