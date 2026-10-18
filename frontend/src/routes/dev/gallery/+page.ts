// The component gallery (spec "Keeping the UI good", item 3) exists only in development
// builds. `import.meta.env.DEV` is replaced by `false` when the app is built, so the
// branch below, and with it the whole gallery, is dropped from the build. Here only a
// "not found" is left. A test (e2e/tests/gallery.spec.ts) searches the built app and the
// image for its marker text and checks that this address shows "not found" there.
import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
  if (import.meta.env.DEV) {
    const { default: Gallery } = await import('./Gallery.svelte');
    return { Gallery };
  }
  error(404, 'Not found');
};
