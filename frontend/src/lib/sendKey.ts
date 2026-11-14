// The change ID for sending one body. The server refuses an ID sent again with a different body
// (0.9.5), so the same body keeps its ID (the honest retry after a lost answer) and a body edited
// since the last send gets a new one.

import { newChangeId } from './changeId';

export class SendKey {
  #key = newChangeId();
  #sent: string | null = null;

  /** The ID for `body`: the same while the body is the same, a new one once it has changed. */
  for(body: unknown): string {
    const text = JSON.stringify(body);
    if (this.#sent !== null && this.#sent !== text) this.#key = newChangeId();
    this.#sent = text;
    return this.#key;
  }

  /** A new ID for a fresh start. */
  reset(): void {
    this.#key = newChangeId();
    this.#sent = null;
  }
}
