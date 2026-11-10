// Several links at once (cabledrawer 31 Oct, F110; spec "Decided for 0.8.0"): each link is read on
// its own, one after another (never together), and kept as its own draft to check later. A link
// that fails shows its own sentence and the rest carry on. Each read is the ordinary single-link
// import, so the same Privacy switch, the outbound gate and server-only fetching apply.
//
// The state lives here, not in the page, so leaving the screen inside the app doesn't stop the
// reading (the screen says "You can leave this screen").

import { ImportFlow } from './import.svelte';

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

  /** Read the links one after another, each into its own draft. Never throws. */
  async run(links: string[]): Promise<void> {
    if (this.running) return;
    const unique = links.filter((link, at) => links.indexOf(link) === at);
    this.rows = unique.map((link) => ({
      link,
      ...parts(link),
      state: 'waiting' as const,
      message: null,
      code: null
    }));
    this.running = true;
    try {
      for (const row of this.rows) await this.#one(row);
    } finally {
      this.running = false;
    }
  }

  async #one(row: LinkRow): Promise<void> {
    row.state = 'reading';
    const flow = new ImportFlow();
    flow.text = row.link;
    try {
      await flow.read();
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
          row.code = 'draft';
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
}

export const importLinks = new ImportLinks();
