// Single sign-on's words (0.9 O1; word list section 78, cabledrawer 12 Nov). The sentences
// for the codes are the server's own (backend sso.MESSAGES): the server sends them with a
// refusal, and these show when it sends a browser back with `?sso=<code>` instead.

export const SSO_MESSAGES: Record<string, string> = {
  not_set_up: 'Single sign-on isn’t set up. Ask your household’s admin.',
  switched_off: 'Single sign-on is switched off in Settings → Privacy. Ask your household’s admin.',
  own_network:
    'Your sign-in server is on your own network. An admin adds it in Settings → Privacy → Your own network.',
  always_blocked: 'Mealwright can’t use that address for your sign-in server.',
  not_https:
    'Your sign-in server’s address must start with https://, unless it’s on your own network in Settings → Privacy.',
  unreachable: 'Mealwright couldn’t reach your sign-in server. Try again in a minute.',
  bad_answer: 'Your sign-in server gave an answer Mealwright couldn’t use.',
  refused: 'Your sign-in server’s answer couldn’t be checked, so you weren’t signed in.',
  expired: 'That sign-in took too long or was already used. Try again.',
  cancelled: 'Signing in was cancelled at your sign-in server.',
  wrong_address: 'Open Mealwright at the address single sign-on was set up for, then try again.',
  secret_unreadable:
    'Mealwright can’t read the saved client secret. An admin enters it again in Settings → Sign-in → Single sign-on.',
  not_let_in:
    'Your sign-in server doesn’t put you in a group Mealwright lets in. Ask your household’s admin.',
  no_account: 'There’s no Mealwright account for you yet. Ask your household’s admin.',
  // 0.9.5 Pe3/M2 (proposed, for cabledrawer): an admin chose "Not someone I know: refuse".
  not_known:
    'Your household’s admin doesn’t know this account, so it can’t sign in here. Ask them if that’s a mistake.',
  removed: 'That account was removed. Ask your household’s admin.',
  someone_else:
    'Your account is linked to someone else at your sign-in server. Sign out there and test again.',
  link_gone: 'There’s no test waiting to be linked. Test sign-in again.'
};

/** The sentence for a code from `?sso=`, or null when there's none. Unknown codes get the
 *  general one, never the code itself. */
export function ssoMessage(code: string | null | undefined): string | null {
  if (!code) return null;
  return SSO_MESSAGES[code] ?? SSO_MESSAGES.bad_answer ?? null;
}

export const signInWith = (button: string): string => `Sign in with ${button}`;

export const OR = 'or';

export const SIGNING_IN = 'Signing you in…';
export const BACK_TO_SIGN_IN = 'Back to sign in';

// "Almost there" (0.9.5 Pe3/M2, mockup Dark-SsoWaiting095-Phone): a single sign-on sign-in
// that matches nobody waits, with no session, until an admin says who it is.
export const ALMOST_THERE = 'Almost there';
/** Before and after the username, which is shown in bold between them. */
export const WAITING_BEFORE = 'You signed in with single sign-on as';
export const WAITING_AFTER =
  ', but this kitchen doesn’t know that name yet. An admin needs to say who you are: ask them to open Settings › Household.';
export const WAITING_NOTE =
  'Nothing in Mealwright is open to you until then. Once they’ve linked you, sign in again.';
export const SIGN_IN_AGAIN = 'Sign in again';
export const SIGN_OUT = 'Sign out';
export const BACK_TO_SETUP = 'Back to single sign-on';
export const TEST_TAB_DONE = 'You can close this tab: the setup tab shows the result.';

export const SETUP_ON_COMPUTER = 'Set up on a computer';
export const SETUP_PHONE_NOTE =
  'Single sign-on is set up on a computer: there’s a lot to copy between two screens.';

export const NOT_SET_UP = 'Not set up';

export const PASSWORD_ON = 'On';
export const PASSWORD_OFF = 'Off: everyone uses single sign-on';
export const PASSWORDS_NOTE =
  'Password sign-in can only be turned off while an admin can sign in with single sign-on.';

// Linking the admin's own login to who the test found (O1 review r1 H1; proposed, for cabledrawer).
export const linkQuestion = (me: string, them: string): string => `Link ${me} to ${them}?`;

/** "Your sign-in server says this is Tess R (tess@example.org)." */
export function linkWho(name: string | null | undefined, email: string | null | undefined) {
  const who = name && email ? `${name} (${email})` : name || email;
  return who ? `Your sign-in server says this is ${who}.` : '';
}

export const linkNote = (me: string): string =>
  `After linking, whoever signs in there as this person is ${me} here, an admin.`;
export const LINK = 'Link';
export const NOT_NOW = 'Not now';
export const linkedText = (me: string, them: string): string =>
  `${me} is linked to ${them} at your sign-in server.`;
export const NOT_LINKED_MEMBER =
  'Not linked to you: your sign-in server doesn’t make this person an Admin.';

/** "Test passed: signed in as tess, groups mealwright-admins → Admin." */
export function testPassedText(
  username: string | null,
  groups: string[],
  role: 'admin' | 'member' | null
): string {
  const who = username ?? 'someone';
  const as = role === 'admin' ? 'Admin' : 'Member';
  const from = groups.length ? `groups ${groups.join(', ')} → ${as}` : `no groups → ${as}`;
  return `Test passed: signed in as ${who}, ${from}.`;
}

/** Under "Anyone else" on the setup screen, where the "Make an account on first sign-in" switch
 *  was (Pe3/M2, cabledrawer 13 Nov: nobody is made at first sign-in; the words proposed, for
 *  cabledrawer). */
export const SSO_WHO_LINKS =
  'Someone whose username at your sign-in server is the same as here is linked to them at their first sign-in. Anyone else waits until an admin says who they are in Settings › Household.';
