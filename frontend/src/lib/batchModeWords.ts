// The words on Batch cook mode (mockup Dark-BatchSession08; spec section 6, "Batch cook
// (Experimental)"). Words the mockup shows are as drawn; the rest are proposed, for cabledrawer.

import type { Schedule, ScheduleRecipe, ScheduleTask } from './client/batchMode';
import { timeWords } from './timeWords';

const KIND_NAME = {
  hob: 'hob',
  pressure: 'pressure cooker',
  oven: 'oven'
} as const;

/** "Task 6 of 19 · about 1 h 20 left" (the time is the hands-on time still to give). */
export function progressWords(done: number, total: number, minutesLeft: number): string {
  const task = `Task ${Math.min(done + 1, total)} of ${total}`;
  if (done >= total) return `All ${total} done`; // proposed
  return minutesLeft > 0
    ? `${task} · about ${timeWords(Math.round(minutesLeft / 5) * 5 || 5)} left`
    : task;
}

/** The tag on a task: "Hands-on · ~8 min", or what it waits in ("Pressure cooker · waiting"). */
export function tagWords(task: ScheduleTask): string {
  if (task.hands === 'hands') return `Hands-on · ~${timeWords(task.minutes)}`;
  const where =
    task.equipment === 'pressure'
      ? 'Pressure cooker'
      : task.equipment === 'oven'
        ? 'Oven'
        : task.equipment === 'hob'
          ? 'On the hob'
          : 'Waiting';
  return task.equipment === 'none' ? 'Waiting' : `${where} · waiting`;
}

/** "Shared prep · both recipes" under a shared task; nothing for a recipe's own step. */
export function sharedWords(task: ScheduleTask, recipes: ScheduleRecipe[]): string | null {
  if (task.kind !== 'prep') return null;
  const names = task.recipe_ids.map(
    (id) => recipes.find((r) => r.recipe_id === id)?.recipe_name ?? 'a recipe'
  );
  return task.recipe_ids.length === recipes.length && recipes.length === 2
    ? 'Shared prep · both recipes'
    : `Shared prep · ${names.join(' and ')}`;
}

/** "In use: hob 1 of 4 · pressure cooker 1 of 1" (what is in use now; nothing: said so). */
export function inUseWords(
  inUse: Record<'hob' | 'pressure' | 'oven', number>,
  kitchen: Schedule['kitchen']
): string {
  const cap = {
    hob: kitchen.hob_rings,
    pressure: kitchen.pressure_cookers,
    oven: kitchen.oven ? 1 : 0
  };
  const parts = (['hob', 'pressure', 'oven'] as const)
    .filter((k) => inUse[k] > 0)
    .map((k) => `${KIND_NAME[k]} ${inUse[k]} of ${cap[k]}`);
  return parts.length ? `In use: ${parts.join(' · ')}` : 'Nothing in use right now'; // proposed
}

const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

/** The quiet NEXT line: "Chicken chettinad: fry the onions with the curry leaves (hob ring 2)." */
export function nextWords(task: ScheduleTask, recipes: ScheduleRecipe[]): string {
  const where =
    task.slot !== null && task.equipment === 'hob'
      ? ` (hob ring ${task.slot})`
      : task.slot !== null && task.equipment === 'pressure'
        ? ` (pressure cooker ${task.slot})`
        : task.slot !== null && task.equipment === 'oven'
          ? ' (oven)'
          : '';
  const body = task.title.replace(/[.!]$/, '');
  if (task.kind === 'prep') return `${body}.`;
  const name = recipes.find((r) => task.recipe_ids.includes(r.recipe_id ?? -1))?.recipe_name;
  return `${name ? `${name}: ${lowerFirst(body)}` : body}${where}.`;
}

/** Said under a task that needs equipment the kitchen has none of (proposed, for cabledrawer). */
export function lacksWords(task: ScheduleTask): string {
  const what =
    task.equipment === 'oven'
      ? 'an oven'
      : task.equipment === 'pressure'
        ? 'a pressure cooker'
        : 'a hob ring';
  return `Your kitchen has no ${what.replace(/^an? /, '')}. Do this on its own, however you manage it.`;
}

/** A recipe's row under Now. */
export function startsWords(inMinutes: number): string {
  return inMinutes <= 0 ? 'Starts next' : `Starts in about ${timeWords(inMinutes)}`;
}
