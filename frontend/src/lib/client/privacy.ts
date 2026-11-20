// Settings › Outside connections (backend api/v1/privacy.py): the switches for outside connections and
// "Your own network". Everyone in the household can read them; only an admin can change them.

import { api } from '#lib/api.js';
import { newChangeId } from '#lib/changeId.js';
import type { Change } from './types';

/** The switches that do something in this version. */
export type SwitchName = 'recipe_import' | 'recipe_photos' | 'single_sign_on' | 'update_check';

export interface PrivacySwitches {
  switches: { connection: SwitchName; on: boolean }[];
  /** False for a member: they see the switches and can't change them. */
  can_change: boolean;
  /** After a PUT that changed the switch: the change in Recent changes, for the toast's Undo
   * (D4, BE5). Null when it was already as asked, and on a GET. */
  change?: Change | null;
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
  /** After a POST: the change in Recent changes, for the toast's Undo (D4, BE5). */
  change?: Change | null;
}

export interface OwnNetworkList {
  entries: OwnNetworkEntry[];
  /** The most entries the list holds. */
  limit: number;
  can_change: boolean;
}

export const getSwitches = () => api<PrivacySwitches>('GET', '/privacy/switches');

export const putSwitch = (connection: SwitchName, on: boolean) =>
  api<PrivacySwitches>(
    'PUT',
    `/privacy/switches/${connection}`,
    { on },
    { idempotencyKey: newChangeId() }
  );

export const getOwnNetwork = () => api<OwnNetworkList>('GET', '/privacy/own-network');

export const addEntry = (value: string) =>
  api<OwnNetworkEntry>(
    'POST',
    '/privacy/own-network',
    { value },
    { idempotencyKey: newChangeId() }
  );

/** Taking an entry off always answers this (200): `passwords_back_on` with a `notice` to show
 * when password sign-in came back on, otherwise false and null. */
export interface RemovedAnswer {
  passwords_back_on: boolean;
  notice: string | null;
  /** The change in Recent changes, for the toast's Undo (D4, BE5). */
  change?: Change | null;
}

export const removeEntry = (id: number) =>
  api<RemovedAnswer>('DELETE', `/privacy/own-network/${id}`, undefined, {
    idempotencyKey: newChangeId()
  });
