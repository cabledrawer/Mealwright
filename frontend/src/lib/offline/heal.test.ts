import { describe, expect, it } from 'vitest';
import {
  FIRST_INSTALL_MARK,
  INSTALL_AT_ONCE,
  answer,
  markFirstInstall,
  takeFirstInstallMark,
  install,
  usable,
  type CacheLike,
  type StorageLike
} from './heal';

/** A cache kept in a map; `broken` makes reading it fail, `failPut` makes keeping fail. */
function fakeStorage(start: Record<string, Record<string, Response>> = {}) {
  const store = new Map(Object.entries(start).map(([n, f]) => [n, new Map(Object.entries(f))]));
  const flags = { brokenOpen: false, failPut: false };
  const cacheOf = (name: string): CacheLike => {
    const files = store.get(name) ?? new Map<string, Response>();
    store.set(name, files);
    return {
      match: async (key) => files.get(key)?.clone(),
      put: async (key, response) => {
        if (flags.failPut) throw new Error('quota');
        files.set(new URL(key, 'http://x').pathname, response);
      },
      delete: async (key) => files.delete(key)
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
    await install(storage, 'v1', [new Request('http://x/a.js')], async () => new Response('new'));
    expect([...(store.get('v1')?.keys() ?? [])]).toEqual(['/a.js']);
  });

  it('a failed install leaves no half-filled cache behind and passes the failure on', async () => {
    const { storage, store } = fakeStorage();
    await expect(install(storage, 'v1', [new Request('http://x/a.js')], noNetwork)).rejects.toThrow(
      'Failed to fetch'
    );
    expect(store.has('v1')).toBe(false);
  });

  it('refuses a redirected, partial, opaque or error answer', () => {
    const redirected = new Response('login page');
    Object.defineProperty(redirected, 'redirected', { value: true });
    expect(usable(redirected)).toBe(false);
    expect(usable(new Response('part', { status: 206 }))).toBe(false);
    const opaque = new Response('x');
    Object.defineProperty(opaque, 'type', { value: 'opaque' });
    expect(usable(opaque)).toBe(false);
    expect(usable(Response.error())).toBe(false);
  });

  it('an install stops, and keeps nothing, when a file comes back redirected', async () => {
    const { storage, store } = fakeStorage();
    const bad = new Response('login page');
    Object.defineProperty(bad, 'redirected', { value: true });
    await expect(
      install(storage, 'v1', [new Request('http://x/a.js')], async () => bad)
    ).rejects.toThrow('Could not fetch');
    expect(store.has('v1')).toBe(false);
  });

  it('never keeps a redirected answer from the network', async () => {
    const { storage, store } = fakeStorage({ v1: {} });
    const bad = new Response('login page');
    Object.defineProperty(bad, 'redirected', { value: true });
    const got = await answer(storage, 'v1', '/a.js', async () => bad);
    expect(await got.text()).toBe('login page');
    expect(store.get('v1')?.has('/a.js')).toBe(false);
  });

  it('downloads in groups, never more than INSTALL_AT_ONCE in flight, and keeps the order', async () => {
    expect(INSTALL_AT_ONCE).toBe(6);
    const { storage, store } = fakeStorage();
    const names = Array.from({ length: 20 }, (_, i) => `/f${i}.js`);
    let inFlight = 0;
    let most = 0;
    await install(
      storage,
      'v1',
      names.map((n) => new Request(`http://x${n}`)),
      async (request) => {
        inFlight++;
        most = Math.max(most, inFlight);
        // Later files answer first, so a wrong order would show.
        await new Promise((done) =>
          setTimeout(done, 20 - Number(new URL(request.url).pathname.slice(2, -3)))
        );
        inFlight--;
        return new Response('x');
      }
    );
    expect(most).toBe(INSTALL_AT_ONCE);
    expect([...(store.get('v1')?.keys() ?? [])]).toEqual(names);
  });

  it('a file failing in the middle of a group drops the whole cache and starts no more', async () => {
    const { storage, store } = fakeStorage();
    const asked: string[] = [];
    const names = Array.from({ length: 14 }, (_, i) => `/f${i}.js`);
    await expect(
      install(
        storage,
        'v1',
        names.map((n) => new Request(`http://x${n}`)),
        async (request) => {
          const path = new URL(request.url).pathname;
          asked.push(path);
          return path === '/f8.js' ? new Response('no', { status: 503 }) : new Response('x');
        }
      )
    ).rejects.toThrow('Could not fetch http://x/f8.js');
    expect(store.has('v1')).toBe(false);
    expect(asked).toHaveLength(12); // the groups of 0-5 and 6-11; the third never starts
  });
});

describe('the first-install mark', () => {
  it('is kept in the cache, read once and then gone, and never counts as an app file', async () => {
    const { storage, store } = fakeStorage();
    await install(storage, 'v1', [new Request('http://x/a.js')], async () => new Response('x'));
    expect(await takeFirstInstallMark(storage, 'v1')).toBe(false); // nothing marked yet
    await markFirstInstall(storage, 'v1');
    expect([...(store.get('v1')?.keys() ?? [])]).toEqual(['/a.js', FIRST_INSTALL_MARK]);
    expect(await takeFirstInstallMark(storage, 'v1')).toBe(true);
    expect(await takeFirstInstallMark(storage, 'v1')).toBe(false); // taken
    expect([...(store.get('v1')?.keys() ?? [])]).toEqual(['/a.js']);
  });

  it('is never served: asking for its address goes to the network like any other unknown file', async () => {
    // The worker only answers KNOWN files; the mark's address is not among the app's files.
    const { handling } = await import('./rules');
    const known = new Set(['/a.js']);
    const url = new URL(FIRST_INSTALL_MARK, 'http://x');
    expect(handling(new Request(url), url, 'http://x', known)).toBe('network');
  });

  it('an unreadable cache means no mark (the safe side: no claim)', async () => {
    const { storage, flags } = fakeStorage();
    flags.brokenOpen = true;
    await markFirstInstall(storage, 'v1'); // must not throw
    expect(await takeFirstInstallMark(storage, 'v1')).toBe(false);
  });
});
