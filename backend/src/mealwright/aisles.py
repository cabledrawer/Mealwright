"""The default aisles (spec section 6, "Offline shopping-list sync", Aisles).

Each food may have an aisle; shop headings on Shopping use these names, in this order until
a shop has its own order (0.8). A food with no aisle shows under Other.
"""

AISLES: tuple[tuple[str, str], ...] = (
    ("veg_fruit", "Veg & fruit"),
    ("meat_fish", "Meat & fish"),
    ("dairy", "Dairy"),
    ("bakery", "Bakery"),
    ("dry_goods", "Dry goods"),
    ("tins_jars", "Tins & jars"),
    ("spices", "Spices"),
    ("frozen", "Frozen"),
    ("drinks", "Drinks"),
    ("household", "Household"),
    ("other", "Other"),
)
AISLE_KEYS: tuple[str, ...] = tuple(key for key, _ in AISLES)
AISLE_LABELS: dict[str, str] = dict(AISLES)
DEFAULT_AISLE = "other"
