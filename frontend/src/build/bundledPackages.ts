import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type { Plugin } from 'vite';

/** The package a module of node_modules belongs to ("clsx", "@scope/name"), or null. */
export function packageOf(id: string): string | null {
  const path = id.split('?')[0].replaceAll('\\', '/');
  const at = path.lastIndexOf('/node_modules/');
  if (at < 0) return null;
  const [first, second] = path.slice(at + '/node_modules/'.length).split('/');
  if (!first) return null;
  return first.startsWith('@') ? (second ? `${first}/${second}` : null) : first;
}

/**
 * Writes the names of every npm package whose code is in the browser bundle to `file`, for
 * scripts/third-party-licences.mjs: the licence notices cover what the app really carries,
 * not a list kept by hand (#207 review M1). Only the browser build counts: the build's server
 * step is never shipped.
 */
export function bundledPackages(file: string): Plugin {
  // The browser code is built in more than one step (the app, its service worker): all count.
  const names = new Set<string>();
  return {
    name: 'mealwright-bundled-packages',
    apply: 'build',
    generateBundle(_options, bundle) {
      if (this.environment?.config.consumer === 'server') return;
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== 'chunk') continue;
        for (const id of Object.keys(chunk.modules)) {
          const name = packageOf(id);
          if (name) names.add(name);
        }
      }
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, JSON.stringify([...names].sort(), null, 2) + '\n');
    }
  };
}

export const BUNDLED_PACKAGES_FILE = join('.svelte-kit', 'bundled-packages.json');
