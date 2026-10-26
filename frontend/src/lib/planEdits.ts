// What the plan looks like straight after a change, before the server has answered
// (optimistic updates, UX principle 8). The server's answer is fetched next and replaces it,
// so these only have to be right for what a person sees in the meantime. Each takes the
// plan and returns a new one; copies get ids below zero until the server's plan arrives.

import type { DropMode, Plan, PlanItem, PlanMeal } from './client/plan';

let temp = 0;
const tempId = () => --temp;

const clone = (plan: Plan): Plan => structuredClone(plan);

const fresh = (plan: Plan, day: string, slotId: number): PlanMeal => {
  const meal: PlanMeal = {
    id: tempId(),
    date: day,
    slot_id: slotId,
    status: 'planned',
    items: [],
    kcal: null
  };
  plan.meals.push(meal);
  return meal;
};

const total = (meal: PlanMeal): number | null => {
  const known = meal.items.filter((i) => i.recipe?.kcal != null);
  return known.length ? known.reduce((sum, i) => sum + (i.recipe?.kcal ?? 0), 0) : null;
};

/** The meal at a day and slot, made when it isn't there. */
function target(plan: Plan, day: string, slotId: number): PlanMeal {
  return plan.meals.find((m) => m.date === day && m.slot_id === slotId) ?? fresh(plan, day, slotId);
}

function tidy(plan: Plan): Plan {
  plan.meals = plan.meals.filter((m) => m.items.length > 0);
  for (const meal of plan.meals) {
    meal.items.forEach((item, i) => (item.position = i));
    meal.kcal = total(meal);
  }
  return plan;
}

export function withoutItem(plan: Plan, itemId: number): Plan {
  const next = clone(plan);
  for (const meal of next.meals) meal.items = meal.items.filter((i) => i.id !== itemId);
  return tidy(next);
}

export function withoutMeal(plan: Plan, mealId: number): Plan {
  const next = clone(plan);
  next.meals = next.meals.filter((m) => m.id !== mealId);
  return tidy(next);
}

const copyOf = (item: PlanItem): PlanItem => ({ ...item, id: tempId() });

export function withMealDropped(
  plan: Plan,
  mealId: number,
  day: string,
  slotId: number,
  mode: DropMode
): Plan {
  const next = clone(plan);
  const meal = next.meals.find((m) => m.id === mealId);
  if (!meal || (meal.date === day && meal.slot_id === slotId)) return plan;
  const items = mode === 'move' ? meal.items : meal.items.filter((i) => i.kind !== 'tub');
  if (!items.length) return plan;
  const existing = next.meals.find((m) => m.date === day && m.slot_id === slotId);
  if (mode === 'move' && !existing) {
    meal.date = day;
    meal.slot_id = slotId;
    return tidy(next);
  }
  const into = existing ?? fresh(next, day, slotId);
  if (mode === 'move') {
    into.items.push(...meal.items);
    next.meals = next.meals.filter((m) => m.id !== meal.id);
  } else {
    into.items.push(...items.map(copyOf));
  }
  return tidy(next);
}

export function withItemDropped(
  plan: Plan,
  itemId: number,
  day: string,
  slotId: number,
  mode: DropMode
): Plan {
  const next = clone(plan);
  const from = next.meals.find((m) => m.items.some((i) => i.id === itemId));
  const item = from?.items.find((i) => i.id === itemId);
  if (!from || !item || (from.date === day && from.slot_id === slotId)) return plan;
  if (mode !== 'move' && item.kind === 'tub') return plan;
  const into = target(next, day, slotId);
  if (mode === 'move') {
    from.items = from.items.filter((i) => i.id !== itemId);
    into.items.push(item);
  } else {
    into.items.push(copyOf(item));
  }
  return tidy(next);
}
