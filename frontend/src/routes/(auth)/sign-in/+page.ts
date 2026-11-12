// What the sign-in page offers (0.9 O1): the password form, a "Sign in with …" button for
// single sign-on, or both. When the server can't be reached the form shows, as before: signing
// in then says it can't reach the server.
import { getSignInOptions, type SignInOptions } from '#lib/client/sso.js';
import type { PageLoad } from './$types';

const FORM_ONLY: SignInOptions = { password: true, sso_button: null };

export const load: PageLoad = async ({ fetch }) => {
  try {
    return { options: await getSignInOptions(fetch) };
  } catch {
    return { options: FORM_ONLY };
  }
};
