// Settings → Privacy: the switches for outside connections and "Your own network" (spec
// section 6, "Recipe import, decided for 0.5").
//
// Kept for the whole visit, so that if the connection drops the page still shows what was
// last loaded (it can't be changed until the connection is back). Forgotten on every way of
// signing out, so none of it carries over to whoever signs in next (see placesAndShops).
//
// A switch flips at once and is sent; if the server refuses or can't be reached it flips
// back and says so, so the page never keeps showing a switch the server doesn't have. The
// entry list answers in the server's own sentences (a refusal is shown as it is).

import { ApiError, cantReachWords, cantReach, forgetWhenSessionEnds } from './api';
import {
  addEntry,
  getOwnNetwork,
  getSwitches,
  putSwitch,
  removeEntry,
  type OwnNetworkEntry,
  type SwitchName
} from './client/privacy';
import { nothingChanged } from './downWords';
import { rememberToForget } from './forgetWhenLoaded';
import { network } from './network.svelte';
import { undoHistory } from './undo.svelte';

/** Chosen by the cause, the same on every page (cabledrawer 30 Oct). */
export const noConnection = (): string => nothingChanged(network.deviceOffline);
const FALLBACK = 'Something went wrong. Try again.';

/** The sentence to show for an error from the server or from not reaching it. */
function sentence(error: unknown): string {
  if (!(error instanceof ApiError)) return FALLBACK;
  return cantReach(error) ? noConnection() : error.detail;
}

/** The sentence when the page itself couldn't be loaded: the same words as every page. */
function loadSentence(error: unknown): string {
  return cantReach(error) ? cantReachWords() : sentence(error);
}

const OFF: Record<SwitchName, boolean> = {
  recipe_import: false,
  recipe_photos: false,
  single_sign_on: false,
  update_check: false
};

class Privacy {
  /** A first answer has come in (or a later one, after being forgotten). */
  loaded = $state(false);
  loading = $state(false);
  /** The page couldn't be loaded: the reason. */
  problem = $state<string | null>(null);

  switches = $state<Record<SwitchName, boolean>>({ ...OFF });
  entries = $state<OwnNetworkEntry[]>([]);
  limit = $state(100);
  /** An admin; a member sees everything and changes nothing. */
  canChange = $state(false);

  /** A switch didn't save: the reason (the switch is back as it was). */
  switchProblem = $state<string | null>(null);
  /** Adding to the list: the server's sentence for what's wrong with the text. */
  addProblem = $state<string | null>(null);
  adding = $state(false);
  /** Taking off the list didn't work: the reason. */
  removeProblem = $state<string | null>(null);
  /** Taking an entry off turned password sign-in back on: the server's sentence saying so. */
  removeNotice = $state<string | null>(null);

  /** What the server last said, per switch. */
  #confirmed: Record<SwitchName, boolean> = { ...OFF };
  /** Goes up with each change to a switch, so only the latest one's answer counts. */
  #latest: Record<SwitchName, number> = {
    recipe_import: 0,
    recipe_photos: 0,
    single_sign_on: 0,
    update_check: 0
  };
  #saving = 0;
  /** Goes up each time it's forgotten, so an answer to an earlier login is dropped. */
  #generation = 0;

  /**
   * True only when the server has said photo downloads are off. While the answer is still
   * coming, or couldn't be had (offline, an error), the state isn't known and this is false:
   * a screen that says "photos: not downloaded" must never say it on a guess.
   */
  get photosOff(): boolean {
    return this.loaded && !this.loading && this.problem === null && !this.switches.recipe_photos;
  }

  /** Fetch both (again, if already loaded: what's shown stays until the answer). */
  async load(): Promise<void> {
    const generation = this.#generation;
    this.loading = true;
    this.problem = null;
    try {
      const [switches, list] = await Promise.all([getSwitches(), getOwnNetwork()]);
      if (generation !== this.#generation) return;
      for (const s of switches.switches) this.#confirmed[s.connection] = s.on;
      // A switch being changed right now keeps what was chosen until its own answer comes.
      if (this.#saving === 0) this.switches = { ...this.#confirmed };
      this.entries = list.entries;
      this.limit = list.limit;
      this.canChange = switches.can_change && list.can_change;
      this.loaded = true;
    } catch (error) {
      if (generation !== this.#generation) return;
      this.problem = loadSentence(error);
    } finally {
      if (generation === this.#generation) this.loading = false;
    }
  }

  /** Add an entry to the end of the list. One a load() already brought in meanwhile is
   *  replaced, so the list never holds an id twice (the page keys its rows by id). */
  #put(entry: OwnNetworkEntry): void {
    this.entries = [...this.entries.filter((e) => e.id !== entry.id), entry];
  }

  /** Forget everything (another login's household may be next). */
  forget(): void {
    this.#generation += 1;
    this.loaded = false;
    this.loading = false;
    this.problem = null;
    this.switches = { ...OFF };
    this.#confirmed = { ...OFF };
    this.entries = [];
    this.limit = 100;
    this.canChange = false;
    this.switchProblem = null;
    this.addProblem = null;
    this.adding = false;
    this.removeProblem = null;
    this.removeNotice = null;
    this.#saving = 0;
  }

  /** Turn a switch on or off. */
  async setSwitch(name: SwitchName, on: boolean): Promise<void> {
    if (!this.canChange) return;
    const generation = this.#generation;
    const mine = ++this.#latest[name];
    this.switches[name] = on;
    this.switchProblem = null;
    this.#saving += 1;
    try {
      const answer = await putSwitch(name, on);
      if (generation !== this.#generation) return;
      for (const s of answer.switches) this.#confirmed[s.connection] = s.on;
      if (mine === this.#latest[name]) this.switches[name] = this.#confirmed[name];
    } catch (error) {
      if (generation !== this.#generation) return;
      // A newer change to the same switch decides what's shown; otherwise put it back.
      if (mine !== this.#latest[name]) return;
      this.switches[name] = this.#confirmed[name];
      this.switchProblem = sentence(error);
    } finally {
      if (generation === this.#generation) this.#saving -= 1;
    }
  }

  /** Add what was typed. True if it was added; otherwise `addProblem` says why. */
  async add(text: string): Promise<boolean> {
    if (!this.canChange || this.adding) return false;
    const generation = this.#generation;
    this.adding = true;
    this.addProblem = null;
    try {
      const entry = await addEntry(text);
      if (generation !== this.#generation) return false;
      this.#put(entry);
      undoHistory.record({
        label: `Added ${entry.value} to Your own network`,
        needsServer: true,
        undo: async () => {
          try {
            const answer = await removeEntry(entry.id);
            if (answer?.notice && this.#generation === generation)
              this.removeNotice = answer.notice;
          } catch (error) {
            // Already gone (taken off on another device): that's what Undo wanted.
            if (!(error instanceof ApiError && error.status === 404)) throw error;
          }
          if (this.#generation === generation) {
            this.entries = this.entries.filter((e) => e.id !== entry.id);
          }
        }
      });
      return true;
    } catch (error) {
      if (generation === this.#generation) this.addProblem = sentence(error);
      return false;
    } finally {
      if (generation === this.#generation) this.adding = false;
    }
  }

  /**
   * Take an entry off the list. It goes at once, with an Undo in the toast and on Ctrl+Z
   * (Undo, not "Are you sure?"); if the server can't be reached, it comes back.
   */
  async remove(entry: OwnNetworkEntry): Promise<void> {
    if (!this.canChange) return;
    const generation = this.#generation;
    const at = this.entries.findIndex((e) => e.id === entry.id);
    if (at === -1) return;
    this.removeProblem = null;
    this.removeNotice = null;
    this.entries = this.entries.filter((e) => e.id !== entry.id);
    let answer;
    try {
      answer = await removeEntry(entry.id);
    } catch (error) {
      if (generation !== this.#generation) return;
      // Already gone (an admin on another device took it off): nothing to put back.
      if (error instanceof ApiError && error.status === 404) return;
      const back = [...this.entries];
      back.splice(Math.min(at, back.length), 0, entry);
      this.entries = back;
      this.removeProblem = sentence(error);
      return;
    }
    if (generation !== this.#generation) return;
    if (answer?.notice) this.removeNotice = answer.notice;
    undoHistory.record({
      label: `Removed ${entry.value} from Your own network`,
      needsServer: true,
      undo: async () => {
        // Put back as a new entry (it keeps its text; it now says who put it back).
        const added = await addEntry(entry.value);
        if (this.#generation === generation) this.#put(added);
      }
    });
  }
}

export const privacy = new Privacy();

forgetWhenSessionEnds(() => privacy.forget());
// The shell forgets it on a wipe or a turned-away sign-in without loading this file for it.
rememberToForget('privacy', () => privacy.forget());
