// "No portions left" for the drop zone and the one-day picker (0.7 P1, cabledrawer 28 Oct).
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { PlanModel } from '#lib/plan.svelte.js';
import type { PlanActions } from '#lib/planActions.js';
import { changeOf, fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import NoPortions from './NoPortions.svelte';
import '../../styles/tokens.css';
import '../../styles/base.css';

describe('No portions left, after a Leftovers here drop', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];
  let model: PlanModel;

  beforeEach(() => {
    undoHistory.clear();
    toasts.dismiss();
    model = new PlanModel();
    model.today = '2026-10-19';
    model.slots = [{ id: 2, name: 'Lunch', position: 1, enabled: true }];
    let answered = 0;
    requests = fakeApi({
      'POST /plan/items/11/move': () =>
        answered++ === 0
          ? [409, { detail: 'No portions left.', code: 'no_portions_left', left: 0, wanted: 1 }]
          : [200, { change: changeOf(900, 'Planned leftovers'), meal_id: 1, item_id: 11 }],
      'GET /plan': [200, { start: '', end: '', meals: [], batch_cooks: [], tubs: [] }]
    });
    const actions = { model, readonly: false } as unknown as PlanActions;
    component = mount(NoPortions, { target: document.body, props: { actions } });
    flushSync();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  const sent = () => requests.filter((r) => r.method === 'POST').map((r) => r.body);

  it('asks by default, shows the alert, and a Cook more answer is sent', async () => {
    void model.drop({ item: 11 }, '2026-10-21', 2, 'leftovers');
    const dialog = page.getByRole('dialog', { name: 'No portions left' });
    await expect
      .element(dialog.getByRole('alert'))
      .toHaveTextContent('No portions left for Wed 21 lunch.');
    expect(toasts.current?.tone).not.toBe('problem'); // the sheet asks, no "Couldn’t save"
    expect(sent()).toEqual([
      { date: '2026-10-21', slot_id: 2, mode: 'leftovers', if_none_left: 'ask' }
    ]);
    await dialog.getByRole('button', { name: /Cook more/ }).click();
    await expect.poll(sent).toEqual([
      { date: '2026-10-21', slot_id: 2, mode: 'leftovers', if_none_left: 'ask' },
      { date: '2026-10-21', slot_id: 2, mode: 'leftovers', if_none_left: 'cook_more' }
    ]);
    expect(model.noPortions).toBeNull();
  });

  it('Cancel puts it away and sends nothing more', async () => {
    void model.drop({ item: 11 }, '2026-10-21', 2, 'leftovers');
    const dialog = page.getByRole('dialog', { name: 'No portions left' });
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    expect(model.noPortions).toBeNull();
    expect(sent()).toHaveLength(1);
  });

  it('a move or copy never sends the choice', async () => {
    void model.drop({ item: 11 }, '2026-10-21', 2, 'move');
    await expect.poll(sent).toEqual([{ date: '2026-10-21', slot_id: 2, mode: 'move' }]);
  });
});
