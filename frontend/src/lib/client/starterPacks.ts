// Starter ingredient packs (contract 6.2, "Starter ingredient packs"; 0.8 R4).

import { api } from '#lib/api.js';
import type { Change } from './types';

export interface StarterItem {
  key: string;
  name: string;
  /** The household has it by this name or another name: it is skipped. */
  already_have: boolean;
  /** What the household calls it, when that isn't this name. */
  have_as: string | null;
  /** Added as a staple ("Don't count it"): the Household pack. */
  staple: boolean;
}

export interface StarterPack {
  id: string;
  name: string;
  items: StarterItem[];
  already_have: number;
}

export interface Added {
  added: number;
  skipped: number;
  change: Change;
}

export const getStarterPacks = () => api<{ packs: StarterPack[] }>('GET', '/starter-packs');

export const addStarterPack = (id: string, keys: string[], idempotencyKey: string) =>
  api<Added>('POST', `/starter-packs/${id}/add`, { keys }, { idempotencyKey });
