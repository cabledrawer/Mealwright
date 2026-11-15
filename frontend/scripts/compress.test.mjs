// Tests for compress.mjs, on a small fake build folder made in a temporary folder.
//
//   cd frontend && node --test scripts/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliDecompressSync, gunzipSync } from 'node:zlib';

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'compress.mjs');
const code = 'export const answer = () => "forty-two and then some more words";\n'.repeat(100);

function build() {
  const root = mkdtempSync(join(tmpdir(), 'mw-compress-'));
  mkdirSync(join(root, '_app', 'immutable'), { recursive: true });
  writeFileSync(join(root, '_app', 'immutable', 'app.js'), code);
  writeFileSync(join(root, 'index.html'), `<!doctype html>${'<p>hello</p>'.repeat(200)}`);
  writeFileSync(join(root, 'tiny.js'), 'x=1');
  writeFileSync(join(root, 'font.woff2'), Buffer.from(code));
  writeFileSync(join(root, 'photo.png'), Buffer.from(code));
  return root;
}

const run = (root) => spawnSync('node', [SCRIPT, root], { encoding: 'utf8' });

test('text files get a .br and a .gz that unpack to the same bytes', () => {
  const root = build();
  assert.equal(run(root).status, 0);
  const file = join(root, '_app', 'immutable', 'app.js');
  assert.equal(brotliDecompressSync(readFileSync(`${file}.br`)).toString(), code);
  assert.equal(gunzipSync(readFileSync(`${file}.gz`)).toString(), code);
  assert.ok(existsSync(join(root, 'index.html.br')) && existsSync(join(root, 'index.html.gz')));
  rmSync(root, { recursive: true });
});

test('fonts, pictures and tiny files are left alone', () => {
  const root = build();
  run(root);
  for (const name of ['font.woff2', 'photo.png', 'tiny.js']) {
    assert.equal(existsSync(join(root, `${name}.br`)), false, name);
    assert.equal(existsSync(join(root, `${name}.gz`)), false, name);
  }
  rmSync(root, { recursive: true });
});

test('a second run leaves no stale copy of a file that has since become too small to bother with', () => {
  const root = build();
  run(root);
  writeFileSync(join(root, 'index.html'), '<p>x</p>');
  run(root);
  assert.equal(existsSync(join(root, 'index.html.br')), false);
  assert.equal(existsSync(join(root, 'index.html.gz')), false);
  rmSync(root, { recursive: true });
});

test('it stops when there is no build', () => {
  const result = run(join(tmpdir(), 'mw-no-such-build'));
  assert.notEqual(result.status, 0);
});
