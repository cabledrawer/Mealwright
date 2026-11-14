// Keeps the repo safe to make public (0.9.5, cabledrawer 13 Nov): ./check runs this on every change.
//   node scripts/private-words.mjs --builtin [--root <dir>] [--allow <file>]
//       home-folder paths, drive mounts, Windows drive paths, private IPv4 addresses and fd00::/8
//       addresses, in every tracked file; the tracked allow list names the true examples.
//   node scripts/private-words.mjs --words <list file> [--root <dir>]
//       the words in the git-ignored private list (one word or regex per line; "#" starts a comment
//       line), case-insensitive, in every tracked file's text and in every file name.
// Prints "file:line: kind: what matched" for each hit and exits 1 on any hit (exit 2 for a broken
// list or allow file). The log stays local. Binary files are not read, only their names are checked.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** The patterns that need no private list. A match must also be allowed by nothing in the allow list to count. */
export const BUILTIN = [
  {
    // Linux /home/<name>/ and a Mac's /Users/<name>/, any case.
    kind: "a home-folder path",
    re: /(?<![A-Za-z0-9_.])\/(?:home|users)\/[A-Za-z0-9._][A-Za-z0-9._-]*\//gi,
  },
  { kind: "a drive mount", re: /(?<![A-Za-z0-9_.])\/mnt\/[a-z]\//gi },
  {
    // A drive letter (either case) then a backslash (or two, as written in code) or one slash, then a letter.
    kind: "a Windows drive path",
    re: /(?<![A-Za-z0-9\\])[A-Za-z]:(?:\\{1,2}|\/(?!\/))[A-Za-z]/g,
  },
  {
    // A UNC path (two backslashes, or four as written in code) and a file:// address that names a host.
    kind: "a network share path",
    re: /(?<![\\\w:])(?:\\{2}|\\{4})[A-Za-z][\w.-]*[A-Za-z0-9]\\{1,2}[A-Za-z$][\w$.-]*|file:\/\/(?!\/)[^\s/'"`)]+\//gi,
  },
  {
    kind: "a private IPv4 address",
    re: /(?<![\d.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(?!\d)/g,
  },
  {
    kind: "a private IPv6 address (fd00::/8)",
    re: /(?<![0-9A-Za-z:])fd[0-9a-f]{2}:[0-9a-f:]*/gi,
  },
];

/** The lines of a list file: comments (a line starting with "#") and blank lines dropped. */
export function listLines(text) {
  return text
    .split("\n")
    .map((l) => l.replace(/\r$/, ""))
    .map((l, i) => ({ text: l.trim(), line: i + 1 }))
    .filter((l) => l.text && !l.text.startsWith("#"));
}

/** Each line as a case-insensitive regex; a bad one throws an Error that names its line. */
export function compileList(text, what) {
  return listLines(text).map(({ text: source, line }) => {
    try {
      return new RegExp(source, "gi");
    } catch (error) {
      throw new Error(
        `${what}, line ${line}: not a valid regular expression (${error.message})`,
      );
    }
  });
}

export function trackedFiles(root) {
  return execFileSync("git", ["-C", root, "ls-files", "-z"], {
    encoding: "utf8",
    maxBuffer: 1 << 28,
  })
    .split("\0")
    .filter(Boolean);
}

function looksBinary(buffer) {
  return buffer.subarray(0, 8000).includes(0);
}

/** An allow entry is "regex", or "path glob<TAB>regex" to allow it in the matching files only (* stays in a folder, ** crosses folders). */
export function compileAllow(text, what) {
  return listLines(text).map(({ text: line, line: n }) => {
    const tab = line.indexOf("\t");
    const glob = tab === -1 ? null : line.slice(0, tab).trim();
    const source = tab === -1 ? line : line.slice(tab + 1).trim();
    try {
      const globRe = glob
        ? new RegExp(
            `^${glob
              .split("**")
              .map((part) =>
                part
                  .split("*")
                  .map((x) => x.replace(/[.+?^${}()|[\]\\]/g, "\\$&"))
                  .join("[^/]*"),
              )
              .join(".*")}$`,
          )
        : null;
      return { re: new RegExp(source, "gi"), globRe };
    } catch (error) {
      throw new Error(
        `${what}, line ${n}: not a valid entry (${error.message})`,
      );
    }
  });
}

/** Allow entries must match the whole hit; a hit inside a longer allowed text is not enough. */
function allowed(allow, hit, file) {
  return allow.some(({ re, globRe }) => {
    if (globRe && !globRe.test(file)) return false;
    re.lastIndex = 0;
    const m = re.exec(hit);
    return m !== null && m[0] === hit;
  });
}

/**
 * Scans the tracked files. checks: [{ kind, re }]. allow: regexes a hit must fully match to be excused
 * (built-in checks only). Returns [{ file, line, kind, match }] (line 0 for a file name).
 */
export function scan({
  root,
  files = trackedFiles(root),
  checks,
  allow = [],
  names = false,
}) {
  const hits = [];
  for (const file of files) {
    if (names) {
      for (const { kind, re } of checks) {
        re.lastIndex = 0;
        const m = re.exec(file);
        if (m)
          hits.push({
            file,
            line: 0,
            kind: `${kind} in a file name`,
            match: m[0],
          });
      }
    }
    let buffer;
    try {
      buffer = readFileSync(`${root}/${file}`);
    } catch {
      continue; // a deleted file, a link to nowhere, a folder (a submodule)
    }
    if (looksBinary(buffer)) continue;
    const lines = buffer.toString("utf8").split("\n");
    lines.forEach((text, i) => {
      for (const { kind, re } of checks) {
        for (const m of text.matchAll(re)) {
          if (allowed(allow, m[0], file)) continue;
          hits.push({ file, line: i + 1, kind, match: m[0] });
        }
      }
    });
  }
  return hits;
}

export function formatHit({ file, line, kind, match }) {
  return `${file}${line ? `:${line}` : ""}: ${kind}: ${match.length > 80 ? `${match.slice(0, 80)}…` : match}`;
}

function option(args, name) {
  const i = args.indexOf(name);
  return i === -1 ? "" : (args[i + 1] ?? "");
}

function main(args) {
  const root =
    option(args, "--root") ||
    fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
  let hits;
  if (args.includes("--builtin")) {
    const allowFile =
      option(args, "--allow") || `${root}/scripts/public-safe-allow.txt`;
    const allow = existsSync(allowFile)
      ? compileAllow(readFileSync(allowFile, "utf8"), allowFile)
      : [];
    hits = scan({ root, checks: BUILTIN, allow });
  } else if (args.includes("--words")) {
    const listFile = option(args, "--words");
    if (!listFile || !existsSync(listFile)) {
      console.log("no private word list here");
      return 0;
    }
    const words = compileList(
      readFileSync(listFile, "utf8"),
      "the private word list",
    );
    hits = scan({
      root,
      checks: words.map((re) => ({ kind: "a private word", re })),
      names: true,
    });
  } else {
    console.error(
      "Usage: private-words.mjs --builtin [--allow <file>] | --words <list file> [--root <dir>]",
    );
    return 2;
  }
  for (const hit of hits) console.log(formatHit(hit));
  if (hits.length)
    console.log(
      `${hits.length} private ${hits.length === 1 ? "thing" : "things"} in tracked files`,
    );
  return hits.length ? 1 : 0;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 2;
  }
}
