import { describe, expect, it } from 'vitest';
import base from './base.css?raw';
import tokens from './tokens.css?raw';
import toast from '../components/Toast.svelte?raw';
import status from '../components/ConnectionStatus.svelte?raw';

// The page on paper (docs/spec.md "Print", cabledrawer 13 Nov): the rules that make every page light
// and plain. (print.spec.ts checks them in a browser with the print media on.)
const printBlock = base.slice(base.indexOf('@media print'));

describe('the page on paper', () => {
  it('has the dark theme’s colours off, so every page prints in the light ones', () => {
    const at = tokens.indexOf('@media not print {');
    expect(at).toBeGreaterThan(0);
    const dark = tokens.indexOf(":root[data-theme='dark']");
    expect(dark).toBeGreaterThan(at);
    // The one block that holds the dark colours is inside it, and it is the last thing in the file.
    expect(tokens.slice(at).match(/data-theme='dark'/g)).toHaveLength(1);
    expect(tokens.trimEnd().endsWith('}\n}')).toBe(true);
  });

  it('hides only the app’s own chrome, not every status or alert on a page', () => {
    expect(printBlock).not.toMatch(/role=/);
    expect(toast).toMatch(/@media print\s*{\s*\.region\s*{\s*display:\s*none/);
    expect(status).toMatch(/@media print\s*{\s*\.status\s*{\s*display:\s*none/);
  });

  it('keeps a hidden pane row hidden', () => {
    expect(printBlock).toMatch(/\.panes \.row\[hidden\]\s*{\s*display:\s*none !important/);
  });
});
