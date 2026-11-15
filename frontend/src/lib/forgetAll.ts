// Everything held in memory for one person's time here, forgotten at once. The app's own
// stores are registered with `forgetWhenSessionEnds` (a session ended) or `forgetOnWipe` (the
// browser was wiped), or both (`forgetAtSignOut`); this runs both lists. Used wherever this tab
// finds out that the sign-in it showed is over: signing out here, another tab signing out, and
// turning a late-answering login away. (A 401 runs the session-end list by itself; a wipe runs
// the wipe list.)
import { runSessionEndHooks } from './api';
import { runWipeHooks } from './offline/wipeHooks';

export function forgetAll(): void {
  runSessionEndHooks();
  runWipeHooks();
}
