// The Shopping actions, shaped as in docs/dev/sync-protocol.md section 4.2. Every Shopping
// write is one of these, and goes through ONE function, sendAction(action) in sync.svelte.ts:
// into the offline queue first, then to POST /shopping/actions in batches (section 11.3).

import { newChangeId } from '$lib/changeId';
import { deviceId } from '$lib/offline/device';
import type { Change } from '$lib/client/types';
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
  /** Move an unticked line to a shop (null = Any shop) on a list (sync protocol 4.2, M-1 to M-8). */
  | { kind: 'move'; item_id: string; list_id: string; shop_id: number | null }
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

/** What makeAction needs to know: the counter number the copy is at. */
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
