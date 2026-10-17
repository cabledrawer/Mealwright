import { describe, expect, it } from 'vitest';
import { newChangeId, uuidFromBytes } from './changeId';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('change IDs', () => {
  it('are version 4 UUIDs, different every time', () => {
    const ids = new Set(Array.from({ length: 200 }, newChangeId));
    expect(ids.size).toBe(200);
    for (const id of ids) expect(id).toMatch(UUID_V4);
  });

  it('can be made without crypto.randomUUID (plain http:// pages)', () => {
    expect(uuidFromBytes(new Uint8Array(16).fill(0xff))).toBe(
      'ffffffff-ffff-4fff-bfff-ffffffffffff'
    );
    expect(uuidFromBytes(new Uint8Array(16))).toBe('00000000-0000-4000-8000-000000000000');
    expect(uuidFromBytes(crypto.getRandomValues(new Uint8Array(16)))).toMatch(UUID_V4);
  });

  it('refuses the wrong number of bytes', () => {
    expect(() => uuidFromBytes(new Uint8Array(15))).toThrow();
  });
});
