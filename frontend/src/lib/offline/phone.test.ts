import { openDB } from 'idb';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import pkg from '../../../package.json';
import { deviceId, forgetDeviceId, loadDeviceId, OLD_DEVICE_KEY, startDevice } from './device';
import {
  ALL_COPY_STORES,
  closePhone,
  DB_NAME,
  DB_VERSION,
  deletePhone,
  getMeta,
  openPhone,
  openPhoneAt,
  phoneDatabaseName,
  usePhoneDatabase
} from './phone';

const UUID = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;

beforeEach(async () => {
  usePhoneDatabase(`test-phone-${crypto.randomUUID()}`);
  forgetDeviceId();
  localStorage.removeItem(OLD_DEVICE_KEY);
});

afterEach(async () => {
  await deletePhone();
  localStorage.removeItem(OLD_DEVICE_KEY);
});

describe('the phone database (sync-protocol 11.1)', () => {
  it('is called mealwright', () => {
    expect(DB_NAME).toBe('mealwright');
  });

  it('has meta, queue and one store per kind of the offline copy', async () => {
    const db = await openPhone();
    expect([...db.objectStoreNames].sort()).toEqual(
      [
        'meta',
        'queue',
        'copy.aisles',
        'copy.foods',
        'copy.items',
        'copy.lists',
        'copy.notes',
        'copy.people',
        'copy.places',
        'copy.questions',
        'copy.removed',
        'copy.shops'
      ].sort()
    );
    expect(ALL_COPY_STORES).toHaveLength(10);
  });

  it('FE-5: has no pantry store', async () => {
    const db = await openPhone();
    for (const store of db.objectStoreNames) {
      expect(store).not.toMatch(/pantry|stock|lot|use/i);
    }
  });

  it('numbers the queue in the order changes go in', async () => {
    const db = await openPhone();
    const a = await db.add('queue', { action: { id: 'a' } });
    const b = await db.add('queue', { action: { id: 'b' } });
    expect(Number(b)).toBeGreaterThan(Number(a));
    expect((await db.getAll('queue')).map((e) => e.action.id)).toEqual(['a', 'b']);
  });
});

describe('FE-4 (part 1): a newer version opens an older version’s database', () => {
  it('keeps queue and meta exactly, and adds the stores it needs', async () => {
    // An older version's database: only meta and queue, with a change waiting.
    const old = await openDB(phoneDatabaseName(), 1, {
      upgrade(db) {
        db.createObjectStore('meta');
        db.createObjectStore('queue', { keyPath: 'seq', autoIncrement: true });
      }
    });
    const entry = {
      action: { id: 'x1', made_at: '2026-10-01T10:00:00Z', seen: 12, kind: 'tick', item_id: 'i' },
      login_id: 1,
      device_id: '11111111-2222-4333-8444-555555555555',
      queued_at: '2026-10-01T10:00:00Z',
      tries: 3
    };
    await old.add('queue', entry);
    await old.put('meta', '11111111-2222-4333-8444-555555555555', 'device_id');
    await old.put('meta', 12, 'cursor');
    old.close();

    const db = await openPhoneAt(DB_VERSION + 1);
    expect(await db.getAll('queue')).toEqual([{ ...entry, seq: 1 }]);
    expect(await db.get('meta', 'device_id')).toBe('11111111-2222-4333-8444-555555555555');
    expect(await db.get('meta', 'cursor')).toBe(12);
    for (const store of ALL_COPY_STORES) expect(db.objectStoreNames.contains(store)).toBe(true);
    db.close();
  });
});

describe('FE-4 (part 2): an update never takes over mid-shop', () => {
  // The app's own code: no new version is ever forced on an open window (sync-protocol 11.6).
  // Sending the old queue before Shopping shows is tested in routes/(app)/shopping.
  const sources = import.meta.glob(['/src/**/*.svelte', '/src/**/*.ts', '/static/**/*.js'], {
    query: '?raw',
    import: 'default',
    eager: true
  }) as Record<string, string>;
  const code = (text: string) =>
    text
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|[^:'"`])\/\/.*$/gm, '$1');

  it('nothing calls skipWaiting() or clients.claim()', () => {
    const app = Object.entries(sources).filter(([path]) => !path.endsWith('.test.ts'));
    expect(app.some(([path]) => path === '/src/service-worker/index.ts')).toBe(true);
    const callers = app
      .filter(([, text]) => /\bskipWaiting\s*\(|\bclaim\s*\(/.test(code(text)))
      .map(([path]) => path);
    expect(callers).toEqual([]);
  });
});

describe('FE-6: idb is pinned', () => {
  it('to an exact version, with no ^ or ~', () => {
    const version = (pkg.dependencies as Record<string, string>).idb;
    expect(version).toMatch(/^\d+\.\d+\.\d+$/);
  });
});

describe('the device ID (sync-protocol 11.8)', () => {
  it('is made once and kept in meta', async () => {
    const id = await loadDeviceId();
    expect(id).toMatch(UUID);
    expect(await getMeta('device_id')).toBe(id);
    forgetDeviceId();
    expect(await loadDeviceId()).toBe(id);
    expect(deviceId()).toBe(id);
  });

  it('moves in from localStorage with the same value, and the old place is cleared', async () => {
    const old = '0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d';
    localStorage.setItem(OLD_DEVICE_KEY, old);
    expect(await loadDeviceId()).toBe(old);
    expect(await getMeta('device_id')).toBe(old);
    expect(localStorage.getItem(OLD_DEVICE_KEY)).toBeNull();
  });

  it('clears the old place even when meta already has one', async () => {
    const id = await loadDeviceId();
    localStorage.setItem(OLD_DEVICE_KEY, '0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d');
    forgetDeviceId();
    expect(await loadDeviceId()).toBe(id);
    expect(localStorage.getItem(OLD_DEVICE_KEY)).toBeNull();
  });

  it('is new after the database is wiped', async () => {
    const first = await loadDeviceId();
    await deletePhone();
    forgetDeviceId();
    expect(await loadDeviceId()).not.toBe(first);
  });

  it('keeps who is signed in, for opening offline', async () => {
    await startDevice({ id: 3, name: 'Wren', username: 'wren', role: 'member' });
    expect(await getMeta('login_id')).toBe(3);
    expect(await getMeta('login_name')).toBe('Wren');
    expect(await getMeta('username')).toBe('wren');
    expect(await getMeta('protocol')).toBe(1);
    expect(await getMeta('device_id')).toMatch(UUID);
    closePhone();
  });
});
