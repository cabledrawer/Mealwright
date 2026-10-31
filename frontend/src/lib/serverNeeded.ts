// A change that needs the server, asked for while it can't be reached (F80 review): nothing is
// sent, and the usual words say why. Controls that can be greyed out are disabled instead.
import { cantReachWords } from './api';
import { network } from './network.svelte';
import { toasts } from './toast.svelte';

/** True (after saying why) when the server can't be reached and the change must wait. */
export function blockedWhileDown(): boolean {
  if (!network.offline) return false;
  toasts.show(cantReachWords());
  return true;
}
