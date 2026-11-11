import { describe, expect, it, vi } from 'vitest';
import { askPicks, reopenLast, type Asks } from './batchFlow';
import type { BatchBody } from './client/plan';

const asks = (method: number | null | undefined, use: number[] | null | undefined): Asks => ({
  method: vi.fn(async () => method),
  optional: vi.fn(async () => use)
});

describe('asking about one recipe of Plan this batch', () => {
  it('sends the way and the optional ingredients that were picked', async () => {
    const a = asks(7, [3, 4]);
    expect(await askPicks(1, 'Sun 15 Nov', a)).toEqual({ method_id: 7, optional_use: [3, 4] });
    // The optional question is for the way chosen.
    expect(a.optional).toHaveBeenCalledWith(1, 'Sun 15 Nov', 7);
  });

  it('sends nothing for a question that had nothing to ask', async () => {
    expect(await askPicks(1, 'Sun', asks(undefined, undefined))).toEqual({});
    expect(await askPicks(1, 'Sun', asks(undefined, []))).toEqual({ optional_use: [] });
  });

  it('plans nothing when the person cancels either question', async () => {
    expect(await askPicks(1, 'Sun', asks(null, [1]))).toBeNull();
    expect(await askPicks(1, 'Sun', asks(7, null))).toBeNull();
  });

  it('does not ask about the optional ingredients after a cancelled way', async () => {
    const a = asks(null, [1]);
    await askPicks(1, 'Sun', a);
    expect(a.optional).not.toHaveBeenCalled();
  });
});

describe('after Plan this batch was refused (H10)', () => {
  it('offers the last sheet again and keeps every earlier answer', () => {
    const body = (n: number): BatchBody => ({
      tub_count: n,
      pattern: 'pick',
      member_ids: [],
      extras_to_freezer: false
    });
    const picked = [{ method_id: 5 }, {}, { optional_use: [] }];
    const flow = reopenLast([body(2), body(3), body(4)], picked);
    expect(flow.at).toBe(2);
    expect(flow.bodies.map((b) => b.tub_count)).toEqual([2, 3]);
    expect(flow.picked).toEqual(picked);
  });
});
