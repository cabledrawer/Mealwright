// The three Mealwright servers the browser tests use (started by serve.mjs).
//   main:   only what Playwright waits for at start-up; no browser test uses it (e2e/review/screens.ts --serve
//           does: it starts serve.mjs and signs in on this port). Kept for that. Each worker starts its own
//           server instead (tests/clock.ts), set up with the admin "tess", plain http:// allowed.
//   fresh:  never set up, for the first-run setup test.
//   strict: plain http:// not allowed, as in a real install behind HTTPS.
//   shots:  its own kitchen with fixed test data, for the saved screenshots (tests/screens.spec.ts),
//           so no other test can change what the screenshots show.
// mealwright.test is a made-up name (.test never resolves on the internet). The
// browser maps it to 127.0.0.1, so a page there is "plain http://, not localhost".

const base = Number(process.env.E2E_APP_PORT ?? 18080);

export const PORTS = { main: base, fresh: base + 1, strict: base + 2, shots: base + 3 };

/** The port of a worker's own server (tests/clock.ts): after the four above, one per worker
 *  (parallelIndex), so a stream's ports are base .. base + 9 at most (E2E_WORKERS up to 6). */
export const WORKER_PORT_FIRST = base + 4;
export const MAX_WORKERS = 6;

export const local = (port: number) => `http://127.0.0.1:${port}`;
export const insecure = (port: number) => `http://mealwright.test:${port}`;

/** The first-run setup code every test server uses (E2E_SETUP_CODE; a real install makes a new
 *  random one at each start and prints it in its log: backend/src/mealwright/setup_code.py). */
export const SETUP_CODE = 'TEST-SETU-PCDE';

export const ADMIN = {
  name: 'Tess',
  username: 'tess',
  password: 'kitchen-secret-2026',
  setup_code: SETUP_CODE,
};

// What playwright.config.ts gives every project that starts signed in (it is a file name only to
// be told apart: tests/clock.ts swaps it for the worker's own sign-in). The shots sign-in is a
// real file, saved by global-setup.ts: one pair per port base, because ./check runs three sets of
// servers at once (desktop, phone and WebKit) and a cookie doesn't tell ports apart.
export const AUTH_FILE = `.auth/tess-${base}.json`;
export const SHOTS_AUTH_FILE = `.auth/shots-${base}.json`;
