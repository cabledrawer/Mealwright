// Settings › Backups & your data (backend api/v1/your_data.py; spec section 7): backups, the export and
// Delete everything. Everyone in the household can read the backups' settings; only an admin
// changes them, backs up now, exports or deletes everything (the server refuses anyone else).

import { api, ApiError, cantReachWords, codeOf, detailOf, sessionEnded } from '#lib/api.js';

export type BackupEvery = 'daily' | 'twice_daily' | 'weekly';

export interface Backups {
  every: BackupEvery;
  /** How many of its own backups are kept, 1 to 30. */
  keep: number;
  /** Include the recipe photos in backups and the safety copy before an upgrade (D2, 0.9.5). */
  photos: boolean;
  /** What this household's recipe photos come to, in bytes. Null for a member. */
  photos_size: number | null;
  /** The database's own size, in bytes: about what a backup without photos comes to. Null for a member. */
  database_size: number | null;
  /**
   * The newest backup: when (ISO, UTC), how big in bytes (its photos counted when it has
   * them) and whether it holds the photos. Null when there's none yet.
   */
  last: { at: string; size: number; photos: boolean } | null;
  /** Why the last try failed, in plain words; null when backups work. */
  problem: string | null;
  problem_at: string | null;
  count: number;
  folder: string;
}

/** The most backups an admin can keep. */
export const KEEP_MOST = 30;

export const getBackups = () => api<Backups>('GET', '/your-data/backups');

export const changeBackups = (change: {
  every?: BackupEvery;
  keep?: number;
  photos?: boolean;
  /** R6: the admin's own password, needed when `keep` would delete backups (an admin who
   *  confirmed with single sign-on leaves it out). */
  password?: string;
}) => api<Backups>('PATCH', '/your-data/backups', change);

/** "Back up now". A backup that fails comes back as the settings with `problem` set. */
export const backUpNow = (password?: string) =>
  api<Backups>('POST', '/your-data/backups', password === undefined ? undefined : { password }, {
    timeoutMs: 120_000
  });

/** Where "Export" downloads the file from (a plain link: the browser saves what it streams). */
export const EXPORT_PATH = '/api/v1/your-data/export';

/** Delete everything: the typed words and the admin's own password, or, for an admin who
 *  confirmed with single sign-on (D3), the words only. */
export const deleteEverything = (words: string, password?: string) =>
  api<void>(
    'POST',
    '/your-data/delete-everything',
    password === undefined ? { words } : { words, password },
    { timeoutMs: 120_000 }
  );

/** How this admin confirms Delete everything (D3): their password, or a fresh single sign-on
 *  sign-in (`confirmed`: this session did, in the last 10 minutes). */
export interface HowToConfirm {
  confirm_with: 'password' | 'single_sign_on';
  confirmed: boolean;
}

export const getHowToConfirm = (what?: { action: 'keep' | 'backup_now'; keep?: number }) =>
  api<HowToConfirm>(
    'GET',
    what
      ? `/your-data/delete-everything?action=${what.action}${what.keep === undefined ? '' : `&keep=${what.keep}`}`
      : '/your-data/delete-everything'
  );

/**
 * Export with a password: the file comes back encrypted (docs/export-format.md). The password
 * goes in the request body only, and is kept nowhere. The file is saved by the browser as the
 * download it is; it is held in memory until then (a household's recipes and photos, so it can be large; a
 * form that streams it to disk instead is a later choice). `leave` stops the download, as when
 * the person goes to another page.
 */
export async function exportWithPassword(password: string, leave?: AbortSignal): Promise<void> {
  // One controller that both leaving the page and the time limit stop (no AbortSignal.any:
  // older browsers lack it, and every encrypted export would fail there).
  const stop = new AbortController();
  const onLeave = () => stop.abort();
  if (leave?.aborted) return;
  leave?.addEventListener('abort', onLeave);
  const timer = setTimeout(onLeave, 600_000);
  try {
    await download(password, stop.signal);
  } finally {
    clearTimeout(timer);
    leave?.removeEventListener('abort', onLeave);
  }
}

async function download(password: string, signal: AbortSignal): Promise<void> {
  let response: Response;
  try {
    response = await fetch(EXPORT_PATH, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ password }),
      signal
    });
  } catch {
    throw new ApiError(0, cantReachWords());
  }
  if (!response.ok) {
    if (response.status === 401) sessionEnded();
    let data: unknown = null;
    try {
      data = await response.json();
    } catch {
      // not JSON: an error page
    }
    throw new ApiError(response.status, detailOf(data), codeOf(data), data);
  }
  let blob: Blob;
  try {
    blob = await response.blob();
  } catch {
    throw new ApiError(0, cantReachWords());
  }
  if (signal.aborted) return; // left the page (or ran out of time) meanwhile: nothing is saved
  const named = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') ?? '');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = named?.[1] ?? 'mealwright-export.zip.mwenc';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
}
