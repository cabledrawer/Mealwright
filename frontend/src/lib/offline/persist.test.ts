import { describe, expect, it, vi } from 'vitest';
import { askToKeepData, type PersistEnv } from './persist';

function env(over: Partial<PersistEnv> = {}) {
  const storage = { persist: vi.fn(async () => true), persisted: vi.fn(async () => false) };
  const remember = vi.fn();
  return {
    storage,
    remember,
    env: {
      standalone: true,
      firefox: false,
      storage,
      asked: () => false,
      remember,
      ...over
    } satisfies PersistEnv
  };
}

describe('asking the browser to keep our data', () => {
  it('asks once the app is installed, and remembers it did', async () => {
    const t = env();
    expect(await askToKeepData(t.env)).toBe(true);
    expect(t.storage.persist).toHaveBeenCalledOnce();
    expect(t.remember).toHaveBeenCalledOnce();
  });

  it('does not ask in a normal browser tab', async () => {
    const t = env({ standalone: false });
    expect(await askToKeepData(t.env)).toBe(false);
    expect(t.storage.persist).not.toHaveBeenCalled();
  });

  it('does not ask where the browser would show a question (Firefox)', async () => {
    const t = env({ firefox: true });
    await askToKeepData(t.env);
    expect(t.storage.persist).not.toHaveBeenCalled();
  });

  it('does not ask twice, or when the browser has no storage manager', async () => {
    const twice = env({ asked: () => true });
    await askToKeepData(twice.env);
    expect(twice.storage.persist).not.toHaveBeenCalled();
    expect(await askToKeepData(env({ storage: undefined }).env)).toBe(false);
  });

  it('does not ask when the data is already kept', async () => {
    const t = env();
    t.storage.persisted.mockResolvedValue(true);
    expect(await askToKeepData(t.env)).toBe(true);
    expect(t.storage.persist).not.toHaveBeenCalled();
  });
});
