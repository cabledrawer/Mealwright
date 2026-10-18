import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { breakPhone, dropPhone, freshPhone } from '$lib/testing/phone';
import { storedLoginId } from './device';
import {
  cantCheckText,
  heldChanges,
  keptText,
  loseOnSignOutText,
  loseOthersText,
  sameUsername,
  storedWaiting,
  UNREADABLE,
  waitingForText
} from './held';
import { closePhone, deletePhone, phoneDatabaseName, sealPhone, setMeta } from './phone';
import { addToQueue } from './store';

const WREN = { login_id: 2, login_name: 'Wren', username: 'wren', role: 'member' };
const DEVICE = '11111111-2222-4333-8444-555555555555';
const tick = (id: string) => ({
  id,
  made_at: '2026-10-18T09:00:00Z',
  seen: 0,
  kind: 'tick' as const,
  item_id: 'i'
});

beforeEach(() => freshPhone());
afterEach(async () => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  await dropPhone();
});

describe('changes held on this phone', () => {
  it('counts the last signed-in person’s waiting changes only', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    await addToQueue(tick('b'), 2, DEVICE);
    await addToQueue(tick('c'), 1, DEVICE);
    expect(await heldChanges()).toEqual({
      who: { id: 2, name: 'Wren', username: 'wren', role: 'member' },
      count: 2,
      ids: ['a', 'b']
    });
  });

  it('none when nothing is waiting, or nobody signed in here', async () => {
    expect(await heldChanges()).toBeNull();
    await setMeta({ ...WREN, device_id: DEVICE });
    expect(await heldChanges()).toBeNull();
  });

  it('a tab sealed by another tab’s wipe still reads a database made again since, without making one', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    sealPhone();
    expect(await heldChanges()).toMatchObject({ who: { id: 2 }, count: 1, ids: ['a'] });
    expect(await storedLoginId()).toBe(2);
    await deletePhone();
    expect(await heldChanges()).toBeNull();
    expect(await storedLoginId()).toBeNull();
    const names = (await indexedDB.databases()).map((d) => d.name);
    expect(names).not.toContain(phoneDatabaseName());
  });

  it('looking doesn’t make a database after a wipe', async () => {
    await deletePhone();
    expect(await heldChanges()).toBeNull();
    const names = (await indexedDB.databases()).map((d) => d.name);
    expect(names).not.toContain(phoneDatabaseName());
  });

  it('says 1 change and 3 changes', () => {
    expect(keptText(3)).toBe('Please sign in again. Your 3 changes are kept on this phone.');
    expect(keptText(1)).toBe('Please sign in again. Your 1 change is kept on this phone.');
    expect(waitingForText('Wren', 3)).toBe(
      "Wren's 3 changes are waiting on this phone. Sign in as Wren to send them."
    );
    expect(waitingForText('Wren', 1)).toBe(
      "Wren's 1 change is waiting on this phone. Sign in as Wren to send it."
    );
    // With the sidebar, it's this computer (by layout).
    expect(keptText(2, 'computer')).toBe(
      'Please sign in again. Your 2 changes are kept on this computer.'
    );
    expect(waitingForText('Wren', 1, 'computer')).toBe(
      "Wren's 1 change is waiting on this computer. Sign in as Wren to send it."
    );
    expect(loseOthersText('Wren', 3)).toBe(
      "Wren's 3 changes haven't been sent yet. If you carry on, they're lost."
    );
    expect(loseOthersText('Wren', 1)).toBe(
      "Wren's 1 change hasn't been sent yet. If you carry on, it's lost."
    );
    expect(loseOnSignOutText(3)).toBe(
      "3 changes haven't been sent yet. If you sign out now, they're lost."
    );
    expect(loseOnSignOutText(1)).toBe(
      "1 change hasn't been sent yet. If you sign out now, it's lost."
    );
  });

  it('compares usernames as the server does', () => {
    const wren = { id: 2, name: 'Wren', username: 'wren', role: 'member' };
    expect(sameUsername(' Wren ', wren)).toBe(true);
    expect(sameUsername('arlo', wren)).toBe(false);
  });
});

describe('a phone database that can’t be read', () => {
  it('is “couldn’t read”, never “nothing waiting” or “nobody here”', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    const mend = breakPhone();
    expect(await heldChanges()).toBe(UNREADABLE);
    expect(await storedLoginId()).toBe(UNREADABLE);
    expect(await storedWaiting(2)).toBe(UNREADABLE);
    // Mended, it reads as it always did.
    mend();
    expect(await heldChanges()).toMatchObject({ who: { id: 2 }, count: 1 });
    expect(await storedLoginId()).toBe(2);
    expect(await storedWaiting(2)).toEqual(['a']);
  });

  it('nor when the browser can’t even list its databases', async () => {
    await setMeta({ ...WREN, device_id: DEVICE });
    await addToQueue(tick('a'), 2, DEVICE);
    closePhone();
    vi.spyOn(indexedDB, 'databases').mockRejectedValue(new DOMException('broken', 'UnknownError'));
    expect(await heldChanges()).toBe(UNREADABLE);
    expect(await storedLoginId()).toBe(UNREADABLE);
    expect(await storedWaiting(2)).toBe(UNREADABLE);
  });

  it('a browser with no IndexedDB at all has nothing kept: nothing is waiting', async () => {
    vi.stubGlobal('indexedDB', undefined);
    expect(await heldChanges()).toBeNull();
    expect(await storedLoginId()).toBeNull();
    expect(await storedWaiting(2)).toEqual([]);
  });

  it('says so, and that nothing has been deleted', () => {
    expect(cantCheckText()).toBe(
      "This phone couldn't check for changes waiting to be sent. Nothing has been deleted."
    );
    expect(cantCheckText('computer')).toBe(
      "This computer couldn't check for changes waiting to be sent. Nothing has been deleted."
    );
  });
});
