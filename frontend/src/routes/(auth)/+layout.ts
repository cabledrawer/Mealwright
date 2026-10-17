// Sign in and first-run setup. Setup is reachable only while there's no account yet;
// sign in only once there is one. Someone already signed in goes straight on.
import { redirect } from '@sveltejs/kit';
import { getMe, getSetup } from '$lib/api';
import { SETUP, SIGN_IN, safeNext, session } from '$lib/session.svelte';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, url }) => {
  const setup = await getSetup(fetch);
  session.setup = setup;
  const onSetup = url.pathname === SETUP;
  if (setup.needs_setup && !onSetup) redirect(307, SETUP);
  if (!setup.needs_setup && onSetup) redirect(307, SIGN_IN);
  if (!setup.needs_setup && (await getMe(fetch))) {
    redirect(307, safeNext(url.searchParams.get('next')));
  }
  return { setup };
};
