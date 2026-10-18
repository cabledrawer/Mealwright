// Sign in and first-run setup. Setup is reachable only while there's no account yet;
// sign in only once there is one. Someone already signed in goes straight on.
//
// When the server can't be reached (just signed out offline, docs/dev/sync-protocol.md
// section 12), the sign-in page still shows: signing in then says it can't reach the server.
// So does it when signing out couldn't be finished: the old session would only send this
// browser back into the app, to be signed out again, round and round.
import { redirect } from '@sveltejs/kit';
import { cantReach, getMe, getSetup, type SetupState } from '$lib/api';
import { signOutState } from '$lib/offline/unfinished.svelte';
import { SETUP, SIGN_IN, safeNext, session } from '$lib/session.svelte';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, url }) => {
  let setup: SetupState;
  try {
    setup = await getSetup(fetch);
  } catch (error) {
    if (!cantReach(error) || url.pathname === SETUP) throw error;
    // Not known offline: plain http:// counts as not allowed until the server says so.
    return { setup: session.setup ?? { needs_setup: false, plain_http_allowed: false } };
  }
  session.setup = setup;
  const onSetup = url.pathname === SETUP;
  if (setup.needs_setup && !onSetup) redirect(307, SETUP);
  if (!setup.needs_setup && onSetup) redirect(307, SIGN_IN);
  if (!setup.needs_setup && !signOutState.unfinished && (await getMe(fetch))) {
    redirect(307, safeNext(url.searchParams.get('next')));
  }
  return { setup };
};
