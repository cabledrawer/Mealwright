import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    // A single-page app: the backend serves build/index.html for every path outside
    // /api, and the app draws each page in the browser (no server rendering).
    adapter: adapter({ pages: 'build', assets: 'build', fallback: 'index.html', strict: true }),
    // Absolute paths, so files load correctly on any page the fallback serves.
    paths: { relative: false }
  },
  compilerOptions: {
    runes: true
  }
};

export default config;
