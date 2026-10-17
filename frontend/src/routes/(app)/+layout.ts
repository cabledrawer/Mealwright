// Everything in (app) needs a signed-in person. On the very first visit there's no
// account yet, so the first person creates the admin (spec section 7, no default
// admin). Otherwise, anyone not signed in goes to sign in, and comes back here after.
import { redirect } from '@sveltejs/kit';
import { getMe, getSetup } from '$lib/api';
import { SETUP, session, signInPath } from '$lib/session.svelte';
import { theme } from '$lib/theme.svelte';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, url, untrack }) => {
  // Only on starting the app and after signing in, not on every page change.
  const heading = untrack(() => url.pathname + url.search);
  const setup = await getSetup(fetch);
  session.setup = setup;
  if (setup.needs_setup) redirect(307, SETUP);
  const me = await getMe(fetch);
  if (!me) redirect(307, signInPath(heading));
  session.me = me;
  // The account's theme wins over this device's copy.
  theme.adopt(me.theme);
};
