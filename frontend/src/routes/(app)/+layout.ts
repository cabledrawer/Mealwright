// Everything in (app) needs a signed-in person. On the very first visit there's no
// account yet, so the first person creates the admin (spec section 7, no default
// admin). Otherwise, anyone not signed in goes to sign in, and comes back here after.
//
// When the server can't be reached, the app opens as whoever was last signed in on this
// device, so the shopping list works offline (docs/dev/sync-protocol.md section 11.4). With
// nobody to open as (never signed in here, or signed out), it shows the sign-in page.
//
// It doesn't wait long to find out (cabledrawer 20 Oct, hand test): if the server hasn't
// answered within half a second (at once when the browser says it is offline), the app opens
// as that person straight away, and the answer, when it comes, is decided on with the same
// rules as here (lib/offline/opening.ts).
import { redirect } from '@sveltejs/kit';
import { cantReach, type Me } from '$lib/api';
import { holdServerLists, releaseServerLists } from '$lib/offline/confirmed';
import { lastSignedIn, startDevice, type SignedIn } from '$lib/offline/device';
import { turnAway } from '$lib/offline/held';
import {
  answeredLate,
  askServer,
  inTime,
  newStart,
  takeLateAnswer,
  type Answer
} from '$lib/offline/opening';
import { endSession } from '$lib/offline/signOut';
import { wipeIfAnotherLogin } from '$lib/offline/wipe';
import { SETUP, session, signInPath } from '$lib/session.svelte';
import { theme } from '$lib/theme.svelte';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, url, untrack }) => {
  // Only on starting the app and after signing in, not on every page change.
  const heading = untrack(() => url.pathname + url.search);
  const start = newStart();
  const late = takeLateAnswer();
  if (late) return decide(late, heading);
  const asked = askServer(fetch);
  const answer = await inTime(asked);
  if (answer) return decide(answer, heading);
  // No answer yet: open as whoever was last signed in here, as offline, and decide when the
  // server answers. Not over someone else who has just signed in: they wait for it.
  const last = await lastSignedIn();
  if (last && (!session.me || session.me.id === last.id)) {
    holdServerLists();
    openAs(fromDevice(last));
    void answeredLate(asked, start);
    return;
  }
  // Nobody to open as, and the browser says it is offline: no need to wait to know.
  if (!last && navigator.onLine === false) redirect(307, signInPath(heading));
  return decide(await asked, heading);
};

async function decide(answer: Answer, heading: string): Promise<void> {
  try {
    await decideNow(answer, heading);
  } finally {
    releaseServerLists();
  }
}

async function decideNow(answer: Answer, heading: string): Promise<void> {
  if ('error' in answer) {
    if (!cantReach(answer.error)) throw answer.error;
    const last = await lastSignedIn();
    if (!last) signIn(heading);
    // Offline: this device's theme stays as it is; nothing is saved to the account.
    openAs(fromDevice(last));
    return;
  }
  session.setup = answer.setup;
  if (answer.setup.needs_setup) redirect(307, SETUP);
  const me = answer.me;
  if (!me) signIn(heading);
  // Signed in as a different login from the one this device holds (perhaps in another tab):
  // start clean, as at sign-out (cabledrawer 18 Oct). Not over someone's waiting changes: those
  // are never sent under another login, never written over, and lost only through the
  // sign-in page's warning (11.5, section 16 decision 4). So this login is signed out again
  // before anything here is touched (the device's `meta`, copy and sender stay as they are),
  // and goes to that warning, with its username filled in. The same when the phone database
  // can't be read: whose changes are waiting isn't known, so nothing is wiped or written and
  // the sign-in page says it couldn't check. Except for the login it was last written for,
  // which carries on, still wiping and writing nothing (cabledrawer 18 Oct). If the server won't end that session, the
  // sign-in page says so and stays (it doesn't send this login back here, to be turned away
  // again and again); still nothing is wiped. And if a wipe couldn't delete the phone
  // database, nobody is let in until it has been: the sign-in page says so, with Try again.
  const held = await wipeIfAnotherLogin(me);
  if (held !== 'kept' && held !== 'wiped') {
    await endSession();
    if (held !== 'wipe-failed') turnAway(me.username);
    signIn(heading);
  }
  openAs(me);
  await startDevice(me);
  // The account's theme wins over this device's copy.
  theme.adopt(me.theme);
}

/** To the sign-in page. Opened from this device already (the server answered late): nobody
 * is signed in here any more. */
function signIn(heading: string): never {
  session.me = null;
  redirect(307, signInPath(heading));
}

function fromDevice(last: SignedIn): Me {
  return {
    id: last.id,
    name: last.name,
    username: last.username,
    role: last.role === 'admin' ? 'admin' : 'member',
    theme: theme.choice
  };
}

/** The same login carries on in place (its Undo kept); anyone else replaces it. */
function openAs(me: Me): void {
  if (session.me && session.me.id === me.id) Object.assign(session.me, me);
  else session.me = me;
}
