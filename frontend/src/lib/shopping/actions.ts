// Every Shopping write goes through ONE function, sendAction(action). An action is shaped as
// in docs/dev/sync-protocol.md section 4.2. In PR 6 sendAction becomes the offline queue;
// until then it sends each action at once.
//
// The server side: PR 2's one-at-a-time list requests exist now. Anything they don't cover
// (tick, untick, put_away, different_pack, answer_double_tick, dismiss_note, and Undo by
// action ID) is sent to POST /shopping/actions as a batch of one (section 4.1), which PR 3
// builds. Until PR 3 is merged those fail with a plain "couldn't save".

import { api, ApiError } from '$lib/api';
import { newChangeId } from '$lib/changeId';
import type { AmountIn, Change } from '$lib/client/types';
import { session } from '$lib/session.svelte';
import type { ShopFood } from './types';

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
      food_id: number;
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
  change?: Change | null;
}

/** What the screen lets sendAction look up. */
export interface SendContext {
  food(id: number): ShopFood | undefined;
  /** The ingredient an item is for (0 if unknown). */
  foodOfItem(itemId: string): number;
  cursor(): number;
}

let context: SendContext = {
  food: () => undefined,
  foodOfItem: () => 0,
  cursor: () => 0
};

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

const DEVICE_KEY = 'mealwright.device-id';

/** A random ID kept on this device (sync-protocol 3.8). */
export function deviceId(): string {
  try {
    const stored = localStorage.getItem(DEVICE_KEY);
    if (stored) return stored;
    const made = newChangeId();
    localStorage.setItem(DEVICE_KEY, made);
    return made;
  } catch {
    return (memoryDevice ??= newChangeId());
  }
}
let memoryDevice: string | null = null;

// --- Sending -------------------------------------------------------------------------------------

/** The server change that an action made, for Undo through PR 2's requests. */
const changeOf = new Map<string, number>();

/** The base-unit name the one-at-a-time requests expect. */
function baseUnit(food: ShopFood | undefined): string {
  return food?.counted_as === 'volume' ? 'ml' : food?.counted_as === 'count' ? 'count' : 'g';
}

/** An action's base-unit amount in the shape PR 2's requests take. */
export function wireAmount(
  foodId: number,
  amount: number,
  sizeId: number | null | undefined
): AmountIn {
  const food = context.food(foodId);
  const size = sizeId ? food?.sizes?.find((s) => s.id === sizeId) : undefined;
  if (size && size.amount > 0) return { amount: amount / size.amount, size_id: size.id };
  return { amount, unit: baseUnit(food) };
}

interface ItemWrite {
  item: { id: string } | null;
  merged: boolean;
  change: Change | null;
}

function remember(id: string, change: Change | null | undefined): void {
  if (change) changeOf.set(id, change.id);
}

/** Send one action. Resolves with what the server said; throws ApiError if it can't be sent. */
export async function sendAction(action: Action): Promise<ActionResult> {
  const key = { idempotencyKey: action.id };
  switch (action.kind) {
    case 'create_list': {
      const r = await api<{ change: Change | null }>(
        'POST',
        '/shopping/lists',
        { id: action.list_id, name: action.name },
        key
      );
      remember(action.id, r.change);
      return { status: 'applied', change: r.change };
    }
    case 'rename_list': {
      const r = await api<{ change: Change | null }>(
        'PATCH',
        `/shopping/lists/${action.list_id}`,
        { name: action.name },
        key
      );
      remember(action.id, r.change);
      return { status: r.change ? 'applied' : 'ignored', reason: 'no_change', change: r.change };
    }
    case 'remove_list': {
      const r = await api<{ change: Change | null }>(
        'DELETE',
        `/shopping/lists/${action.list_id}`,
        undefined,
        key
      );
      remember(action.id, r.change);
      return { status: 'applied', change: r.change };
    }
    case 'add': {
      const body: Record<string, unknown> = { id: action.item_id, food_id: action.food_id };
      if (action.amount) body.amount = wireAmount(action.food_id, action.amount, action.size_id);
      if (action.shop_id !== undefined) body.shop_id = action.shop_id;
      const r = await api<ItemWrite>('POST', `/shopping/lists/${action.list_id}/items`, body, key);
      remember(action.id, r.change);
      return {
        status: r.merged ? 'merged' : 'applied',
        item_id: r.item?.id ?? action.item_id,
        change: r.change
      };
    }
    case 'set_amount': {
      const foodId = context.foodOfItem(action.item_id);
      const r = await api<ItemWrite>(
        'PATCH',
        `/shopping/items/${action.item_id}`,
        { amount: wireAmount(foodId, action.amount, action.size_id) },
        key
      );
      remember(action.id, r.change);
      return { status: 'applied', change: r.change };
    }
    case 'delete': {
      const r = await api<ItemWrite>('DELETE', `/shopping/items/${action.item_id}`, undefined, key);
      remember(action.id, r.change);
      return { status: r.change ? 'applied' : 'ignored', reason: 'deleted', change: r.change };
    }
    case 'clear_ticked': {
      const r = await api<{ change: Change | null }>(
        'POST',
        `/shopping/lists/${action.list_id}/clear-ticked`,
        { item_ids: action.item_ids },
        key
      );
      remember(action.id, r.change);
      return { status: r.change ? 'applied' : 'ignored', change: r.change };
    }
    case 'undo': {
      const changeId = changeOf.get(action.undoes);
      if (changeId !== undefined) {
        const r = await api<{ result: string; message: string; change: Change }>(
          'POST',
          `/changes/${changeId}/undo`,
          undefined,
          key
        );
        return {
          status: 'applied',
          message: r.result === 'done' ? null : r.message,
          change: r.change
        };
      }
      return sendBatch(action);
    }
    default:
      return sendBatch(action);
  }
}

interface BatchAnswer {
  results?: (ActionResult & { id: string })[];
}

/** POST /shopping/actions with one action (sync-protocol 4.1). Built by PR 3. */
async function sendBatch(action: Action): Promise<ActionResult> {
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
  remember(action.id, result.change);
  return result;
}
