import { spawn, type ChildProcess } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { request, test as base } from '@playwright/test';
import { ADMIN, AUTH_FILE, MAX_WORKERS, PORTS, WORKER_PORT_FIRST, insecure, local } from './servers.ts';

// One fixed date and time for every browser test and saved screenshot, the same for the browser
// and the servers, so a run that crosses midnight or a clock change (UK clocks go back on 25
// October) reads the same as any other. Every spec imports `test` and `expect` from here.
//
// The run starts at FIXED_MOMENT and time then passes normally. playwright.config.ts works out
// once per run how far that is from the real time (E2E_CLOCK_SHIFT_MS). The servers move their
// clock by that much (serve.mjs starts them with backend/scripts/e2e_server.py, test-only), and
// each test's browser starts at the real time moved by the same amount (Playwright's clock).
// Sign-in cookies last a number of seconds, so they work whatever the date.

export * from '@playwright/test';

/** The day every test runs on: a Saturday. */
export const FIXED_DAY = '2026-10-17';
/** 10:00 in London (British Summer Time): far from midnight and from the clock change. */
export const FIXED_MOMENT = Date.parse(`${FIXED_DAY}T09:00:00Z`);

/** How far the tests' clock is from the real one, in milliseconds (set in playwright.config.ts). */
export function clockShift(): number {
  const shift = Number(process.env.E2E_CLOCK_SHIFT_MS);
  if (process.env.E2E_CLOCK_SHIFT_MS === undefined || !Number.isFinite(shift)) {
    throw new Error('E2E_CLOCK_SHIFT_MS is not set (playwright.config.ts sets it)');
  }
  return shift;
}

/** Now, on the tests' clock. */
export const testNow = () => Date.now() + clockShift();

/** A worker's own server, as the tests see it. `storageState` is the admin's sign-in on it. */
export type WorkerServer = {
  port: number;
  url: string;
  /** The same server by a name that isn't localhost (plain http://, as a real install without HTTPS). */
  insecureUrl: string;
  storageState: Awaited<ReturnType<Awaited<ReturnType<typeof request.newContext>>['storageState']>>;
};

const BACKEND = fileURLToPath(new URL('../../backend', import.meta.url));
const FRONTEND_BUILD = fileURLToPath(new URL('../../frontend/build', import.meta.url));

async function waitUntilUp(port: number, child: ChildProcess) {
  for (let i = 0; i < 1200; i++) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`The worker's Mealwright server on port ${port} stopped while starting (${child.exitCode ?? child.signalCode}).`);
    }
    try {
      if ((await fetch(`${local(port)}/api/v1/version`, { signal: AbortSignal.timeout(2000) })).ok) return;
    } catch {
      // not up yet (a try gives up after 2 s: a closed port can hang for minutes here, not refuse)
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`The worker's Mealwright server on port ${port} didn't start in 120 s.`);
}

/** Every test in a worker runs on that worker's own Mealwright server (cabledrawer 8 Nov, T2b): the
 *  same test launcher serve.mjs uses (backend/scripts/e2e_server.py, the same clock shift), on its
 *  own port (PORTS: base + 4 + the worker's number) and its own empty data folder, with the admin
 *  set up and signed in. It stops, and its folder goes, when the worker ends. Nothing in Mealwright
 *  itself is different. The tests' `baseURL` and `storageState` (the saved sign-in every project
 *  that starts signed in gets) point at it. The first-run, strict and screenshots servers stay
 *  shared, one each per stream, as serve.mjs starts them. */
export const test = base.extend<{ app: WorkerServer }, { workerServer: WorkerServer }>({
  workerServer: [
    async ({}, use, workerInfo) => {
      if (workerInfo.parallelIndex >= MAX_WORKERS) {
        throw new Error(`E2E_WORKERS can be ${MAX_WORKERS} at most (a stream has ports for that many servers).`);
      }
      const port = WORKER_PORT_FIRST + workerInfo.parallelIndex;
      const scratch = mkdtempSync(join(tmpdir(), `mealwright-e2e-w${workerInfo.parallelIndex}-`));
      const dataDir = join(scratch, 'data');
      mkdirSync(dataDir);
      // Started through a small shell that stops the server when this worker is gone, even when the
      // worker is killed outright (SIGKILL, so no exit hook runs): it checks every second.
      const watch = [
        'uv run --frozen --project "$2" python "$3" & server=$!',
        'trap \'kill "$server" 2>/dev/null; wait "$server"; exit\' TERM INT',
        'while kill -0 "$1" 2>/dev/null && kill -0 "$server" 2>/dev/null; do sleep 1; done',
        'kill "$server" 2>/dev/null; wait "$server"',
      ].join('\n');
      const child = spawn('sh', ['-c', watch, 'sh', String(process.pid), BACKEND, join(BACKEND, 'scripts/e2e_server.py')], {
        stdio: 'inherit',
        env: {
          ...process.env,
          MEALWRIGHT_DATA_DIR: dataDir,
          MEALWRIGHT_HOST: '127.0.0.1',
          MEALWRIGHT_PORT: String(port),
          MEALWRIGHT_FRONTEND_DIR: FRONTEND_BUILD,
          MEALWRIGHT_ALLOW_PLAIN_HTTP: 'true',
        },
      });
      const ended = new Promise<void>((resolve) => child.once('exit', () => resolve()));
      // If this worker is stopped (Ctrl-C, or Playwright ending it), the server must not outlive it.
      const stopServer = () => child.kill('SIGTERM');
      process.once('exit', stopServer);
      try {
        await waitUntilUp(port, child);
        const api = await request.newContext({ baseURL: local(port) });
        const made = await api.post('/api/v1/setup', { data: ADMIN });
        if (made.status() !== 201) {
          throw new Error(`Couldn't set up the worker's server: ${made.status()} ${await made.text()}`);
        }
        const storageState = await api.storageState();
        await api.dispose();
        await use({ port, url: local(port), insecureUrl: insecure(port), storageState });
      } finally {
        process.off('exit', stopServer);
        if (child.exitCode === null && child.signalCode === null) {
          child.kill('SIGTERM');
          const killer = setTimeout(() => child.kill('SIGKILL'), 5000);
          await ended;
          clearTimeout(killer);
        }
        rmSync(scratch, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
      }
    },
    { scope: 'worker', timeout: 150_000 },
  ],

  // The same server for the test: tests that open a second browser, or the server by another name.
  app: async ({ workerServer }, use) => use(workerServer),

  // The main server's address (the config's default) and the saved sign-in become the worker's.
  // Anything else a test or project sets (the first-run server, no sign-in, the screenshots
  // sign-in) stays as it is.
  baseURL: async ({ baseURL, workerServer }, use) => use(baseURL === local(PORTS.main) ? workerServer.url : baseURL),
  storageState: async ({ storageState, workerServer }, use) =>
    use(storageState === AUTH_FILE ? workerServer.storageState : storageState),

  // Every page in the test's own browser starts on the tests' clock. A browser a test opens
  // itself (browser.newContext) installs it with `context.clock.install({ time: testNow() })`.
  context: async ({ context }, use) => {
    await context.clock.install({ time: testNow() });
    await use(context);
  },
});
