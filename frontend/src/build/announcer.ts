import type { Plugin } from 'vite';

/**
 * SvelteKit's screen-reader announcer ("page changed") hides itself with an inline
 * style attribute, which the strict CSP blocks (style-src 'self', no inline styles).
 * Remove the attribute; src/lib/styles/base.css hides #svelte-announcer instead. The
 * build fails if SvelteKit's markup changes, or if the browser build (the one people
 * load) never finds the announcer, so this can't silently stop working (SvelteKit 3 moved
 * the markup out of the generated root.svelte). Each build (client, ssr) is tracked on its
 * own, and starts afresh, so one build finding it can't cover for another.
 */
export function announcerWithoutInlineStyle(): Plugin {
  const pattern = /(<div\s+id="svelte-announcer"[^>]*?)\s+style="[^"]*"/;
  const found = new Set<string>();
  const where = (context: { environment: { name: string } }) => context.environment.name;
  return {
    name: 'mealwright:announcer-without-inline-style',
    apply: 'build',
    enforce: 'pre',
    buildStart() {
      found.delete(where(this));
    },
    transform(code, id) {
      if (!/\.(svelte|js|ts)(\?|$)/.test(id) || !code.includes('svelte-announcer')) return null;
      if (!pattern.test(code)) {
        throw new Error(
          `the SvelteKit announcer markup has changed (${id}): update announcerWithoutInlineStyle() in src/build/announcer.ts`
        );
      }
      found.add(where(this));
      return { code: code.replace(pattern, '$1'), map: null };
    },
    buildEnd(error) {
      if (!error && where(this) === 'client' && !found.has('client')) {
        throw new Error(
          "The SvelteKit announcer was not found in the browser build: update announcerWithoutInlineStyle() in src/build/announcer.ts"
        );
      }
    }
  };
}
