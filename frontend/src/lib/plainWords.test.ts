import { describe, expect, it } from 'vitest';

// Plain words (UX principle 7; cabledrawer 17 Oct): on screen it's always "ingredient",
// never "food". "Food" stays the word in code and the data model. This scans every
// string a person could see in the web app: text in the markup, the aria-label, title,
// placeholder and alt attributes (and props passed as text), and every string in the
// code with a space in it (sentences such as toasts and labels; identifiers and API
// paths have no spaces). Comments are left out. Sentences from the server aren't here:
// the server words those itself.

const sources = import.meta.glob(['/src/**/*.svelte', '/src/**/*.ts'], {
  query: '?raw',
  import: 'default',
  eager: true
}) as Record<string, string>;

/** Files that aren't the app itself. */
const SKIP = [/\.test\.ts$/, /^\/src\/lib\/testing\//];

/** Strings that mention "food" on purpose and never reach the screen. */
const ALLOWED = new Set<string>([]);

const FOOD = /\bfoods?\b/i;

/** A straight apostrophe inside a word ("can't", "X's" where X stands for a ${…}). */
const STRAIGHT = /[A-Za-z]'[A-Za-z]/;

function withoutComments(code: string): string {
  return code
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"`])\/\/.*$/gm, '$1');
}

/**
 * The string literals in some code. Template strings come back as their text (each
 * ${…} as the placeholder word "X") plus the code inside each ${…}, scanned in turn.
 */
function literals(code: string): { text: string; inner: string[] }[] {
  const out: { text: string; inner: string[] }[] = [];
  let i = 0;
  while (i < code.length) {
    const quote = code[i]!;
    if (quote === "'" || quote === '"') {
      let text = '';
      i++;
      while (i < code.length && code[i] !== quote && code[i] !== '\n') {
        if (code[i] === '\\') i++;
        text += code[i++];
      }
      i++;
      out.push({ text, inner: [] });
    } else if (quote === '`') {
      let text = '';
      const inner: string[] = [];
      i++;
      while (i < code.length && code[i] !== '`') {
        if (code[i] === '\\') {
          text += code[i + 1];
          i += 2;
        } else if (code[i] === '$' && code[i + 1] === '{') {
          // Read to the matching }, stepping over strings inside (they may hold braces).
          let depth = 1;
          let part = '';
          i += 2;
          while (i < code.length && depth > 0) {
            const ch = code[i]!;
            if (ch === "'" || ch === '"' || ch === '`') {
              const start = i;
              const close = ch;
              i++;
              let nest = 0;
              while (i < code.length && (code[i] !== close || nest > 0)) {
                if (close === '`' && code[i] === '$' && code[i + 1] === '{') nest++;
                else if (close === '`' && code[i] === '}' && nest > 0) nest--;
                if (code[i] === '\\') i++;
                i++;
              }
              i++;
              part += code.slice(start, i);
              continue;
            }
            if (ch === '{') depth++;
            if (ch === '}') depth--;
            if (depth > 0) part += ch;
            i++;
          }
          inner.push(part);
          text += 'X';
        } else text += code[i++];
      }
      i++;
      out.push({ text, inner });
    } else i++;
  }
  return out;
}

/** Human-looking strings in code: with a space, or just the word "food(s)". */
function sentences(code: string): string[] {
  const found: string[] = [];
  for (const { text, inner } of literals(code)) {
    for (const part of inner) found.push(...sentences(part));
    const words = text.trim();
    // API paths ("/foods/…") are addresses, not words.
    if (words.startsWith('/')) continue;
    // A one-word string that is just "food(s)" is a word on screen too ("2 foods").
    if (/\s/.test(words) || /^foods?$/i.test(words)) found.push(words);
  }
  return found;
}

/** Split Svelte markup into its {expressions} (braces balanced) and the rest. */
function expressions(markup: string): { rest: string; inside: string[] } {
  let rest = '';
  const inside: string[] = [];
  let depth = 0;
  let current = '';
  for (const ch of markup) {
    if (ch === '{') {
      if (depth > 0) current += ch;
      depth++;
    } else if (ch === '}' && depth > 0) {
      depth--;
      if (depth === 0) {
        inside.push(current);
        current = '';
        rest += ' ';
      } else current += ch;
    } else if (depth > 0) current += ch;
    else rest += ch;
  }
  return { rest, inside };
}

/** Text a person sees in Svelte markup. */
function markupText(markup: string): string[] {
  const found: string[] = [];
  const { rest, inside } = expressions(markup);
  // Attributes read out or shown.
  const attr =
    /\b(aria-label|aria-description|title|placeholder|alt|label|subtitle|overline|message)="([^"]*)"/g;
  for (const match of rest.matchAll(attr)) found.push(match[2]!);
  // Text between tags.
  const text = rest.replace(/<[^>]*>/g, '\n');
  for (const line of text.split('\n')) if (line.trim()) found.push(line.trim());
  // Strings inside {expressions}.
  for (const expression of inside) found.push(...sentences(expression));
  return found;
}

function visibleStrings(path: string, source: string): string[] {
  const code = withoutComments(source);
  if (!path.endsWith('.svelte')) return sentences(code);
  const scripts = [...code.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]!);
  const markup = code
    .replace(/<script[^>]*>[\s\S]*?<\/script>/g, ' ')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/g, ' ');
  return [...scripts.flatMap(sentences), ...markupText(markup)];
}

describe('plain words', () => {
  it('finds the app’s files', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  it('says "ingredient", never "food", on screen', () => {
    const problems: string[] = [];
    for (const [path, source] of Object.entries(sources)) {
      if (SKIP.some((skip) => skip.test(path))) continue;
      for (const text of visibleStrings(path, source)) {
        if (FOOD.test(text) && !ALLOWED.has(text)) problems.push(`${path}: “${text}”`);
      }
    }
    expect(problems, problems.join('\n')).toEqual([]);
  });

  // Curly apostrophes on screen (word list section 11, ruling 3): "Couldn’t", "You’re".
  it('uses curly apostrophes on screen, never a straight one', () => {
    const problems: string[] = [];
    for (const [path, source] of Object.entries(sources)) {
      if (SKIP.some((skip) => skip.test(path))) continue;
      for (const text of visibleStrings(path, source)) {
        if (STRAIGHT.test(text)) problems.push(`${path}: “${text}”`);
      }
    }
    expect(problems, problems.join('\n')).toEqual([]);
  });

  it('the apostrophe check catches a straight one in markup, attributes and code', () => {
    const svelte = (body: string) => visibleStrings('/x.svelte', body);
    const found = (texts: string[]) => texts.some((text) => STRAIGHT.test(text));
    expect(found(svelte("<p>You're offline.</p>"))).toBe(true);
    expect(found(svelte('<input placeholder="What\'s left" />'))).toBe(true);
    expect(found(visibleStrings('/x.ts', 'const a = "Can\'t reach it";'))).toBe(true);
    expect(found(visibleStrings('/x.ts', "const a = `${name}'s list`;"))).toBe(true);
    expect(found(svelte('<p>You’re offline.</p>'))).toBe(false);
    // Comments aren't on screen.
    expect(found(visibleStrings('/x.ts', "// it's a comment\nconst a = 1;"))).toBe(false);
  });
});
