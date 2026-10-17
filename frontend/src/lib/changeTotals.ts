// The lines under a change in Recent changes: one per ingredient and place, from the
// server's `totals` (amounts already worded as sold): "Paneer: 0 g → 2 packs · 400 g",
// "Chana masala: Cupboard → Freezer".

import type { ChangeTotal } from './client/types';

export function totalWords(total: ChangeTotal): string {
  const parts: string[] = [];
  if (total.before.display !== total.after.display) {
    parts.push(`${total.before.display} → ${total.after.display}`);
  }
  const { place_before: from, place_after: to } = total;
  if (from && to && from.id !== to.id) parts.push(`${from.name} → ${to.name}`);
  return parts.length ? `${total.name}: ${parts.join(' · ')}` : total.name;
}
