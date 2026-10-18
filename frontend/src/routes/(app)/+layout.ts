// Everything in (app) needs a signed-in person. On the very first visit there's no
// account yet, so the first person creates the admin (spec section 7, no default
// admin). Otherwise, anyone not signed in goes to sign in, and comes back here after.
//
// When the server can't be reached, the app opens as whoever was last signed in on this
// device, so the shopping list works offline (docs/dev/sync-protocol.md section 11.4).
import { redirect } from '@sveltejs/kit';
import { cantReach, getMe, getSetup, type Me } from '$lib/api';
import { lastSignedIn, startDevice } from '$lib/offline/device';
import { SETUP, session, signInPath } from '$lib/session.svelte';
import { theme } from '$lib/theme.svelte';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, url, untrack }) => {
  // Only on starting the app and after signing in, not on every page change.
  const heading = untrack(() => url.pathname + url.search);
  let me: Me | null;
  try {
    const setup = await getSetup(fetch);
    session.setup = setup;
    if (setup.needs_setup) redirect(307, SETUP);
    me = await getMe(fetch);
  } catch (error) {
    const last = cantReach(error) ? await lastSignedIn() : null;
    if (!last) throw error;
    // Offline: this device's theme stays as it is; nothing is saved to the account.
    session.me = {
      id: last.id,
      name: last.name,
      username: last.username,
      role: last.role === 'admin' ? 'admin' : 'member',
      theme: theme.choice
    };
    return;
  }
  if (!me) redirect(307, signInPath(heading));
  session.me = me;
  await startDevice(me);
  // The account's theme wins over this device's copy.
  theme.adopt(me.theme);
};
