// Starts everything the browser tests need: builds the web app (unless E2E_SKIP_BUILD=1), then runs four
// Mealwright servers on 127.0.0.1, each with its own empty data folder (see
// tests/servers.ts). The backend works out the CSP hashes of the built page at start-up,
// so it starts after the build. Stops them all when Playwright stops this script.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const base = Number(process.env.E2E_APP_PORT ?? 18080);
const servers = [
  { name: 'fresh', port: base + 1, plainHttp: true },
  { name: 'strict', port: base + 2, plainHttp: false },
  { name: 'shots', port: base + 3, plainHttp: true },
  { name: 'main', port: base, plainHttp: true }, // last: Playwright waits for this one
];

// With E2E_SKIP_BUILD=1 the web app already built in ../frontend/build is used as it is:
// ./check builds it once (its size-limit step) and runs two sets of servers on that one build,
// because two builds into the same folder at once would spoil it.
if (process.env.E2E_SKIP_BUILD === '1') {
  if (!existsSync('../frontend/build/index.html')) {
    console.error('E2E_SKIP_BUILD=1, but there is no built web app in ../frontend/build.');
    process.exit(1);
  }
} else {
  const build = spawnSync('npm', ['--prefix', '../frontend', 'run', '-s', 'build'], {
    stdio: 'inherit',
  });
  if (build.status !== 0) process.exit(build.status ?? 1);
}

// With E2E_CLOCK_SHIFT_MS (the browser tests, playwright.config.ts) each server's clock is moved
// to the tests' fixed date and time by a test-only launcher that isn't in the app or the image
// (backend/scripts/e2e_server.py). Without it (review/screens.ts) they run on the real time.
const start = process.env.E2E_CLOCK_SHIFT_MS
  ? ['../backend/scripts/e2e_server.py']
  : ['-m', 'mealwright'];

// One throwaway folder for the whole run, with a data folder per server inside it. It is
// removed when the servers have stopped, so a run never leaves its data behind in /tmp
// (cabledrawer 22 Oct). playwright.config.ts asks Playwright to stop this script with SIGTERM and
// wait, because Playwright's default is to kill it outright, which skips this clean-up.
const scratch = mkdtempSync(join(tmpdir(), 'mealwright-e2e-'));

const children = [];
let stopping = false;
/** Stop every server, wait for them to end, remove the scratch folder, then exit. */
function shutdown(code) {
  if (stopping) return;
  stopping = true;
  const ended = children.map(
    (child) =>
      new Promise((resolve) => {
        if (child.exitCode !== null || child.signalCode !== null) return resolve();
        child.once('exit', resolve);
        child.kill('SIGTERM');
      }),
  );
  // A server that won't stop is killed after a few seconds, so the clean-up still happens.
  const killer = setTimeout(() => {
    for (const child of children) child.kill('SIGKILL');
  }, 5000);
  Promise.all(ended).then(() => {
    clearTimeout(killer);
    rmSync(scratch, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    process.exit(code);
  });
}
process.on('SIGTERM', () => shutdown(0));
process.on('SIGINT', () => shutdown(0));

async function ready(port) {
  for (let i = 0; i < 600; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${port}/api/v1/version`)).ok) return;
    } catch {
      // not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`server on port ${port} didn't start`);
}

for (const { name, port, plainHttp } of servers) {
  if (stopping) break; // stopped while the others were still starting
  const dataDir = join(scratch, name);
  mkdirSync(dataDir);
  const child = spawn('uv', ['run', '--frozen', '--project', '../backend', 'python', ...start], {
    stdio: 'inherit',
    env: {
      ...process.env,
      MEALWRIGHT_DATA_DIR: dataDir,
      MEALWRIGHT_HOST: '127.0.0.1',
      MEALWRIGHT_PORT: String(port),
      MEALWRIGHT_FRONTEND_DIR: '../frontend/build',
      MEALWRIGHT_ALLOW_PLAIN_HTTP: String(plainHttp),
    },
  });
  child.on('exit', (code) => {
    if (stopping) return;
    console.error(`Mealwright server "${name}" stopped (${code}).`);
    shutdown(1);
  });
  children.push(child);
  await ready(port);
}
