// The default aisles and their order (spec section 6, "Aisles"). The same names the server
// uses (backend/src/mealwright/aisles.py). Headings on Shopping use these names, not the
// mockups' older "Fruit & veg" and "Rice & grains".

export const AISLES: readonly { key: string; name: string }[] = [
  { key: 'veg_fruit', name: 'Veg & fruit' },
  { key: 'meat_fish', name: 'Meat & fish' },
  { key: 'dairy', name: 'Dairy' },
  { key: 'bakery', name: 'Bakery' },
  { key: 'dry_goods', name: 'Dry goods' },
  { key: 'tins_jars', name: 'Tins & jars' },
  { key: 'spices', name: 'Spices' },
  { key: 'frozen', name: 'Frozen' },
  { key: 'drinks', name: 'Drinks' },
  { key: 'household', name: 'Household' },
  { key: 'other', name: 'Other' }
];

export const AISLE_NAMES: Record<string, string> = Object.fromEntries(
  AISLES.map((a) => [a.key, a.name])
);
