// Settings → Household (0.9 A1): the household's people, loaded once and shared by the Household
// and Person screens. Every change answers with the whole list and the change made, so its Undo
// (the toast, Ctrl+Z, Recent changes) is the server's own. Admins only change; everyone looks.

import { ApiError, cantReach, cantReachWords, forgetWhenSessionEnds } from './api';
import { lastOwnChange, onUndoOf, serverUndo } from './client/changes';
import { changed, getHousehold } from './client/household';
import {
  addPerson,
  changePerson,
  getPeople,
  linkSignIn,
  refuseSignIn,
  removePerson,
  unlinkSignIn,
  setAskWhosThis,
  type Colour,
  type People,
  type PersonChange,
  type WaitingSignIn
} from './client/people';
import { nothingChanged } from './downWords';
import { network } from './network.svelte';
import { undoHistory } from './undo.svelte';
import { api } from './api';
import type { Household } from './client/types';

const FALLBACK = 'Something went wrong. Try again.';

/** The sentence for an error: the server's own, or "can't reach". */
export function sentence(error: unknown): string {
  if (!(error instanceof ApiError)) return FALLBACK;
  return cantReach(error) ? nothingChanged(network.deviceOffline) : error.detail;
}

class Household_ {
  loaded = $state(false);
  /** Why the list couldn't be loaded (the page shows it with Try again). */
  problem = $state<string | null>(null);
  people = $state<People['people']>([]);
  canChange = $state(false);
  askWhosThis = $state(false);
  /** "Who is this?" (0.9.5 Pe3/M2): single sign-on sign-ins waiting for an admin. */
  waiting = $state<WaitingSignIn[]>([]);
  /** Single sign-on is set up (admins only): the Person page shows who is linked. */
  singleSignOn = $state(false);
  name = $state('');
  /** The household's time zone, for times on the Person page (null: this device's own). */
  zone = $state<string | null>(null);
  /** How long a removal can be undone (the household's own setting). */
  undoDays = $state(7);
  /** A change is on its way to the server. */
  busy = $state(false);
  #generation = 0;

  forget() {
    this.#generation++;
    this.loaded = false;
    this.problem = null;
    this.people = [];
    this.canChange = false;
    this.askWhosThis = false;
    this.waiting = [];
    this.singleSignOn = false;
    this.name = '';
    this.zone = null;
    this.busy = false;
  }

  #put(found: People) {
    this.people = found.people;
    this.canChange = found.can_change;
    this.askWhosThis = found.ask_whos_this;
    this.waiting = found.waiting ?? [];
    this.singleSignOn = found.single_sign_on ?? false;
  }

  async load(): Promise<void> {
    const generation = this.#generation;
    try {
      const [found, household] = await Promise.all([getPeople(), getHousehold()]);
      if (generation !== this.#generation) return;
      this.#put(found);
      this.name = household.name;
      this.zone = household.time_zone;
      this.undoDays = household.undo_days;
      this.problem = null;
      this.loaded = true;
    } catch (error) {
      if (generation !== this.#generation) return;
      this.problem = cantReach(error) ? cantReachWords() : sentence(error);
    }
  }

  /** Make a change; true when it was made. A refusal throws, with the server's sentence. */
  async #write(made: Promise<People>): Promise<boolean> {
    const generation = this.#generation;
    this.busy = true;
    try {
      const found = await made;
      if (generation !== this.#generation) return false;
      this.#put(found);
      if (found.change) {
        undoHistory.record({
          label: found.change.summary,
          needsServer: true,
          undo: serverUndo(found.change.id, () => void this.load())
        });
      }
      return true;
    } finally {
      if (generation === this.#generation) this.busy = false;
    }
  }

  add(name: string, colour: Colour | null, portion: number) {
    return this.#write(addPerson(name, colour, portion));
  }

  change(id: number, change: PersonChange) {
    return this.#write(changePerson(id, change));
  }

  remove(id: number) {
    return this.#write(removePerson(id));
  }

  /** Link a waiting sign-in to a person, or to a new person (null). */
  link(id: number, memberId: number | null) {
    return this.#write(linkSignIn(id, memberId));
  }

  /** Unlink a person from their account at the sign-in server. */
  unlink(memberId: number) {
    return this.#write(unlinkSignIn(memberId));
  }

  /** "Not someone I know: refuse". */
  refuse(id: number) {
    return this.#write(refuseSignIn(id));
  }

  ask(on: boolean) {
    return this.#write(setAskWhosThis(on));
  }

  /** The household's name (admins). The server's own change, with its Undo. */
  async rename(name: string): Promise<void> {
    const before = this.name;
    this.name = name;
    try {
      const household = await changed(api<Household>('PATCH', '/household', { name }));
      this.name = household.name;
      if (household.name === before) return;
      // The rename is the server's own change (household_renamed): its Undo is the server's.
      const last = await lastOwnChange();
      if (last) undoHistory.record(last);
    } catch (error) {
      this.name = before;
      throw error;
    }
  }
}

export const household = new Household_();

forgetWhenSessionEnds(() => household.forget());

// An Undo from anywhere (Recent changes, Ctrl+Z after a reload) puts people back: look again.
for (const kind of [
  'person_added',
  'person_changed',
  'person_removed',
  'whos_this_switch',
  'household_renamed'
]) {
  onUndoOf(kind, () => {
    if (household.loaded) void household.load();
  });
}
