import { describe, expect, it } from 'vitest';
import { SendKey } from './sendKey';

describe('the change ID for a body', () => {
  it('keeps the ID while the body is the same, and makes a new one when it changed', () => {
    const key = new SendKey();
    const first = key.for({ name: 'Sambar', serves: 4 });
    expect(key.for({ name: 'Sambar', serves: 4 })).toBe(first);
    const edited = key.for({ name: 'Sambar', serves: 6 });
    expect(edited).not.toBe(first);
    expect(key.for({ name: 'Sambar', serves: 6 })).toBe(edited);
  });

  it('starts again with a new ID on reset', () => {
    const key = new SendKey();
    const first = key.for({ a: 1 });
    key.reset();
    expect(key.for({ a: 1 })).not.toBe(first);
  });
});
