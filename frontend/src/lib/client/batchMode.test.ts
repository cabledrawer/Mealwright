import { afterEach, describe, expect, it, vi } from 'vitest';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { markTaskDone, startTaskTimer, undoTaskDone } from './batchMode';

afterEach(() => vi.unstubAllGlobals());

const progress = { tasks: [], done_count: 0 };
const task = '/batch-cook/sessions/4/schedule/tasks/t2';

// D3 (BE14): a task is marked done, or not, with a PATCH on it; its timer is started with
// POST .../start-timer. Marks waiting on the phone are sent through these, so they follow.
describe('batch cook mode', () => {
  it('marks a task done, and takes it back, with a PATCH on the task', async () => {
    const requests = fakeApi({ [`PATCH ${task}?brief=true`]: [200, progress] });
    await markTaskDone(4, 't2', '2026-11-20T10:00:00Z', '2026-11-20T09:00:00Z');
    await markTaskDone(4, 't2');
    await undoTaskDone(4, 't2', '2026-11-20T09:00:00Z');
    await undoTaskDone(4, 't2');
    expect(requests.map((r) => [r.method, r.url, r.body])).toEqual([
      [
        'PATCH',
        `${task}?brief=true`,
        { done: true, at: '2026-11-20T10:00:00Z', made_at: '2026-11-20T09:00:00Z' }
      ],
      ['PATCH', `${task}?brief=true`, { done: true }],
      ['PATCH', `${task}?brief=true`, { done: false, made_at: '2026-11-20T09:00:00Z' }],
      ['PATCH', `${task}?brief=true`, { done: false }]
    ]);
  });

  it('starts a timer with POST start-timer', async () => {
    const requests = fakeApi({ [`POST ${task}/start-timer?brief=true`]: [200, progress] });
    await startTaskTimer(4, 't2', '2026-11-20T10:00:00Z');
    expect(requests.map((r) => [r.method, r.url, r.body])).toEqual([
      ['POST', `${task}/start-timer?brief=true`, { at: '2026-11-20T10:00:00Z' }]
    ]);
  });
});
