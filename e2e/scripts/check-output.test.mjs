// ./check writes the screen to fd 3 (`exec 3>&1`). A failing step's last lines are copied there
// with tee; when the screen is redirected to a file, a plain `tee /dev/fd/3` re-opens that file at
// its start and overwrites the first lines (the run's header and its DIAGNOSIS RUN line).
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const checkScript = readFileSync(fileURLToPath(new URL('../../check', import.meta.url)), 'utf8');

function screenFile(tee) {
  const dir = mkdtempSync(join(tmpdir(), 'mealwright-fd3-'));
  try {
    const out = join(dir, 'screen.txt');
    const script = `exec 3>${JSON.stringify(out)}; echo "first line" >&3; echo "second line" >&3; echo "copied" | ${tee} >/dev/null`;
    const r = spawnSync('bash', ['-c', script], { encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    return readFileSync(out, 'utf8');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test('every tee to the screen in ./check appends (tee -a /dev/fd/3)', () => {
  const tees = checkScript.match(/\btee\b[^\n|]*\/dev\/fd\/3/g) ?? [];
  assert.ok(tees.length > 0, './check copies lines to the screen with tee');
  for (const t of tees) assert.match(t, /^tee -a \/dev\/fd\/3$/, `"${t}" must append, or it overwrites the screen file's start`);
});

test('with the screen redirected to a file, tee -a keeps the first lines', () => {
  assert.equal(screenFile('tee -a /dev/fd/3'), 'first line\nsecond line\ncopied\n');
  // Why: the plain form starts writing at the file's start.
  assert.notEqual(screenFile('tee /dev/fd/3'), 'first line\nsecond line\ncopied\n');
});
