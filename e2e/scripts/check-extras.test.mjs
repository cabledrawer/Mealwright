// The Dockerfile, compose, shell script and image smoke steps of ./check (0.9.5; cabledrawer 13 Nov, Q5:
// hadolint and shellcheck "in the check image only, never shipped"). These tests hold what can be held
// without Docker: the linters are pinned by digest, the shipped Dockerfile does not mention them, the
// lists of files each step covers hold every such file in the repo, and the smoke script uses its own
// name and port and always cleans up.
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url)).replace(/\/$/, '');
const check = readFileSync(`${root}/check`, 'utf8');
const tracked = execFileSync('git', ['-C', root, 'ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean);

/** A function of ./check run on its own, with ROOT set: its lines, in order. */
function listed(name) {
  const start = check.indexOf('repo_files() {');
  const end = check.indexOf('hadolint_run() {');
  const run = spawnSync('bash', ['-c', `${check.slice(start, end)}\n${name}`], {
    env: { ...process.env, ROOT: root },
    encoding: 'utf8'
  });
  assert.equal(run.status, 0, run.stderr);
  return run.stdout.split('\n').filter(Boolean).sort();
}

test('hadolint and shellcheck are pinned by digest and named in ./check only', () => {
  for (const name of ['HADOLINT', 'SHELLCHECK']) {
    assert.match(check, new RegExp(`^${name}="[a-z/]+@sha256:[0-9a-f]{64}"`, 'm'), `${name} is not pinned by digest`);
  }
});

test('the shipped Dockerfile holds neither linter, and ./check looks inside the built image for them', () => {
  const dockerfile = readFileSync(`${root}/Dockerfile`, 'utf8');
  assert.doesNotMatch(dockerfile, /hadolint|shellcheck/i);
  assert.ok(check.includes('step "image: no lint tools"  no_lint_tools_in_image'));
  assert.match(check, /for tool in hadolint shellcheck; do/);
});

test('every shell script in the repo is checked, found by its extension or its first line', () => {
  const executable = execFileSync('git', ['-C', root, 'ls-files', '-s'], { encoding: 'utf8' })
    .split('\n')
    .filter((line) => line.startsWith('100755'))
    .map((line) => line.split('\t')[1]);
  const wanted = tracked.filter((f) => {
    if (f.endsWith('.sh')) return true;
    if (!executable.includes(f)) return false;
    const first = readFileSync(`${root}/${f}`, 'utf8').slice(0, 80).split('\n')[0];
    return /^#!.*[/ ](ba|da|k)?sh( |$)/.test(first);
  });
  const got = listed('shell_scripts');
  for (const f of wanted) assert.ok(got.includes(f), `${f} is a shell script that ./check does not shellcheck`);
  assert.ok(got.includes('check') && got.includes('scripts/smoke-image.sh'));
});

test('every compose example and Dockerfile is covered', () => {
  const compose = tracked.filter((f) => /(^|\/)(docker-)?compose[^/]*\.ya?ml$/.test(f));
  assert.ok(compose.length > 0);
  assert.deepEqual(listed('compose_files'), compose.sort());
  const dockerfiles = tracked.filter((f) => /(^|\/)(Dockerfile[^/]*|[^/]*\.Dockerfile)$/.test(f));
  assert.deepEqual(listed('dockerfiles'), dockerfiles.sort());
});

test('the smoke run has its own container name and port, and always removes what it made', () => {
  const smoke = readFileSync(`${root}/scripts/smoke-image.sh`, 'utf8');
  assert.match(smoke, /^NAME="mealwright-smoke-\$SUFFIX"/m);
  assert.match(smoke, /^SUFFIX="\$\$-\$RANDOM"/m);
  assert.ok(smoke.includes('-p 127.0.0.1::8080'), 'the host port must be picked by Docker, on loopback');
  assert.doesNotMatch(smoke, /-p [0-9]+:/);
  assert.match(smoke, /^trap cleanup EXIT$/m);
  assert.match(smoke, /docker rm -f "\$NAME"/);
  assert.match(smoke, /docker volume rm "\$VOLUME"/);
  assert.ok(check.includes('step "image: smoke run"      scripts/smoke-image.sh "$IMAGE"'));
});
