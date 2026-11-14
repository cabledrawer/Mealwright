// The "repo: private words" and "repo: home paths and addresses" steps of ./check (0.9.5). Every
// private-looking value below is made up (example users, example networks, example words).
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url)).replace(
  /\/$/,
  "",
);
const script = `${root}/e2e/scripts/private-words.mjs`;
const check = readFileSync(`${root}/check`, "utf8");
const made = [];
// Written in pieces so that this file itself holds no such value for the step to find.
const HOME = "/ho" + "me/jo/";
const MNT = "/mn" + "t/x/";
const DRIVE = "D:" + "\\\\Stuff";
const LAN = "192.168" + ".7.7";
const TEN = "10.20" + ".30.40";
const ULA = "fd12" + ":99::1";
const EX = "192.168" + ".1.20";
const EX2 = "192.168" + ".1.200";

/** A throwaway git repo holding these files (all added to the index): its folder. */
function repo(files) {
  const dir = mkdtempSync(
    `${process.env.TMPDIR || tmpdir()}/mw-private-words-`,
  );
  made.push(dir);
  execFileSync("git", ["-C", dir, "init", "-q"]);
  for (const [name, content] of Object.entries(files)) {
    mkdirSync(dirname(`${dir}/${name}`), { recursive: true });
    writeFileSync(`${dir}/${name}`, content);
  }
  execFileSync("git", ["-C", dir, "add", "-A"]);
  return dir;
}
after(() => made.forEach((d) => rmSync(d, { recursive: true, force: true })));

function run(args) {
  const r = spawnSync("node", [script, ...args], { encoding: "utf8" });
  return { code: r.status, out: r.stdout, err: r.stderr };
}

test("a home-folder path, a drive mount, a Windows path and a private address each fail, with file:line", () => {
  const dir = repo({
    "notes.md": `fine\nsee ${HOME}project/x\n`,
    "a/b.txt": `copy from ${MNT}Stuff\nand ${DRIVE}\\here\n`,
    "net.py": `HOST = "${LAN}"\nOTHER = "${TEN}"\nV6 = "${ULA}"\n`,
  });
  const { code, out } = run([
    "--builtin",
    "--root",
    dir,
    "--allow",
    `${dir}/none.txt`,
  ]);
  assert.equal(code, 1);
  for (const want of [
    "notes.md:2: a home-folder path",
    "a/b.txt:1: a drive mount",
    "a/b.txt:2: a Windows drive path",
    "net.py:1: a private IPv4 address",
    "net.py:2: a private IPv4 address",
    "net.py:3: a private IPv6 address",
  ]) {
    assert.ok(out.includes(want), `missing "${want}" in:\n${out}`);
  }
});

test("documentation ranges, public addresses and version numbers are fine; an allow entry must match the whole hit", () => {
  const dir = repo({
    "ok.md":
      "a 192.0.2.5 b 198.51.100.7 c 203.0.113.9 d 8.8.8.8 e 10.0.0 f version 172.5.1\nTime 12:30 and \\d\\d:\\d\\d\n",
    "ex.md": `the example ${EX} is allowed, ${EX2} is not\n`,
  });
  writeFileSync(
    `${dir}/allow.txt`,
    `# a comment\n\n${EX.replaceAll(".", "\\.")}\n`,
  );
  const { code, out } = run([
    "--builtin",
    "--root",
    dir,
    "--allow",
    `${dir}/allow.txt`,
  ]);
  assert.equal(code, 1);
  assert.ok(!out.includes("ok.md"), out);
  assert.ok(out.includes(`ex.md:1: a private IPv4 address: ${EX2}`), out);
  assert.ok(!out.includes(`address: ${EX}\n`), out);
});

test("a word on the private list fails, case-insensitively, with file:line; comments and blank lines are ignored", () => {
  const dir = repo({ "doc.md": "one\nThe box is named Quux-Server here\n" });
  writeFileSync(`${dir}.list`, "# comment\n\nquux-server\n");
  made.push(`${dir}.list`);
  const { code, out } = run(["--words", `${dir}.list`, "--root", dir]);
  assert.equal(code, 1);
  assert.ok(out.includes("doc.md:2: a private word: Quux-Server"), out);
});

test("a file NAME that holds a private word fails", () => {
  const dir = repo({
    "shots/quux-server-home.png": "x",
    "clean.md": "nothing",
  });
  writeFileSync(`${dir}.list`, "quux-server\n");
  made.push(`${dir}.list`);
  const { code, out } = run(["--words", `${dir}.list`, "--root", dir]);
  assert.equal(code, 1);
  assert.ok(
    out.includes("shots/quux-server-home.png: a private word in a file name"),
    out,
  );
});

test("no list: the step says so and does not fail; ./check records it as skipped", () => {
  const dir = repo({ "doc.md": "quux-server" });
  const { code, out } = run([
    "--words",
    `${dir}/does-not-exist`,
    "--root",
    dir,
  ]);
  assert.equal(code, 0);
  assert.match(out, /no private word list here/);
  assert.ok(
    check.includes('skip "repo: private words" "no private word list here"'),
  );
  assert.ok(
    check.includes(
      'step "repo: private words" node e2e/scripts/private-words.mjs --words "$words"',
    ),
  );
  assert.ok(
    check.includes(
      'step "repo: home paths and addresses" node e2e/scripts/private-words.mjs --builtin',
    ),
  );
});

test("both steps run in the fast run too: they come before the fast run's skips", () => {
  const at = (s) => check.indexOf(s);
  assert.ok(at("public_safe_steps\nif ((FAST)); then") > 0);
  assert.ok(at("extra_steps() {") > at("public_safe_steps() {"));
});

test("binary files do not crash it, and their names are still checked", () => {
  const dir = repo({ "pic.bin": `abc\0 ${HOME}x \0def`, "ok.txt": "fine" });
  writeFileSync(`${dir}.list`, "pic\\.bin\n");
  made.push(`${dir}.list`);
  assert.equal(
    run(["--builtin", "--root", dir, "--allow", `${dir}/none`]).code,
    0,
  );
  const { code, out } = run(["--words", `${dir}.list`, "--root", dir]);
  assert.equal(code, 1);
  assert.ok(out.includes("pic.bin: a private word in a file name"), out);
});

test("a broken list line is an error (exit 2) that names the line, never a pass", () => {
  const dir = repo({ "doc.md": "x" });
  writeFileSync(`${dir}.list`, "fine\n(unclosed\n");
  made.push(`${dir}.list`);
  const { code, err } = run(["--words", `${dir}.list`, "--root", dir]);
  assert.equal(code, 2);
  assert.match(err, /line 2: not a valid regular expression/);
});

test("the tracked example word list holds made-up words only", () => {
  const example = readFileSync(`${root}/.private-words.example`, "utf8");
  const words = example
    .split("\n")
    .filter((l) => l.trim() && !l.startsWith("#"));
  assert.ok(words.length > 0);
  // No tracked file of this repo holds an example word, and no example word is a built-in hit.
  assert.equal(
    run(["--words", `${root}/.private-words.example`, "--root", root]).code,
    0,
  );
  assert.ok(example.includes("made up"));
  const notes = readFileSync(`${root}/CLAUDE.local.md.example`, "utf8");
  assert.ok(notes.includes("The values below are made up."));
});

test("this repo has no home-folder path, drive path or private address outside its allow list", () => {
  const { code, out } = run(["--builtin", "--root", root]);
  assert.equal(code, 0, out);
});

test("the private files are git-ignored and not tracked", () => {
  for (const f of ["CLAUDE.local.md", ".private-words"]) {
    const ignored = spawnSync("git", ["-C", root, "check-ignore", "-q", f]);
    assert.equal(ignored.status, 0, `${f} is not git-ignored`);
    const tracked = execFileSync("git", ["-C", root, "ls-files", f], {
      encoding: "utf8",
    });
    assert.equal(tracked, "");
  }
});
