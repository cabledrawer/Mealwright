// Batch cook mode (Experimental; 0.8 wave 6, B3; docs/dev/api-0.2.md 6.3f): the session's
// schedule and where it is up to, and one "Cooked it" for the whole session.

import { api } from '#lib/api.js';
import type { Answer, Change } from './types';
import type { CookChoice, CookedMealWrite, Proposal } from './cook';

export type Hands = 'hands' | 'waiting';
export type Equipment = 'hob' | 'pressure' | 'oven' | 'none';
export type TaskState = 'done' | 'running' | 'ready' | 'later';

export interface ScheduleTask {
  id: string;
  kind: 'step' | 'prep';
  title: string;
  recipe_ids: number[];
  step_ids: number[];
  /** Minutes from the start of the session. */
  start: number;
  end: number;
  minutes: number;
  hands: Hands;
  equipment: Equipment;
  slot: number | null;
  lacks: boolean;
  state: TaskState;
  started_at: string | null;
  done_at: string | null;
  ends_at: string | null;
}

export interface ScheduleRecipe {
  batch_id: number;
  recipe_id: number | null;
  recipe_name: string;
  tub_count: number;
  pattern: string;
  colour: string | null;
}

export interface Schedule {
  session_id: number;
  cook_day: string;
  made_at: string;
  stale: boolean;
  total_minutes: number;
  minutes_left: number;
  kitchen: { hob_rings: number; pressure_cookers: number; oven: boolean };
  recipes: ScheduleRecipe[];
  tasks: ScheduleTask[];
  before: { recipe_id: number; step_id: number; text: string; minutes: number }[];
  now_id: string | null;
  next_id: string | null;
  in_use: Record<'hob' | 'pressure' | 'oven', number>;
  done_count: number;
  server_time: string;
}

const base = (id: number) => `/batch-cook/sessions/${id}/schedule`;

/** Start batch cook mode (an existing schedule comes back as it is). */
export const startSchedule = (id: number, planAgain = false) =>
  api<Schedule>('POST', base(id), planAgain ? { plan_again: true } : {});

export const getSchedule = (id: number) => api<Schedule>('GET', base(id));

export const markTaskDone = (id: number, task: string) =>
  api<Schedule>('PUT', `${base(id)}/tasks/${task}/done`);

export const undoTaskDone = (id: number, task: string) =>
  api<Schedule>('DELETE', `${base(id)}/tasks/${task}/done`);

export const startTaskTimer = (id: number, task: string) =>
  api<Schedule>('PUT', `${base(id)}/tasks/${task}/timer`);

export interface SessionProposal {
  session_id: number;
  cook_day: string;
  items: {
    batch_id: number;
    recipe_name: string;
    tub_count: number;
    tubs: { place: string | null; count: number }[];
    proposal: Proposal;
  }[];
}

export interface SessionItemBody {
  batch_id: number;
  portions?: number;
  choices?: CookChoice[];
}

export const previewSessionCook = (
  id: number,
  body: { items: SessionItemBody[]; answers: Answer[] }
) => api<SessionProposal>('POST', `/batch-cook/sessions/${id}/cook/preview`, body);

export const cookSession = (
  id: number,
  body: { items: SessionItemBody[]; answers: Answer[] },
  key: string
) => api<CookedMealWrite>('POST', `/batch-cook/sessions/${id}/cook`, body, { idempotencyKey: key });

export type { Change };
