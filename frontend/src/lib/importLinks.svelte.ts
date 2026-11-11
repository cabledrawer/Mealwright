// Several links at once (cabledrawer 31 Oct, F110; spec "Decided for 0.8.0"): each link is read on
// its own, one after another (never together), and kept as its own draft to check later. A link
// that fails shows its own sentence and the rest carry on. Each read is the ordinary single-link
// import, so the same Privacy switch, the outbound gate and server-only fetching apply.
//
// The state lives here, not in the page, so leaving the screen inside the app doesn't stop the
// reading (the screen says "You can leave this screen").

import { SvelteURL } from 'svelte/reactivity';
import { forgetWhenSessionEnds } from './api';
import { serverUndo } from './client/changes';
import type { Saved } from './client/imports';
import { drafts } from './drafts.svelte';
import { kitchen } from './freshness.svelte';
import { saveFromDraft } from './import.draftSave';
import { ImportFlow } from './import.svelte';
import { toasts } from './toast.svelte';
import { undoHistory } from './undo.svelte';
import { forgetOnWipe } from './offline/wipeHooks';

/** Words on the screen (mockup Dark-ImportLinks08-Phone; "in Drafts" is agreed; "✓ All matched" and
 *  "Needs checking" are cabledrawer 11 Nov; the rest is proposed, for cabledrawer). */
export const ALL_MATCHED = '✓ All matched';
export const NEEDS_CHECKING = 'Needs checking';
export const READING = 'Reading…';
/** The button on a link that failed (RF4 I3; proposed, for cabledrawer). */
export const TRY_AGAIN = 'Try again';
export const WAITING = 'Waiting';
export const SAVED = '✓ Saved';
export const IN_DRAFTS = 'in Drafts';
export const LINKS_HELP =
  'Each recipe goes to Drafts to check and save later. If one link can’t be read, the rest carry on. You can leave this screen.';
export const LINKS_SERVER_NOTE =
  'Only Mealwright’s server fetches these pages, and only because Recipe import is switched on in Settings.';
/** Quick import (F216, cabledrawer 10 Nov; the words are accepted, cabledrawer 11 Nov). */
export const savedWords = (count: number): string =>
  `Saved ${count} ${count === 1 ? 'recipe' : 'recipes'}`;
export const saveReadyWords = (count: number): string =>
  `Save ${count} ready ${count === 1 ? 'recipe' : 'recipes'}`;
/** After the one Undo of a quick import when some of the saves couldn't be taken back (proposed,
 *  for cabledrawer). */
export const undidWords = (done: number, total: number): string => `Undid ${done} of ${total}`;
export const GONE_FROM_DRAFTS = 'No longer in Drafts';
export const QUICK_HELP =
  'Ready means every ingredient matched. The others stay in Drafts for you to check.';
export const ALREADY_HAVE = 'You already have this recipe. It was not read again.';

/** The most links one paste reads (proposed, for cabledrawer). */
export const MOST_LINKS = 20;
/** The household's most drafts (the server's `MAX_DRAFTS`). */
export const DRAFT_LIMIT = 50;

/** Said under the box before anything is pasted (F208, cabledrawer 10 Nov; the words are proposed,
 *  for cabledrawer). The number is `MOST_LINKS`, the one the paste is cut at. */
export const pasteLimitWords = (): string =>
  `You can paste up to ${MOST_LINKS} links at once. Mealwright reads them one after another.`;

/** Said under the list when a paste had more links than were read (proposed, for cabledrawer). */
export const leftOutWords = (left: number, room: number | null): string =>
  `${left} more ${left === 1 ? 'link was' : 'links were'} left out. A paste reads up to ${MOST_LINKS} links${
    room !== null && room < MOST_LINKS ? `, and Drafts has room for ${room} more` : ''
  }.`;

/** Said when Drafts had no room at all, so no link was read (proposed, for cabledrawer). */
export const noneReadWords = (count: number): string =>
  count === 1
    ? 'Drafts is full: the link was not read. Finish or delete a draft first.'
    : `Drafts is full: none of the ${count} links were read. Finish or delete a draft first.`;

/** Why the rest were not read when Drafts is full or links are switched off (proposed). */
export const STOPPED_DRAFTS_FULL = 'Not read: Drafts is full. Finish or delete a draft first.';
export const STOPPED_SWITCHED_OFF = 'Not read: importing from links is switched off.';

export const linksHeading = (count: number): string => `${count} links · one after another`;

export interface LinkRow {
  link: string;
  /** The site, without "www.". */
  site: string;
  /** The link's last word until the recipe's name is read. */
  title: string;
  state: 'waiting' | 'reading' | 'ready' | 'failed';
  /** Why a failed link failed: the server's own sentence. */
  message: string | null;
  /** The failure's code, for "Paste text" (offered where pasting the text can help). */
  code: string | null;
  /** The draft a read link was kept as, so its row can open it (F209). */
  draftId: number | null;
  /** The recipe a quick import saved it as (F216), until that is undone. */
  savedId: number | null;
  /** Every ingredient line matched, none to confirm or needing the person: the draft can be saved
   *  as it is (quick import, F216). */
  allMatched: boolean;
}

/** The codes after which pasting the page's text is the way forward (as for one link). */
const PASTE_HELPS = /^(site_refused|import_switched_off|bad_link|not_a_page|no_recipe|cant_read)$/;
export const canPaste = (row: LinkRow): boolean => row.code !== null && PASTE_HELPS.test(row.code);

/** A link as the server reads it (scheme added, host in lower case, no fragment, no trailing
 *  slash), so the same page typed two ways is read once. A link that can't be read as one stays
 *  as it was. */
export function sameLink(link: string): string {
  try {
    const url = new SvelteURL(/^[a-z][a-z0-9+.-]*:\/\//i.test(link) ? link : `https://${link}`);
    const path = url.pathname.replace(/\/+$/, '');
    return `${url.protocol}//${url.host}${path}${url.search}`;
  } catch {
    return link;
  }
}

function parts(link: string): { site: string; title: string } {
  try {
    const url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(link) ? link : `https://${link}`);
    const site = url.hostname.replace(/^www\./i, '');
    const slug = url.pathname.split('/').filter(Boolean).pop() ?? '';
    return { site, title: decodeURIComponent(slug) || site };
  } catch {
    return { site: '', title: link };
  }
}

/** Every ingredient line is tied to an ingredient (matched, or a staple), and there is at least
 *  one: nothing is to confirm and nothing needs the person (F216). */
export function readyToSave(flow: ImportFlow): boolean {
  const lines = flow.review?.lines.filter((line) => line.kind === 'ingredient') ?? [];
  return lines.length > 0 && flow.unlinked === 0;
}

export class ImportLinks {
  rows = $state<LinkRow[]>([]);
  running = $state(false);

  /** How many links of the last paste were left out (over the most, or no room in Drafts). */
  leftOut = $state(0);
  /** Drafts' room at that time, when it limited the paste. */
  room = $state<number | null>(null);
  /** Bumped when the session ends, so a run that is still going stops. */
  #generation = 0;

  /** Read the links one after another, each into its own draft. Never throws. */
  async run(links: string[]): Promise<void> {
    if (this.running) return;
    // Set before the first await: two quick pastes must not start two runs.
    this.running = true;
    const generation = this.#generation;
    try {
      const seen: string[] = [];
      const unique = links.filter((link) => {
        const key = sameLink(link);
        if (seen.includes(key)) return false;
        seen.push(key);
        return true;
      });
      if (!drafts.loaded) await drafts.load();
      if (generation !== this.#generation) return;
      // A press after some links failed reads only the links not read yet: a row that is ready
      // with its draft still in Drafts (or already saved) is kept as it is, so no recipe gets a
      // second draft (RF4 I3).
      const before = [...this.rows];
      const kept = (link: string): LinkRow | undefined => {
        const row = before.find((each) => sameLink(each.link) === sameLink(link));
        return row && row.state === 'ready' && !this.gone(row) ? row : undefined;
      };
      const fresh = unique.filter((link) => !kept(link));
      const room = drafts.count === null ? null : Math.max(0, DRAFT_LIMIT - drafts.count);
      const allowed = Math.min(MOST_LINKS, room ?? MOST_LINKS);
      this.leftOut = Math.max(0, fresh.length - allowed);
      this.room = room;
      const taken = fresh.slice(0, allowed);
      this.rows = unique.flatMap((link) => {
        const row = kept(link);
        if (row) return [row];
        if (!taken.includes(link)) return [];
        return [
          {
            link,
            ...parts(link),
            state: 'waiting' as const,
            message: null,
            code: null,
            draftId: null,
            savedId: null,
            allMatched: false
          }
        ];
      });
      let stopped: string | null = null;
      for (const row of this.rows) {
        if (generation !== this.#generation) return;
        if (row.state !== 'waiting') continue; // read in an earlier press
        if (stopped) {
          row.state = 'failed';
          row.message = stopped;
          row.code = 'stopped';
          continue;
        }
        await this.#one(row, generation);
        if (generation !== this.#generation) return;
        if (row.code === 'too_many_drafts') stopped = STOPPED_DRAFTS_FULL;
        else if (row.code === 'import_switched_off') stopped = STOPPED_SWITCHED_OFF;
      }
    } finally {
      if (generation === this.#generation) this.running = false;
    }
  }

  /** Read one failed link again, on its own row (RF4 I3). The other rows are left as they are. */
  async retry(row: LinkRow): Promise<void> {
    if (this.running || this.saving || row.state !== 'failed') return;
    this.running = true;
    const generation = this.#generation;
    try {
      row.message = null;
      row.code = null;
      await this.#one(row, generation);
    } finally {
      if (generation === this.#generation) this.running = false;
    }
  }

  async #one(row: LinkRow, generation: number): Promise<void> {
    row.state = 'reading';
    const flow = new ImportFlow();
    flow.text = row.link;
    try {
      await flow.read();
      // Signed out while the page was being read: nothing is kept.
      if (generation !== this.#generation) return;
      if (flow.already) {
        row.state = 'failed';
        row.message = ALREADY_HAVE;
        row.code = 'already_imported';
      } else if (flow.problem) {
        row.state = 'failed';
        row.message = flow.problem.message;
        row.code = flow.problem.code;
      } else if (flow.review) {
        if (await flow.keepAsDraft()) {
          // The list knows the new draft before its row says it is there (see `gone`).
          await drafts.load();
          if (generation !== this.#generation) return;
          row.state = 'ready';
          row.title = flow.review.name || row.title;
          row.draftId = flow.draftId;
          row.allMatched = readyToSave(flow);
        } else {
          void flow.dropPhoto();
          row.state = 'failed';
          row.message = flow.draftProblem ?? 'Couldn’t keep the draft. Try again.';
          row.code = flow.draftProblemCode ?? 'draft';
        }
      }
    } catch {
      row.state = 'failed';
      row.message = 'Couldn’t read that. Try again.';
      row.code = 'failed';
    }
  }

  /** Saving quick import's drafts is under way. */
  saving = $state(false);

  /** The draft this row was kept as isn't in Drafts any more: saved or discarded from Check, or
   *  deleted on another phone. Only said once the list has been fetched. */
  gone(row: LinkRow): boolean {
    return (
      row.state === 'ready' &&
      row.savedId === null &&
      (row.draftId === null ||
        (drafts.loaded && !drafts.drafts.some((draft) => draft.id === row.draftId)))
    );
  }

  /** The read links whose drafts can be saved as they are: every ingredient matched, and still
   *  there. */
  get ready(): LinkRow[] {
    return this.rows.filter(
      (row) => row.state === 'ready' && row.allMatched && row.savedId === null && !this.gone(row)
    );
  }

  /** Quick import (F216): save every draft whose ingredients all matched, one after another, with
   *  the Drafts list's own Save recipe. One toast says how many, with one Undo that takes each
   *  save back (the server's own Undo of an import: the recipe goes and its draft comes back to
   *  Drafts). A draft that can't be saved stays in Drafts with its sentence on its row. */
  async saveReady(): Promise<void> {
    if (this.saving || this.running) return;
    if (this.ready.length === 0) return;
    await drafts.load(); // what is still there now
    const rows = this.ready;
    if (rows.length === 0) return;
    this.saving = true;
    const generation = this.#generation;
    const done: { row: LinkRow; saved: Saved }[] = [];
    let failed = 0;
    try {
      for (const row of rows) {
        if (generation !== this.#generation) return;
        const result = await saveFromDraft(row.draftId!, { quiet: true });
        if (generation !== this.#generation) return;
        if ('problem' in result) {
          row.message = result.problem;
          // Already gone (saved or discarded elsewhere): not a failure, and no draft to open.
          if (result.gone) row.draftId = null;
          else failed += 1;
          continue;
        }
        row.savedId = result.recipeId;
        row.message = null;
        done.push({ row, saved: result.saved });
      }
    } finally {
      if (generation === this.#generation) this.saving = false;
    }
    void drafts.load();
    if (done.length === 0 && failed === 0) return; // every one was already gone
    if (done.length === 0) {
      toasts.show('Couldn’t save those recipes. They stay in Drafts.', { tone: 'problem' });
      return;
    }
    kitchen.changed();
    const words = savedWords(done.length);
    undoHistory.record({
      label:
        failed > 0 ? `${words}. ${failed} ${failed === 1 ? 'stays' : 'stay'} in Drafts` : words,
      needsServer: true,
      undo: async () => {
        let message: string | void = undefined;
        let undone = 0;
        // Each save is taken back on its own: one that can't be doesn't stop the rest.
        for (const { row, saved } of done) {
          try {
            const said = await serverUndo(saved.change.id)();
            if (said) message = said;
            row.savedId = null;
            undone += 1;
          } catch {
            // stays saved; counted below
          }
        }
        await drafts.load();
        return undone === done.length ? message : undidWords(undone, done.length);
      }
    });
  }

  clear(): void {
    if (!this.running) this.rows = [];
  }

  /** The session ended (sign-out): stop reading and forget the list. */
  forget(): void {
    this.#generation += 1;
    this.running = false;
    this.rows = [];
    this.leftOut = 0;
    this.room = null;
  }
}

export const importLinks = new ImportLinks();
forgetWhenSessionEnds(() => importLinks.forget());
forgetOnWipe(() => importLinks.forget());
