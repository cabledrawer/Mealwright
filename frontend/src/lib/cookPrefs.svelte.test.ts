import { afterEach, describe, expect, it, vi } from 'vitest';
import { CookPrefs, OLD_PER_STEP_KEY } from './cookPrefs.svelte';

const household = (on: boolean) =>
  new Response(JSON.stringify({ name: 'Home', cook_per_step: on }), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });

function serve(handler: (method: string, body: unknown) => Response | Promise<Response>) {
  const calls: { method: string; body: unknown }[] = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const body = init.body ? JSON.parse(String(init.body)) : undefined;
    // Only the household calls count: the offline check of an earlier test may ask for the version.
    if (url === '/api/v1/household') calls.push({ method: String(init.method), body });
    return handler(String(init.method), body);
  });
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.removeItem(OLD_PER_STEP_KEY);
});

describe('Cook mode’s per-step ingredients switch (a household setting)', () => {
  it('is off until the household says otherwise', async () => {
    expect(new CookPrefs().perStep).toBe(false);
    serve(() => household(true));
    const prefs = new CookPrefs();
    await prefs.load();
    expect(prefs.perStep).toBe(true);
  });

  it('is saved to the household, and a fresh screen reads it back', async () => {
    let stored = false;
    const calls = serve((method, body) => {
      if (method === 'PATCH') stored = (body as { cook_per_step: boolean }).cook_per_step;
      return household(stored);
    });
    const prefs = new CookPrefs();
    expect(await prefs.setPerStep(true)).toBeNull();
    expect(prefs.perStep).toBe(true);
    expect(calls).toEqual([{ method: 'PATCH', body: { cook_per_step: true } }]);
    const second = new CookPrefs();
    await second.load();
    expect(second.perStep).toBe(true);
    expect(await prefs.setPerStep(false)).toBeNull();
    await second.load();
    expect(second.perStep).toBe(false);
  });

  it('goes back to what it was, and says so in one short line, when the server can’t be reached', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('network down');
    });
    const prefs = new CookPrefs();
    const line = await prefs.setPerStep(true);
    expect(prefs.perStep).toBe(false);
    expect(line).toMatch(/Nothing was changed\.$/);
  });

  it('goes back too when the server answers with an error', async () => {
    serve(() => new Response('{"detail":"no"}', { status: 500 }));
    const prefs = new CookPrefs();
    prefs.perStep = true;
    const line = await prefs.setPerStep(false);
    expect(prefs.perStep).toBe(true);
    expect(line).toBe('Couldn’t save. Try again.');
  });

  it('keeps what it had when the household can’t be read', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('network down');
    });
    const prefs = new CookPrefs();
    prefs.perStep = true;
    await prefs.load();
    expect(prefs.perStep).toBe(true);
  });

  it('no longer uses this device’s old key: a device that had it on does not switch the household on', async () => {
    localStorage.setItem(OLD_PER_STEP_KEY, '1');
    const calls = serve(() => household(false));
    const prefs = new CookPrefs();
    expect(prefs.perStep).toBe(false);
    await prefs.load();
    expect(prefs.perStep).toBe(false);
    expect(calls.every((c) => c.method === 'GET')).toBe(true);
    expect(localStorage.getItem(OLD_PER_STEP_KEY)).toBeNull();
  });

  it('the error line clears after a later flip that works', async () => {
    let fail = true;
    serve(() => (fail ? new Response('{"detail":"no"}', { status: 500 }) : household(true)));
    const prefs = new CookPrefs();
    await prefs.setPerStep(true);
    expect(prefs.problem).toBe('Couldn’t save. Try again.');
    fail = false;
    await prefs.setPerStep(true);
    expect(prefs.problem).toBeNull();
    expect(prefs.perStep).toBe(true);
  });

  it('a failed flip’s error line is gone when Cook mode is opened again, and when it is left', async () => {
    serve((method) =>
      method === 'PATCH' ? new Response('{"detail":"no"}', { status: 500 }) : household(false)
    );
    const prefs = new CookPrefs();
    await prefs.setPerStep(true);
    expect(prefs.problem).toBe('Couldn’t save. Try again.');
    prefs.leave();
    expect(prefs.problem).toBeNull();
    await prefs.setPerStep(true);
    expect(prefs.problem).not.toBeNull();
    await prefs.load(); // Cook mode opened again
    expect(prefs.problem).toBeNull();
  });

  it('a read that comes back after the person flipped the switch is ignored', async () => {
    let release: (r: Response) => void = () => {};
    const slow = new Promise<Response>((resolve) => (release = resolve));
    const prefs = new CookPrefs();
    vi.stubGlobal('fetch', async (_url: string, init: RequestInit) =>
      init.method === 'GET' ? slow : household(true)
    );
    const loading = prefs.load();
    await prefs.setPerStep(true);
    release(household(false)); // the old answer, from before the flip
    await loading;
    expect(prefs.perStep).toBe(true);
  });
});
