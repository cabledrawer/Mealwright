// Several links at once (cabledrawer 31 Oct, F110; spec "Decided for 0.8.0"): each link is read on
// its own, one after another (never together), and kept as its own draft to check later. A link
// that fails shows its own sentence and the rest carry on. Each read is the ordinary single-link
// import, so the same Privacy switch, the outbound gate and server-only fetching apply.
//
// The state lives here, not in the page, so leaving the screen inside the app doesn't stop the
// reading (the screen says "You can leave this screen").

import { SvelteURL } from 'svelte/reactivity';
import { forgetWhenSessionEnds } from './api';
import { drafts } from './drafts.svelte';
import { ImportFlow } from './import.svelte';
import { forgetOnWipe } from './offline/wipeHooks';

/** Words on the screen (mockup Dark-ImportLinks08-Phone; "Ready to check" and "in Drafts" are
 *  agreed, the rest is proposed, for cabledrawer). */
export const READY_TO_CHECK = '✓ Ready to check';
export const READING = 'Reading…';
export const WAITING = 'Waiting';
export const IN_DRAFTS = 'in Drafts';
export const LINKS_HELP =
  'Each recipe goes to Drafts to check and save later. If one link can’t be read, the rest carry on. You can leave this screen.';
export const LINKS_SERVER_NOTE =
  'Only Mealwright’s server fetches these pages, and only because Recipe import is switched on in Settings.';
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
      const room = drafts.count === null ? null : Math.max(0, DRAFT_LIMIT - drafts.count);
      const allowed = Math.min(MOST_LINKS, room ?? MOST_LINKS);
      this.leftOut = Math.max(0, unique.length - allowed);
      this.room = room;
      this.rows = unique.slice(0, allowed).map((link) => ({
        link,
        ...parts(link),
        state: 'waiting' as const,
        message: null,
        code: null
      }));
      let stopped: string | null = null;
      for (const row of this.rows) {
        if (generation !== this.#generation) return;
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
          row.state = 'ready';
          row.title = flow.review.name || row.title;
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
