// Everything in (app) needs a signed-in person. On the very first visit there's no
// account yet, so the first person creates the admin (spec section 7, no default
// admin). Otherwise, anyone not signed in goes to sign in, and comes back here after.
//
// When the server can't be reached, the app opens as whoever was last signed in on this
// device, so the shopping list works offline (docs/dev/sync-protocol.md section 11.4). With
// nobody to open as (never signed in here, or signed out), it shows the sign-in page.
//
// It doesn't wait long to find out (cabledrawer 20 Oct, hand test: the saved copy shows at once):
// if the server hasn't answered within half a second (at once when the browser says it is
// offline), the app opens as that person straight away, and the answer, when it comes, is
// decided on with the same rules as here (lib/offline/opening.ts). A late answer naming a
// different login never wipes while the screen is up: that login is turned away to the
// sign-in page instead (turnAwayLate).
import { isRedirect, redirect } from '@sveltejs/kit';
import { cantReach, type Me } from '#lib/api.js';
import { holdServerLists, releaseServerLists } from '#lib/offline/confirmed.js';
import { lastSignedIn, startDevice, type SignedIn } from '#lib/offline/device.js';
import { turnAway } from '#lib/offline/held.js';
import {
  answeredLate,
  askServer,
  inTime,
  newStart,
  openedOffline,
  takeLateAnswer,
  type Answer,
  type LateAnswer
} from '#lib/offline/opening.js';
import { drafts } from '#lib/drafts.svelte.js';
import { endSession } from '#lib/offline/signOut.js';
import { wipeIfAnotherLogin } from '#lib/offline/wipe.js';
import { wipePending } from '#lib/offline/wipePending.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { forgetAll } from '#lib/forgetAll.js';
import { forgetLoaded } from '#lib/forgetWhenLoaded.js';
import { updates } from '#lib/updates.svelte.js';
import { SETUP, session, signInPath } from '#lib/session.svelte.js';
import { shoppingSync } from '#lib/shopping/sync.svelte.js';
import { theme } from '#lib/theme.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, url, untrack }) => {
  // Only on starting the app and after signing in, not on every page change.
  const heading = untrack(() => url.pathname + url.search);
  const start = newStart();
  const late = takeLateAnswer();
  if (late) return decide(late.answer, heading, late.picks, late);
  // Theme picks when this start asks: a theme picked after that is newer than the server's
  // answer, and stays (cabledrawer 8 Nov). Kept with this start's answer, even when that answer
  // comes late and another start has begun meanwhile.
  const picks = theme.picks;
  const asked = askServer(fetch);
  const answer = await inTime(asked);
  if (answer) return decide(answer, heading, picks);
  // No answer yet: open as whoever was last signed in here, as offline, and decide when the
  // server answers. Not over someone else who has just signed in: they wait for it.
  const last = await lastSignedIn();
  if (last && (!session.me || session.me.id === last.id)) {
    holdServerLists();
    openAs(fromDevice(last));
    void answeredLate(asked, start, last.id, picks);
    return;
  }
  // Nobody to open as, and the browser says it is offline: no need to wait to know.
  if (!last && navigator.onLine === false) redirect(307, signInPath(heading));
  return decide(await asked, heading, picks);
};

/** Decide, then let the server's lists through: once it is known who is signed in, or that
 * nobody is (sign in, setup). Not after a server error: who is signed in still isn't known. */
async function decide(
  answer: Answer,
  heading: string,
  picks: number,
  late: LateAnswer | null = null
) {
  try {
    await decideNow(answer, heading, picks, late);
  } catch (error) {
    if (isRedirect(error)) releaseServerLists();
    throw error;
  }
  releaseServerLists();
}

async function decideNow(
  answer: Answer,
  heading: string,
  picks: number,
  late: LateAnswer | null
): Promise<void> {
  if ('error' in answer) {
    if (!cantReach(answer.error)) throw answer.error;
    const last = await lastSignedIn();
    if (!last) signIn(heading);
    // Offline: this device's theme stays as it is; nothing is saved to the account. The
    // server is asked who is signed in once it can be reached (askAgain).
    openAs(fromDevice(last));
    openedOffline(last.id, picks);
    return;
  }
  session.setup = answer.setup;
  if (answer.setup.needs_setup) {
    // Opened from this device already (a late answer): nobody is signed in here any more.
    session.me = null;
    redirect(307, SETUP);
  }
  const me = answer.me;
  if (!me) signIn(heading);
  if (late && me.id !== late.openedAs) return turnAwayLate(me, heading);
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
  // The account's theme wins over this device's copy, but not over a theme picked since the
  // app started (a slow server's answer is older than that choice).
  theme.adopt(me.theme, picks, me.id);
}

/**
 * The server answered late, naming a different login from the one the app opened as from this
 * device (signed in in another tab, say). Nothing is wiped while the screen is up, and the app
 * doesn't reload itself (11.6). Until the sign-in page shows, the app stays the device login's:
 * a change made meanwhile is queued as theirs, kept, and never sent as the other login (the
 * server refuses another login's batch, 11.5). That other login is signed out again and goes
 * to the sign-in page with its username filled in, as a login turned away at the start does;
 * the sign-in page then warns about the waiting changes, or wipes when there are none, by its
 * usual rules (11.5). What the app showed is forgotten first, so none of it carries over to
 * whoever signs in next. Not when a wipe is still unfinished: nobody may sign in until it is.
 */
async function turnAwayLate(me: Me, heading: string): Promise<never> {
  await endSession();
  if (!wipePending()) turnAway(me.username);
  shoppingSync.forget();
  placesAndShops.forget();
  forgetLoaded('privacy');
  updates.forget();
  drafts.forget();
  undoHistory.clear();
  toasts.dismiss();
  forgetAll();
  signIn(heading);
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
