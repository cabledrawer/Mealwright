// ./check's worker counts per browser stream (stream_workers), run in bash with the function taken
// from ./check itself (node --test). Defaults: desktop 3, phone 2, WebKit 2 (cabledrawer 8 Nov, T2c).
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const checkScript = readFileSync(fileURLToPath(new URL('../../check', import.meta.url)), 'utf8');
const fn = checkScript.match(/^stream_workers\(\) \{\n[\s\S]*?^\}\n/m)?.[0];

function workers(env, label) {
  assert.ok(fn, 'stream_workers is in ./check');
  const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('CHECK_WORKERS_')));
  const r = spawnSync('bash', ['-c', `${fn}\nstream_workers ${label}`], { encoding: 'utf8', env: { ...clean, ...env } });
  return { status: r.status, out: r.stdout.trim(), err: r.stderr.trim() };
}

test('the default workers are desktop 3, phone 2, WebKit 2, and 2 when phone and WebKit share a stream', () => {
  assert.deepEqual(
    ['desktop', 'phone', 'webkit', 'phone+webkit'].map((l) => workers({}, l).out),
    ['3', '2', '2', '2'],
  );
});

test('CHECK_WORKERS_* changes a stream, and a count outside 1 to 6 is refused', () => {
  assert.equal(workers({ CHECK_WORKERS_DESKTOP: '5' }, 'desktop').out, '5');
  const bad = workers({ CHECK_WORKERS_PHONE: '7' }, 'phone');
  assert.equal(bad.status, 2);
  assert.match(bad.err, /1 to 6/);
});
