// Settings → Privacy (backend api/v1/privacy.py): the switches for outside connections and
// "Your own network". Everyone in the household can read them; only an admin can change them.

import { api } from '#lib/api.js';

/** The switches that do something in this version. */
export type SwitchName = 'recipe_import' | 'recipe_photos' | 'update_check';

export interface PrivacySwitches {
  switches: { connection: SwitchName; on: boolean }[];
  /** False for a member: they see the switches and can't change them. */
  can_change: boolean;
}

export interface OwnNetworkEntry {
  id: number;
  kind: 'name' | 'address' | 'range';
  /** The text as the server keeps it: a lower-case name, an address, or a range. */
  value: string;
  /** How many addresses an IPv4 range holds; null for anything else. */
  addresses: number | null;
  added_by: string;
  /** The day it was added, in the household's time zone ("2026-10-22"). */
  added_on: string;
}

export interface OwnNetworkList {
  entries: OwnNetworkEntry[];
  /** The most entries the list holds. */
  limit: number;
  can_change: boolean;
}

export const getSwitches = () => api<PrivacySwitches>('GET', '/privacy/switches');

export const putSwitch = (connection: SwitchName, on: boolean) =>
  api<PrivacySwitches>('PUT', `/privacy/switches/${connection}`, { on });

export const getOwnNetwork = () => api<OwnNetworkList>('GET', '/privacy/own-network');

export const addEntry = (value: string) =>
  api<OwnNetworkEntry>('POST', '/privacy/own-network', { value });

export const removeEntry = (id: number) => api<void>('DELETE', `/privacy/own-network/${id}`);
