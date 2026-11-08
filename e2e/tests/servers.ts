// The three Mealwright servers the browser tests use (started by serve.mjs).
//   main:   set up (admin "tess"), plain http:// allowed, as most tests need.
//   fresh:  never set up, for the first-run setup test.
//   strict: plain http:// not allowed, as in a real install behind HTTPS.
//   shots:  its own kitchen with fixed test data, for the saved screenshots (tests/screens.spec.ts),
//           so no other test can change what the screenshots show.
// mealwright.test is a made-up name (.test never resolves on the internet). The
// browser maps it to 127.0.0.1, so a page there is "plain http://, not localhost".

const base = Number(process.env.E2E_APP_PORT ?? 18080);

export const PORTS = { main: base, fresh: base + 1, strict: base + 2, shots: base + 3 };

export const local = (port: number) => `http://127.0.0.1:${port}`;
export const insecure = (port: number) => `http://mealwright.test:${port}`;

export const ADMIN = { name: 'Tess', username: 'tess', password: 'kitchen-secret-2026' };

// Saved sign-ins, one pair per port base: ./check runs three sets of servers at once (desktop, phone
// and WebKit), and a cookie doesn't tell ports apart, so each run keeps its own.
export const AUTH_FILE = `.auth/tess-${base}.json`;
export const SHOTS_AUTH_FILE = `.auth/shots-${base}.json`;
