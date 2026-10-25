import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { playwright } from '@vitest/browser-playwright';
import { defineConfig } from 'vitest/config';
import { announcerWithoutInlineStyle } from './src/build/announcer.ts';

/**
 * The SvelteKit and Svelte options (SvelteKit 3 keeps them here, not in svelte.config.js).
 * Exported so eslint.config.js can read the same options.
 */
export const svelteOptions = {
  preprocess: vitePreprocess(),
  // A single-page app: the backend serves build/index.html for every path outside
  // /api, and the app draws each page in the browser (no server rendering).
  adapter: adapter({ pages: 'build', assets: 'build', fallback: 'index.html', strict: true }),
  // Absolute paths, so files load correctly on any page the fallback serves.
  paths: { relative: false },
  // No hourly check for a new version: updates come through our service worker
  // (cabledrawer, 25 Oct 2026).
  version: { pollInterval: 0 },
  compilerOptions: { runes: true }
};

export default defineConfig({
  plugins: [announcerWithoutInlineStyle(), sveltekit(svelteOptions)],
  build: {
    // Fonts stay as separate files instead of being inlined into the CSS.
    assetsInlineLimit: 0
  },
  test: {
    // Unit and component tests run in real headless Chromium, so they see the same
    // CSS and DOM as the app does.
    include: ['src/**/*.test.ts'],
    browser: {
      enabled: true,
      headless: true,
      provider: playwright(),
      instances: [{ browser: 'chromium' }]
    }
  }
});
