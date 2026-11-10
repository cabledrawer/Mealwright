import { describe, expect, it } from 'vitest';
import { onceLoader } from './loadReviewPage.js';

describe('the Check screen loader', () => {
  it('forgets a failed load, so Try again fetches it afresh, and keeps a good one', async () => {
    let calls = 0;
    const load = onceLoader(() => {
      calls += 1;
      return calls === 1 ? Promise.reject(new Error('chunk blocked')) : Promise.resolve('page');
    });
    await expect(load()).rejects.toThrow('chunk blocked');
    await expect(load()).resolves.toBe('page');
    await expect(load()).resolves.toBe('page');
    expect(calls).toBe(2);
  });
});
