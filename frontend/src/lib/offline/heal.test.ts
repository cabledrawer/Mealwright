import { describe, expect, it } from 'vitest';
import { answer, install, usable, type CacheLike, type StorageLike } from './heal';

/** A cache kept in a map; `broken` makes reading it fail, `failPut` makes keeping fail. */
function fakeStorage(start: Record<string, Record<string, Response>> = {}) {
  const store = new Map(Object.entries(start).map(([n, f]) => [n, new Map(Object.entries(f))]));
  const flags = { brokenOpen: false, failAdd: false, failPut: false };
  const cacheOf = (name: string): CacheLike => {
    const files = store.get(name) ?? new Map<string, Response>();
    store.set(name, files);
    return {
      match: async (key) => files.get(key)?.clone(),
      put: async (key, response) => {
        if (flags.failPut) throw new Error('quota');
        files.set(key, response);
      },
      delete: async (key) => files.delete(key),
      addAll: async (requests) => {
        for (const request of requests) {
          files.set(new URL(request.url, 'http://x').pathname, new Response('new'));
          if (flags.failAdd) throw new Error('network');
        }
      }
    };
  };
  const storage: StorageLike = {
    open: async (name) => {
      if (flags.brokenOpen) throw new Error('unreadable');
      return cacheOf(name);
    },
    delete: async (name) => store.delete(name)
  };
  return { storage, store, flags };
}

const noNetwork = async () => {
  throw new TypeError('Failed to fetch');
};

describe('the service worker cache heals itself', () => {
  it('counts only a plain 200 as usable', () => {
    expect(usable(new Response('x'))).toBe(true);
    expect(usable(new Response('x', { status: 500 }))).toBe(false);
    expect(usable(new Response('x', { status: 404 }))).toBe(false);
    expect(usable(undefined)).toBe(false);
  });

  it('serves a good copy from the cache with no connection', async () => {
    const { storage } = fakeStorage({ v1: { '/a.js': new Response('good') } });
    const got = await answer(storage, 'v1', '/a.js', noNetwork);
    expect(await got.text()).toBe('good');
  });

  it('fetches fresh when a file is missing, and keeps it', async () => {
    const { storage, store } = fakeStorage({ v1: {} });
    const got = await answer(storage, 'v1', '/a.js', async () => new Response('fresh'));
    expect(await got.text()).toBe('fresh');
    expect(await store.get('v1')?.get('/a.js')?.text()).toBe('fresh');
  });

  it('drops a bad copy (an error page left in the cache) and fetches fresh', async () => {
    const { storage, store } = fakeStorage({
      v1: { '/a.js': new Response('oops', { status: 500 }) }
    });
    const got = await answer(storage, 'v1', '/a.js', async () => new Response('fresh'));
    expect(await got.text()).toBe('fresh');
    expect(await store.get('v1')?.get('/a.js')?.text()).toBe('fresh');
  });

  it('with a bad copy and no connection, drops it and passes the failure on', async () => {
    const { storage, store } = fakeStorage({
      v1: { '/a.js': new Response('oops', { status: 500 }) }
    });
    await expect(answer(storage, 'v1', '/a.js', noNetwork)).rejects.toThrow('Failed to fetch');
    expect(store.get('v1')?.has('/a.js')).toBe(false);
  });

  it('treats a cache that cannot be opened as empty and still answers from the network', async () => {
    const { storage, flags } = fakeStorage();
    flags.brokenOpen = true;
    const got = await answer(storage, 'v1', '/a.js', async () => new Response('fresh'));
    expect(await got.text()).toBe('fresh');
  });

  it('still answers when the fresh copy cannot be kept', async () => {
    const { storage, flags } = fakeStorage({ v1: {} });
    flags.failPut = true;
    const got = await answer(storage, 'v1', '/a.js', async () => new Response('fresh'));
    expect(await got.text()).toBe('fresh');
  });

  it('never keeps an error answer from the network', async () => {
    const { storage, store } = fakeStorage({ v1: {} });
    const got = await answer(
      storage,
      'v1',
      '/a.js',
      async () => new Response('no', { status: 503 })
    );
    expect(got.status).toBe(503);
    expect(store.get('v1')?.has('/a.js')).toBe(false);
  });

  it('an install starts clean over a half-written cache of the same name', async () => {
    const { storage, store } = fakeStorage({ v1: { '/stale.js': new Response('half') } });
    await install(storage, 'v1', [new Request('http://x/a.js')]);
    expect([...(store.get('v1')?.keys() ?? [])]).toEqual(['/a.js']);
  });

  it('a failed install leaves no half-filled cache behind and passes the failure on', async () => {
    const { storage, store, flags } = fakeStorage();
    flags.failAdd = true;
    await expect(install(storage, 'v1', [new Request('http://x/a.js')])).rejects.toThrow('network');
    expect(store.has('v1')).toBe(false);
  });
});
