// "Cooked it" says a failure once, itself (cookReview.svelte.ts), so the meal's answer sends
// without a toast, and again once with the same change ID if its reply never came: the server
// then answers from the first and does nothing twice.

import { newChangeId } from './changeId';
import { worthRetrying } from './api';
import type { Outcome } from './save';

export async function sendTwice<T>(
  send: (changeId: string) => Promise<Outcome<T>>
): Promise<Outcome<T>> {
  const changeId = newChangeId();
  const first = await send(changeId);
  return !first.ok && !first.cancelled && worthRetrying(first.error) ? send(changeId) : first;
}
