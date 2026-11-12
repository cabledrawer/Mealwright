// The words and anchors of Settings → Privacy (docs/dev/words.md section 18). Every
// sentence not marked as cabledrawer's is "proposed, for cabledrawer" (0.5 PR 4).

import type { OwnNetworkEntry, SwitchName } from './client/privacy';
import { dayMonthWords } from './dates';
import { downLine } from './downWords';

/**
 * Where the section "Outside connections" starts: /settings/privacy#outside-connections.
 * The import screen's "Photo not downloaded" and "switched off" links land here.
 */
export const OUTSIDE_CONNECTIONS_ANCHOR = 'outside-connections';
/** Where "Your own network" starts: /settings/privacy#your-own-network. */
export const OWN_NETWORK_ANCHOR = 'your-own-network';

export const SWITCH_WORDS: Record<SwitchName, { label: string; detail: string }> = {
  recipe_import: {
    label: 'Recipe import from links',
    detail: 'Visits a website only when you paste its link'
  },
  recipe_photos: {
    label: 'Download recipe photos',
    detail: 'The recipe’s main photo, kept on this server. Off: imports come without a photo.'
  },
  // Mockup Dark-Privacy09-Phone (X1). Also what Check now in About needs (proposed, for cabledrawer).
  update_check: {
    label: 'Check for updates daily',
    detail: 'Asks GitHub’s public release list once a day. Sends nothing about you or this server'
  }
};

/** The order they're shown in. */
export const SWITCH_ORDER: readonly SwitchName[] = [
  'recipe_import',
  'recipe_photos',
  'update_check'
];

/** Why a switch or the list can't be changed just now. */
export type Locked = 'member' | 'offline' | null;

export const MEMBER_NOTE =
  'Only an admin can change these, because they decide what Mealwright may contact.';
/** Offline, or the server not answering: the words say which (downWords.ts, cabledrawer 30 Oct). */
export const offlineNote = (device: boolean): string =>
  downLine(
    device,
    (b) => `This is as it was when you last looked, and it can’t be changed ${b.until}.`
  );

export const LEAD = 'Nothing leaves this server unless you switch it on.';
export const LEARN_IMPORT_LIMITS =
  'Imports: pages up to 5 MB, web pages only, up to 5 redirects, each address checked again.';

export const NETWORK_INTRO =
  'Links to your own network (your router, other home servers, this server) are blocked, to keep them safe. Add the ones Mealwright may visit, like a home wiki.';
export const NETWORK_EMPTY = 'Nothing added yet. Every address on your own network is blocked.';
export const NETWORK_HELP = 'Each entry is a name, one address, or a range like 192.168.1.0/24.';
/** cabledrawer 23 Oct, question 26: link-local is named too, as the refusal sentence names it. */
export const NETWORK_BLOCKED =
  'this server itself (localhost), link-local and cloud “metadata” addresses.';

/** "A name · added by Tess, 22 Oct"; "A range · 256 addresses · added by Tess, 22 Oct". */
export function entryWords(entry: OwnNetworkEntry): string {
  const kind =
    entry.kind === 'name' ? 'A name' : entry.kind === 'address' ? 'An address' : 'A range';
  const parts = [kind];
  if (entry.addresses !== null) {
    parts.push(`${entry.addresses.toLocaleString('en-GB')} addresses`);
  }
  const day = dayMonthWords(entry.added_on);
  parts.push(entry.added_by ? `added by ${entry.added_by}, ${day}` : `added ${day}`);
  return parts.join(' · ');
}
