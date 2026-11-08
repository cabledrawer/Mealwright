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

test('a full check runs the backend tests first, on their own, unless CHECK_PYTEST_FIRST=0 (cabledrawer 8 Nov)', () => {
  const uses = checkScript.match(/CHECK_PYTEST_FIRST:-\d/g) ?? [];
  assert.ok(uses.length >= 2, 'CHECK_PYTEST_FIRST is read in the backend step');
  assert.deepEqual([...new Set(uses)], ['CHECK_PYTEST_FIRST:-1']);
});

// branch_name: a detached copy (the frozen copy) names the branch whose tip it is, not "?".
const branchFn = checkScript.match(/^branch_name\(\) \{\n[\s\S]*?^\}\n/m)?.[0];
test('branch_name names the branch in a detached copy, and "(detached)" when no branch is there', () => {
  assert.ok(branchFn, 'branch_name is in ./check');
  const r = spawnSync('bash', ['-c', `set -e
d="$(mktemp -d)"; trap 'rm -rf "$d"' EXIT
git -C "$d" init -q -b work; git -C "$d" -c user.name=t -c user.email=t@t commit -q --allow-empty -m one
ROOT="$d"
${branchFn}
echo "on:$(branch_name)"
git -C "$d" checkout -q --detach
echo "tip:$(branch_name)"
git -C "$d" -c user.name=t -c user.email=t@t commit -q --allow-empty -m two
echo "none:$(branch_name)"`], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(r.stdout.trim().split('\n'), ['on:work', 'tip:work', 'none:(detached)']);
});
