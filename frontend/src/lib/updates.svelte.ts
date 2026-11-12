// Settings → About's update parts (spec section 7 "Updates"; plan row X1): what the server says
// about its version, and an admin's Check now. Loading it never connects anywhere outside;
// Check now asks the server, which asks the release list through its outbound gate as a
// person's press, whatever the Privacy switch says (it controls only the daily check).

import { ApiError, cantReach, cantReachWords, forgetWhenSessionEnds } from './api';
import { checkNow, getUpdates, type Updates } from './client/updates';

class UpdateState {
  info = $state<Updates | null>(null);
  loading = $state(false);
  /** The page couldn't be loaded: the reason. */
  problem = $state<string | null>(null);
  checking = $state(false);
  /** Check now itself didn't reach the server: the reason. */
  checkProblem = $state<string | null>(null);
  /** Goes up each time it's forgotten, so an answer to an earlier login is dropped. */
  #generation = 0;

  /** An admin, and the last answer said a newer version is out: "Update available". */
  get available(): boolean {
    return this.info?.can_check === true && this.info.last?.outcome === 'newer';
  }

  async load(): Promise<void> {
    const mine = this.#generation;
    this.loading = true;
    try {
      const info = await getUpdates();
      if (mine !== this.#generation) return;
      this.info = info;
      this.problem = null;
    } catch (error) {
      if (mine !== this.#generation) return;
      this.problem = sentence(error);
    } finally {
      if (mine === this.#generation) this.loading = false;
    }
  }

  async check(): Promise<void> {
    if (this.checking) return;
    const mine = this.#generation;
    this.checking = true;
    this.checkProblem = null;
    try {
      const info = await checkNow();
      if (mine === this.#generation) this.info = info;
    } catch (error) {
      if (mine === this.#generation) this.checkProblem = sentence(error);
    } finally {
      if (mine === this.#generation) this.checking = false;
    }
  }

  forget(): void {
    this.#generation++;
    this.info = null;
    this.loading = false;
    this.problem = null;
    this.checking = false;
    this.checkProblem = null;
  }
}

function sentence(error: unknown): string {
  if (error instanceof ApiError && !cantReach(error)) return error.detail;
  return cantReachWords();
}

export const updates = new UpdateState();

forgetWhenSessionEnds(() => updates.forget());
