import { describe, expect, it } from 'vitest';
import type { ScheduleRecipe, ScheduleTask } from './client/batchMode';
import { timeWords } from './timeWords';
import { inUseWords, nextWords, progressWords, sharedWords, tagWords } from './batchModeWords';

const recipes: ScheduleRecipe[] = [
  { batch_id: 1, recipe_id: 1, recipe_name: 'Sambar', tub_count: 3, pattern: 'pick', colour: null },
  {
    batch_id: 2,
    recipe_id: 2,
    recipe_name: 'Chicken chettinad',
    tub_count: 4,
    pattern: 'pick',
    colour: null
  }
];
const task = (over: Partial<ScheduleTask>): ScheduleTask => ({
  id: 't1',
  kind: 'step',
  title: 'Fry the onions with the curry leaves.',
  recipe_ids: [2],
  step_ids: [],
  start: 0,
  end: 8,
  minutes: 8,
  hands: 'hands',
  equipment: 'hob',
  slot: 2,
  lacks: false,
  state: 'ready',
  started_at: null,
  done_at: null,
  ends_at: null,
  ...over
});

describe('the words of Batch cook mode', () => {
  it('says the mockup’s lines', () => {
    expect(progressWords(5, 19, 80)).toBe(`Task 6 of 19 · about ${timeWords(80)} left`);
    expect(tagWords(task({}))).toBe(`Hands-on · ~${timeWords(8)}`);
    expect(tagWords(task({ hands: 'waiting', equipment: 'pressure' }))).toBe(
      'Pressure cooker · waiting'
    );
    expect(sharedWords(task({ kind: 'prep', recipe_ids: [1, 2] }), recipes)).toBe(
      'Shared prep · both recipes'
    );
    expect(
      inUseWords(
        { hob: 1, pressure: 1, oven: 0 },
        { hob_rings: 4, pressure_cookers: 1, oven: true }
      )
    ).toBe('In use: hob 1 of 4 · pressure cooker 1 of 1');
    expect(nextWords(task({}), recipes)).toBe(
      'Chicken chettinad: fry the onions with the curry leaves (hob ring 2).'
    );
  });

  it('says so when nothing is in use or everything is done', () => {
    expect(
      inUseWords(
        { hob: 0, pressure: 0, oven: 0 },
        { hob_rings: 2, pressure_cookers: 0, oven: false }
      )
    ).toBe('Nothing in use right now');
    expect(progressWords(19, 19, 0)).toBe('All 19 done');
  });
});
