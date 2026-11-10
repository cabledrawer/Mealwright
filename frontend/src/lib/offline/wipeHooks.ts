// Things that live only in the page and must be forgotten when this browser is wiped at sign-out
// (the several-links list: importLinks.svelte.ts). A tiny registry, so the wipe doesn't import
// the screens' code (the page size limit).

const hooks = new Set<() => void>();

export function forgetOnWipe(forget: () => void): void {
  hooks.add(forget);
}

export function runWipeHooks(): void {
  for (const forget of hooks) forget();
}
