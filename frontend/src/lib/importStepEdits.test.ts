import { describe, expect, it } from 'vitest';
import { ImportFlow } from './import.svelte';
import type { ReviewStep } from './client/imports';
import { activeTime, confirmWait, removeStep, reworkMinutes, takeOffWait } from './importStepEdits';
import { undoHistory } from './undo.svelte';

const MARINATE = { kind: 'marinate', min_minutes: 240, max_minutes: 720, overnight: true };

function flowWith(minutes: string, total: number | null, typed = false) {
  const steps: ReviewStep[] = [
    { kind: 'step', text: 'Marinate overnight.', wait: { ...MARINATE }, wait_confirmed: false },
    { kind: 'step', text: 'Fry.', wait: null }
  ];
  const flow = {
    review: { steps, page_time_minutes: total },
    minutes,
    minutesTyped: typed,
    previewStep: null,
    setMinutesWorkedOut(text: string) {
      this.minutes = text;
    },
    reworkMinutes() {
      ImportFlow.prototype.reworkMinutes.call(this as never);
    },
    keepStepUndo() {}
  };
  return { flow: flow as unknown as ImportFlow & typeof flow, steps };
}

describe('the time and the waits on Check (M1 fix 1)', () => {
  it('works the active time out from the page total and the waits', () => {
    expect(activeTime(745, [MARINATE])).toBe(25);
    expect(activeTime(745, [])).toBe(745);
    expect(activeTime(300, [MARINATE])).toBe(60); // held only the shortest
    expect(activeTime(100, [MARINATE])).toBe(100); // held neither: left alone
    expect(activeTime(null, [MARINATE])).toBeNull();
  });

  it('gives the minutes back on No wait, and takes them again on Undo', async () => {
    const { flow, steps } = flowWith('25', 745);
    takeOffWait(flow, steps[0]!);
    expect(flow.minutes).toBe('745');
    await undoHistory.undoLast();
    expect(steps[0]!.wait).toEqual(MARINATE);
    expect(flow.minutes).toBe('25');
  });

  it('follows a changed wait and a confirmed one', () => {
    const { flow, steps } = flowWith('25', 745);
    steps[0]!.wait = { kind: 'marinate', min_minutes: 120, max_minutes: 120, overnight: false };
    reworkMinutes(flow);
    expect(flow.minutes).toBe('625');
    confirmWait(flow, steps[0]!);
    expect(flow.minutes).toBe('625');
    expect(steps[0]!.wait_confirmed).toBe(true);
  });

  it('leaves Minutes alone once it was typed in, or when the page gave no total', () => {
    const typed = flowWith('40', 745, true);
    takeOffWait(typed.flow, typed.steps[0]!);
    expect(typed.flow.minutes).toBe('40');
    const none = flowWith('25', null);
    takeOffWait(none.flow, none.steps[0]!);
    expect(none.flow.minutes).toBe('25');
  });
});

describe('the second way of cooking it (M2)', () => {
  it('No wait on its step has an Undo that puts the wait back', async () => {
    const { flow, steps } = flowWith('25', 745);
    const second: ReviewStep = {
      kind: 'step',
      text: 'Soak.',
      wait: { ...MARINATE },
      wait_confirmed: false
    };
    (flow.review as unknown as { second_method: unknown }).second_method = {
      name: 'Instant Pot',
      steps: [second]
    };
    takeOffWait(flow, second);
    expect(second.wait).toBeNull();
    await undoHistory.undoLast();
    expect(second.wait).toEqual(MARINATE);
  });
});

describe('taking out a step that waits (M1 review round 2, L3)', () => {
  it('gives its minutes back, and Undo takes them again', async () => {
    const { flow, steps } = flowWith('25', 745);
    removeStep(flow, 0);
    expect(steps).toHaveLength(1);
    expect(flow.minutes).toBe('745');
    await undoHistory.undoLast();
    expect(steps).toHaveLength(2);
    expect(flow.minutes).toBe('25');
  });
});
