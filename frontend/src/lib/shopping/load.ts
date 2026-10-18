// Getting the shopping copy. The real source is GET /shopping/changes?since=0 (sync-protocol
// 5.5, built by PR 3), which carries everything. A server without it (PR 2 only) is read
// through its list views instead and fills in what it can: no ticks, notes, cards or people.

import { api, ApiError } from '$lib/api';
import type { AmountOut, Place, Ref } from '$lib/client/types';
import type { ListItem, ListRow, ShopFood, ShopRow, ShoppingCopy, Tick } from './types';

/** PR 3's answer, whole (sync-protocol 5.5). */
type ChangesAnswer = Omit<ShoppingCopy, 'counts'> & { reset?: boolean };

interface ViewItem {
  id: string;
  list_id: string;
  food: Ref;
  amount: AmountOut | null;
  shop: Ref | null;
  aisle: string;
  ticked_at: string | null;
  ticked_by: { login_id: number; name: string } | null;
  put_away_place: Ref | null;
  hand_edited: boolean;
  source: string;
  added_by: string;
}

interface ListViewAnswer {
  shopping_list: { id: string };
  shops: { aisles: { items: ViewItem[] }[]; in_trolley: ViewItem[] }[];
}

interface ListsAnswer {
  lists: { id: string; name: string; main: boolean; to_buy: number; ticked: number }[];
}

let haveChanges: boolean | null = null;

/** Whether the server has the "changes since" request (for tests: reset to ask again). */
export function forgetServerKind(): void {
  haveChanges = null;
}

export async function loadCopy(selected: string | null): Promise<ShoppingCopy> {
  if (haveChanges !== false) {
    try {
      const copy = await api<ChangesAnswer>('GET', '/shopping/changes?since=0');
      haveChanges = true;
      return {
        ...copy,
        lists: (copy.lists ?? []).filter((l) => !l.removed),
        notes: copy.notes ?? [],
        questions: copy.questions ?? []
      };
    } catch (error) {
      if (!(error instanceof ApiError) || (error.status !== 404 && error.status !== 405)) {
        throw error;
      }
      haveChanges = false;
    }
  }
  return loadFromViews(selected);
}

function tickOf(item: ViewItem): Tick[] {
  if (!item.ticked_at || !item.ticked_by) return [];
  return [
    {
      id: `view-${item.id}`,
      by: item.ticked_by,
      at: item.ticked_at,
      place_id: item.put_away_place?.id ?? null,
      bought: null,
      standing: true
    }
  ];
}

async function loadFromViews(selected: string | null): Promise<ShoppingCopy> {
  const [listsAnswer, shops, places] = await Promise.all([
    api<ListsAnswer>('GET', '/shopping/lists'),
    api<Ref[]>('GET', '/shops'),
    api<Place[]>('GET', '/places')
  ]);
  const lists: ListRow[] = listsAnswer.lists.map((l, position) => ({
    id: l.id,
    name: l.name,
    main: l.main,
    position,
    removed: false
  }));
  const counts = Object.fromEntries(
    listsAnswer.lists.map((l) => [l.id, { to_buy: l.to_buy, ticked: l.ticked }])
  );
  const open = lists.find((l) => l.id === selected) ?? lists.find((l) => l.main) ?? lists[0];
  const items: ListItem[] = [];
  const foods = new Map<number, ShopFood>();
  if (open) {
    const view = await api<ListViewAnswer>('GET', `/shopping/lists/${open.id}`);
    for (const group of view.shops) {
      for (const item of [...group.aisles.flatMap((a) => a.items), ...group.in_trolley]) {
        if (!foods.has(item.food.id)) {
          foods.set(item.food.id, {
            id: item.food.id,
            name: item.food.name,
            other_names: [],
            counted_as:
              item.amount?.unit === 'ml'
                ? 'volume'
                : item.amount?.unit === 'count'
                  ? 'count'
                  : 'weight',
            staple: false,
            aisle: item.aisle,
            shop_id: null,
            place_id: null,
            sizes: null
          });
        }
        items.push({
          id: item.id,
          list_id: item.list_id,
          food_id: item.food.id,
          shop_id: item.shop?.id ?? null,
          amount: item.amount?.amount ?? null,
          size_id: item.amount?.as_sold?.size.id ?? null,
          display: item.amount?.short ?? null,
          source: item.source,
          hand_edited: item.hand_edited,
          put_away_place_id: item.put_away_place?.id ?? null,
          ticks: tickOf(item),
          added_by: null,
          deleted: false,
          merged_into_id: null
        });
      }
    }
  }
  const shopRows: ShopRow[] = shops.map((s, position) => ({
    id: s.id,
    name: s.name,
    position,
    aisle_order: null
  }));
  return {
    cursor: 0,
    lists,
    items,
    notes: [],
    questions: [],
    foods: [...foods.values()],
    shops: shopRows,
    places: places.map((p, position) => ({ ...p, position })),
    people: null,
    counts
  };
}
