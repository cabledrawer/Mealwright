import { describe, expect, it } from 'vitest';

// FE2: a screen's code that is fetched when first wanted goes through <Lazy> (or LazyCode /
// fetchCode), so a failed fetch always says "Couldn’t open that. Try again." A bare
// `{#await import()}` is allowed only with its own `{:catch}` that does something.
const files = import.meta.glob(['/src/**/*.svelte'], {
  query: '?raw',
  import: 'default',
  eager: true
}) as Record<string, string>;

describe('lazy code', () => {
  it('has no {#await import()} without a {:catch}', () => {
    const bare: string[] = [];
    for (const [path, text] of Object.entries(files)) {
      for (const match of text.matchAll(/\{#await import\(/g)) {
        const rest = text.slice(match.index);
        const end = rest.indexOf('{/await}');
        if (!rest.slice(0, end).includes('{:catch')) bare.push(path);
      }
    }
    expect(bare).toEqual([]);
  });
});
