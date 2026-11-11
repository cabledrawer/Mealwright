// Another tab wipes this browser (sign-out): this tab hears it, by any of the three ways,
// and seals its database so it never makes it again (cabledrawer 18 Oct).

import { deleteDB } from 'idb';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { deviceId, loadDeviceId, startDevice } from './device';
import { getMeta, openPhone, phoneDatabaseName, setMeta } from './phone';
import { onWipedElsewhere, tellOtherTabs, WIPED } from './otherTabs';

const ALEX = { id: 2, name: 'Alex', username: 'alex', role: 'member' };
let stop: () => void = () => {};

beforeEach(() => freshPhone());
afterEach(async () => {
  stop();
  await dropPhone();
});

const names = async () => (await indexedDB.databases()).map((db) => db.name);

describe('another tab wiped this browser', () => {
  it('heard on the channel: this tab seals its database, forgets the device ID, and is told', async () => {
    const before = await loadDeviceId();
    const heard = vi.fn();
    stop = onWipedElsewhere(heard);
    const otherTab = new BroadcastChannel(WIPED);
    otherTab.postMessage({ db: phoneDatabaseName() });
    otherTab.close();
    await vi.waitFor(() => expect(heard).toHaveBeenCalledOnce());
    expect(deviceId()).not.toBe(before);
    // The other tab deletes the database; this one never makes it again, even when asked.
    await deleteDB(phoneDatabaseName());
    await expect(setMeta({ cursor: 3 })).rejects.toThrow();
    await expect(getMeta('login_id')).rejects.toThrow();
    expect(await names()).not.toContain(phoneDatabaseName());
  });

  it('heard when the database is deleted under it (versionchange), once only', async () => {
    await setMeta({ cursor: 1 });
    const heard = vi.fn();
    stop = onWipedElsewhere(heard);
    // As another tab does: delete while this tab has it open. This tab lets go, so it goes.
    await deleteDB(phoneDatabaseName());
    expect(heard).toHaveBeenCalledOnce();
    await expect(openPhone()).rejects.toThrow();
    expect(await names()).not.toContain(phoneDatabaseName());
    // The channel saying so too doesn't run it again.
    const otherTab = new BroadcastChannel(WIPED);
    otherTab.postMessage({ db: phoneDatabaseName() });
    otherTab.close();
    await new Promise((r) => setTimeout(r, 50));
    expect(heard).toHaveBeenCalledOnce();
  });

  it('heard through the storage event, where there is no BroadcastChannel', async () => {
    const heard = vi.fn();
    stop = onWipedElsewhere(heard);
    window.dispatchEvent(
      new StorageEvent('storage', { key: WIPED, newValue: phoneDatabaseName() })
    );
    expect(heard).toHaveBeenCalledOnce();
  });

  it('only this database counts (each test file has its own)', async () => {
    const heard = vi.fn();
    stop = onWipedElsewhere(heard);
    const otherTab = new BroadcastChannel(WIPED);
    otherTab.postMessage({ db: 'test-someone-else' });
    otherTab.close();
    window.dispatchEvent(new StorageEvent('storage', { key: WIPED, newValue: 'test-else' }));
    await new Promise((r) => setTimeout(r, 50));
    expect(heard).not.toHaveBeenCalled();
  });

  it('signing in again opens the database again', async () => {
    stop = onWipedElsewhere(() => {});
    window.dispatchEvent(
      new StorageEvent('storage', { key: WIPED, newValue: phoneDatabaseName() })
    );
    await expect(openPhone()).rejects.toThrow();
    await startDevice(ALEX);
    expect(await getMeta('login_id')).toBe(2);
  });

  it('the wiping tab tells the others, and doesn’t hear itself', async () => {
    const otherTab = new BroadcastChannel(WIPED);
    const got = new Promise((resolve) => (otherTab.onmessage = (e) => resolve(e.data)));
    const heard = vi.fn();
    stop = onWipedElsewhere(heard);
    tellOtherTabs();
    expect(await got).toEqual({ db: phoneDatabaseName() });
    otherTab.close();
    await new Promise((r) => setTimeout(r, 50));
    expect(heard).not.toHaveBeenCalled();
    expect(localStorage.getItem(WIPED)).toBeNull();
  });
});
