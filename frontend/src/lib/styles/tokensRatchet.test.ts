import { describe, expect, it } from 'vitest';

// FE27: sizes and corners come from the tokens (they follow the browser's text size). Literal
// px values that have no token yet stay, but the count may only go down: lower the limits when
// you convert more, never raise them.
const files = import.meta.glob(['/src/**/*.svelte', '/src/lib/styles/*.css'], {
  query: '?raw',
  import: 'default',
  eager: true
}) as Record<string, string>;

function count(pattern: RegExp): number {
  let total = 0;
  for (const [path, text] of Object.entries(files)) {
    if (path.endsWith('/tokens.css')) continue;
    total += text.match(pattern)?.length ?? 0;
  }
  return total;
}

describe('literal sizes in styles (FE27)', () => {
  it('font sizes in px that have a token stay converted', () => {
    expect(count(/font-size: *(?:11|12|13|14|15|17|18|20)px/g)).toBe(0);
  });
  it('corner radii in px that have a token stay converted', () => {
    expect(count(/border[\w-]*radius: *(?:9|12|14|16|18|20|22|24|28|999)px *;/g)).toBe(0);
  });
  it('every focus ring uses the one width', () => {
    expect(count(/outline: *[2-9]px solid var\(--color-(?:accent|focus)\)/g)).toBe(0);
  });
});
