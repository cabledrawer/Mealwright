// Settings → Your data (backend api/v1/your_data.py; spec section 7): backups, the export and
// Delete everything. Everyone in the household can read the backups' settings; only an admin
// changes them, backs up now, exports or deletes everything (the server refuses anyone else).

import { api } from '#lib/api.js';

export type BackupEvery = 'daily' | 'twice-daily' | 'weekly';

export interface Backups {
  every: BackupEvery;
  /** How many of its own backups are kept, 1 to 30. */
  keep: number;
  /** The newest backup: when (ISO, UTC) and how big, in bytes. Null when there's none yet. */
  last: { at: string; size: number } | null;
  /** Why the last try failed, in plain words; null when backups work. */
  problem: string | null;
  problem_at: string | null;
  count: number;
  folder: string;
}

/** The most backups an admin can keep. */
export const KEEP_MOST = 30;

export const getBackups = () => api<Backups>('GET', '/backups');

export const changeBackups = (change: { every?: BackupEvery; keep?: number }) =>
  api<Backups>('PATCH', '/backups', change);

/** "Back up now". A backup that fails comes back as the settings with `problem` set. */
export const backUpNow = () => api<Backups>('POST', '/backups', undefined, { timeoutMs: 120_000 });

/** Where "Export" downloads the file from (a plain link: the browser saves what it streams). */
export const EXPORT_PATH = '/api/v1/export';

/** Delete everything: the typed words and the admin's own password. */
export const deleteEverything = (words: string, password: string) =>
  api<void>('POST', '/delete-everything', { words, password }, { timeoutMs: 120_000 });
