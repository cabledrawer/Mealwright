// Every Shopping write goes through ONE function, sendAction(action). An action is shaped as
// in docs/dev/sync-protocol.md section 4.2. In PR 6 sendAction becomes the offline queue;
// until then it sends each action at once, as a batch of one (section 4.1) to
// POST /shopping/actions, and hands the changes in the answer to the screen.

import { api, ApiError } from '$lib/api';
import { newChangeId } from '$lib/changeId';
import { deviceId } from '$lib/offline/device';
import type { Change } from '$lib/client/types';
import { session } from '$lib/session.svelte';
import type { ChangesAnswer } from './types';

export interface ActionBase {
  /** Phone-made ID. Sent again, it is never applied twice. */
  id: string;
  made_at: string;
  /** The counter number this device had seen when it made the action. */
  seen: number;
}

export type ActionFields =
  | { kind: 'create_list'; list_id: string; name: string }
  | { kind: 'rename_list'; list_id: string; name: string }
  | { kind: 'remove_list'; list_id: string }
  | {
      kind: 'add';
      list_id: string;
      item_id: string;
      /** An existing ingredient, or: */
      food_id?: number;
      /** a brand-new one from the add box, with the packet sizes chosen (sync-protocol 4.4). */
      new_food?: {
        name: string;
        counted_as: 'weight' | 'volume' | 'count';
        staple: boolean;
        sizes?: { name: string; amount: number }[];
      };
      amount?: number | null;
      size_id?: number | null;
      shop_id?: number | null;
    }
  | { kind: 'set_amount'; item_id: string; amount: number; size_id?: number | null }
  | { kind: 'delete'; item_id: string }
  | { kind: 'tick'; item_id: string }
  | { kind: 'untick'; item_id: string; tick_ids: string[] }
  | { kind: 'put_away'; item_id: string; place_id: number; tick_ids: string[]; use_by?: string }
  | {
      kind: 'different_pack';
      item_id: string;
      tick_id: string;
      count: number;
      pack: number;
      size_id?: number | null;
    }
  | { kind: 'clear_ticked'; list_id: string; item_ids: string[] }
  | { kind: 'answer_double_tick'; question_id: number; answer: 'two' | 'one' }
  | { kind: 'dismiss_note'; note_id: number }
  | { kind: 'undo'; undoes: string };

export type Action = ActionBase & ActionFields;

/** What the server said about one action (section 5.4). */
export interface ActionResult {
  status: 'applied' | 'merged' | 'ignored' | 'refused';
  reason?: string | null;
  message?: string | null;
  /** The item an add joined or made. */
  item_id?: string | null;
  /** The ingredient an add with `new_food` used or made. */
  food_id?: number | null;
  change?: Change | null;
  /** The changes since the batch's `since`, read after the action (5.5). */
  changes?: ChangesAnswer;
}

/** What the screen lets sendAction know: the counter number its copy is at. */
export interface SendContext {
  cursor(): number;
}

let context: SendContext = { cursor: () => 0 };

export function setSendContext(next: SendContext): void {
  context = next;
}

/** Fill in the envelope fields of an action. */
export function makeAction<F extends ActionFields>(fields: F, id: string = newChangeId()) {
  return {
    id,
    made_at: new Date().toISOString(),
    seen: context.cursor(),
    ...fields
  } as ActionBase & F;
}

// --- This device ---------------------------------------------------------------------------------

/** A random ID kept on this device (sync-protocol 11.8), in the phone database. */
export { deviceId };

// --- Sending -------------------------------------------------------------------------------------

interface BatchAnswer {
  results?: (ActionResult & { id: string })[];
  changes?: ChangesAnswer;
}

/** Send one action. Resolves with what the server said; throws ApiError if it can't be sent. */
export async function sendAction(action: Action): Promise<ActionResult> {
  const answer = await api<BatchAnswer>('POST', '/shopping/actions', {
    protocol: 1,
    device_id: deviceId(),
    login_id: session.me?.id ?? 0,
    since: context.cursor(),
    sent_at: new Date().toISOString(),
    actions: [action]
  });
  const result = answer.results?.find((r) => r.id === action.id) ?? answer.results?.[0];
  if (!result) throw new ApiError(500, 'Couldn’t save — try again');
  if (result.status === 'refused') {
    throw new ApiError(
      422,
      result.message || 'That change couldn’t be saved.',
      result.reason ?? null
    );
  }
  return { ...result, changes: answer.changes };
}
