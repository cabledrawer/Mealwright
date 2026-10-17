// Starts everything the browser tests need: builds the web app, then runs three
// Mealwright servers on 127.0.0.1, each with its own empty data folder (see
// tests/servers.ts). The backend works out the CSP hashes of the built page at start-up,
// so it starts after the build. Stops them all when Playwright stops this script.
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const base = Number(process.env.E2E_APP_PORT ?? 18080);
const servers = [
  { name: 'fresh', port: base + 1, plainHttp: true },
  { name: 'strict', port: base + 2, plainHttp: false },
  { name: 'main', port: base, plainHttp: true }, // last: Playwright waits for this one
];

const build = spawnSync('npm', ['--prefix', '../frontend', 'run', '-s', 'build'], {
  stdio: 'inherit',
});
if (build.status !== 0) process.exit(build.status ?? 1);

const children = [];
const stop = () => {
  for (const child of children) child.kill('SIGTERM');
};
process.on('SIGTERM', () => {
  stop();
  process.exit(0);
});
process.on('SIGINT', () => {
  stop();
  process.exit(0);
});

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
  const child = spawn('uv', ['run', '--frozen', '--project', '../backend', 'python', '-m', 'mealwright'], {
    stdio: 'inherit',
    env: {
      ...process.env,
      MEALWRIGHT_DATA_DIR: mkdtempSync(join(tmpdir(), `mealwright-e2e-${name}-`)),
      MEALWRIGHT_HOST: '127.0.0.1',
      MEALWRIGHT_PORT: String(port),
      MEALWRIGHT_FRONTEND_DIR: '../frontend/build',
      MEALWRIGHT_ALLOW_PLAIN_HTTP: String(plainHttp),
    },
  });
  child.on('exit', (code) => {
    console.error(`Mealwright server "${name}" stopped (${code}).`);
    stop();
    process.exit(1);
  });
  children.push(child);
  await ready(port);
}
