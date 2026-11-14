// Import from Mealie (0.9.5; backend api/v1/mealie.py, cabledrawer 13 Nov): the file is read on
// the server and shown before anything is added; "Bring in" runs on the server, so the screen
// can be left; one Undo for the whole import, for 7 days. Anyone in the household may import.

import { api } from '#lib/api.js';

export interface PreviewRecipe {
  /** Mealie's own id for it: send it in `leave_out` to leave it out. */
  key: string;
  name: string;
  /** Its first few Mealie tags. */
  tags: string[];
  photo: boolean;
  /** The household has it already (same name and source): left out. */
  already: boolean;
}

export interface MealiePreview {
  new: number;
  already: number;
  /** New recipes with a photo, and those photos' size in the file. */
  with_photo: number;
  photo_bytes: number;
  foods_matching: number;
  foods_new: number;
  /** Never brought in: meal_plans, shopping_lists, users, cookbooks → how many. */
  left_out: Record<string, number>;
  /** Every recipe in the file, in its order (empty once started). */
  recipes: PreviewRecipe[];
}

export type ResultState = 'saved' | 'draft' | 'saved_all' | 'already' | 'skipped';

export interface MealieResult {
  key: string;
  name: string;
  state: ResultState;
  recipe_id?: number | null;
  draft_id?: number | null;
  /** The first lines it couldn't read, as written. */
  unread: string[];
  unread_count: number;
}

export type ImportState = 'ready' | 'running' | 'done' | 'failed' | 'undone';

export interface MealieImport {
  id: number;
  state: ImportState;
  file_name: string;
  /** The file's size while the server keeps it. */
  file_bytes: number | null;
  started_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  /** While Undo works (7 days after it finished). */
  undo_until: string | null;
  photos: boolean;
  leave_out: string[];
  total: number;
  done: number;
  counts: { saved: number; drafts: number; already: number; skipped: number; new_foods: number };
  preview: MealiePreview;
  /** The last few brought in, newest last. */
  recent: MealieResult[];
  /** Recipes waiting in Drafts (the first 50). */
  to_check: MealieResult[];
}

export interface MealieUndone {
  recipes: number;
  kept: number;
  foods: number;
  drafts: number;
}

/** How long one upload may take (a big file over a slow home network). */
const UPLOAD_MS = 30 * 60_000;

/** Send the backup file; the answer is what's in it. Nothing is added yet. */
export const sendMealieFile = (file: File) =>
  api<MealieImport>(
    'POST',
    `/mealie-imports?file_name=${encodeURIComponent(file.name.slice(0, 500))}`,
    file.type ? file : new Blob([file], { type: 'application/zip' }),
    { timeoutMs: UPLOAD_MS }
  );

/** The import running now, or else the newest one. */
export const currentMealieImport = () =>
  api<{ current: MealieImport | null }>('GET', '/mealie-imports/current');

export const getMealieImport = (id: number) => api<MealieImport>('GET', `/mealie-imports/${id}`);

/** "Bring in": the server carries on by itself. */
export const startMealieImport = (id: number, leaveOut: string[], photos: boolean) =>
  api<MealieImport>('POST', `/mealie-imports/${id}/start`, { leave_out: leaveOut, photos });

/** Cancel on the preview: the file is deleted, nothing was added. */
export const cancelMealieImport = (id: number) => api<void>('DELETE', `/mealie-imports/${id}`);

export const undoMealieImport = (id: number) =>
  api<MealieUndone>('POST', `/mealie-imports/${id}/undo`, undefined, { timeoutMs: 120_000 });

/** Save every Mealie draft as it is: unread lines stay plain text, off the shopping list. */
export const saveAllMealieDrafts = () =>
  api<{ saved: number }>('POST', '/mealie-imports/drafts/save-all', undefined, {
    timeoutMs: 300_000
  });
