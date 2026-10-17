import { sveltekit } from '@sveltejs/kit/vite';
import { playwright } from '@vitest/browser-playwright';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

/**
 * SvelteKit's screen-reader announcer ("page changed") hides itself with an inline
 * style attribute, which the strict CSP blocks (style-src 'self', no inline styles).
 * Remove the attribute; src/lib/styles/base.css hides #svelte-announcer instead. The
 * build fails if SvelteKit's markup changes, so this can't silently stop working.
 */
function announcerWithoutInlineStyle(): Plugin {
  const pattern = /(<div id="svelte-announcer"[^>]*?)\s+style="[^"]*"/;
  return {
    name: 'mealwright:announcer-without-inline-style',
    enforce: 'pre',
    transform(code, id) {
      if (!id.endsWith('/.svelte-kit/generated/root.svelte')) return null;
      if (!pattern.test(code)) {
        throw new Error(
          "SvelteKit's announcer markup has changed: update announcerWithoutInlineStyle() in vite.config.ts"
        );
      }
      return { code: code.replace(pattern, '$1'), map: null };
    }
  };
}

export default defineConfig({
  plugins: [announcerWithoutInlineStyle(), sveltekit()],
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
