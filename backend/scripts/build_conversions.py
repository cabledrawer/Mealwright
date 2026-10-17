# ruff: noqa: E501  (the CHOICES table reads best one food per line)
"""Build Mealwright's bundled food-conversion table from USDA FoodData Central.

Source: USDA FoodData Central, SR Legacy (April 2018), CSV download
`FoodData_Central_sr_legacy_food_csv_2018-04.zip`, public domain under CC0 1.0. See
docs/dev/conversions.md for where to download it and how the table is checked.

Every number in the output comes from the USDA file. This script only chooses which USDA
food and which of its "household measure" portions to use (the CHOICES list below), and
divides: weight per millilitre = portion grams / portion volume; weight of one item =
portion grams / portion count. Nothing is typed in or estimated by hand. If a chosen food
or portion isn't in the file exactly as written, the build stops.

Run it with the stdlib only, against the downloaded zip (untrusted data: it is only
read, never unpacked or run):

    python -I scripts/build_conversions.py /path/to/FoodData_Central_sr_legacy_food_csv_2018-04.zip

It writes src/mealwright/data/food-conversions.csv, including each food's starting aisle:
the USDA food category of the chosen food, mapped to one of Mealwright's aisles by
CATEGORY_AISLE below, unless AISLE_OVERRIDES names the ingredient (for the few where the
USDA category isn't where a shop keeps it: dried beans vs tinned, sugar vs honey).
"""

import csv
import io
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple

FOLDER = "FoodData_Central_sr_legacy_food_csv_2018-04/"
OUT = (
    Path(__file__).resolve().parent.parent / "src" / "mealwright" / "data" / "food-conversions.csv"
)

# USDA household measures are US customary (SR Legacy documentation): 1 cup = 8 US fl oz.
US_FL_OZ_ML = 29.5735295625
VOLUME_ML = {
    "cup": 8 * US_FL_OZ_ML,
    "tbsp": US_FL_OZ_ML / 2,
    "tablespoon": US_FL_OZ_ML / 2,
    "tsp": US_FL_OZ_ML / 6,
    "teaspoon": US_FL_OZ_ML / 6,
    "fl oz": US_FL_OZ_ML,
}


# Mealwright's aisles (spec section 6, "Offline shopping-list sync"). The same keys as
# mealwright.aisles.AISLES; a test checks they match.
AISLE_KEYS = (
    "veg_fruit", "meat_fish", "dairy", "bakery", "dry_goods", "tins_jars",
    "spices", "frozen", "drinks", "household", "other",
)  # fmt: skip

# Every USDA SR Legacy food category -> an aisle. A category missing from this map stops the
# build, so nothing is silently left as Other.
CATEGORY_AISLE = {
    "Dairy and Egg Products": "dairy",
    "Spices and Herbs": "spices",
    "Baby Foods": "other",
    "Fats and Oils": "tins_jars",
    "Poultry Products": "meat_fish",
    "Soups, Sauces, and Gravies": "tins_jars",
    "Sausages and Luncheon Meats": "meat_fish",
    "Breakfast Cereals": "dry_goods",
    "Fruits and Fruit Juices": "veg_fruit",
    "Pork Products": "meat_fish",
    "Vegetables and Vegetable Products": "veg_fruit",
    "Nut and Seed Products": "dry_goods",
    "Beef Products": "meat_fish",
    "Beverages": "drinks",
    "Finfish and Shellfish Products": "meat_fish",
    "Legumes and Legume Products": "dry_goods",
    "Lamb, Veal, and Game Products": "meat_fish",
    "Baked Products": "bakery",
    "Sweets": "dry_goods",
    "Cereal Grains and Pasta": "dry_goods",
    "Fast Foods": "other",
    "Meals, Entrees, and Side Dishes": "other",
    "Snacks": "other",
    "American Indian/Alaska Native Foods": "other",
    "Restaurant Foods": "other",
}

# Where the USDA category isn't where a shop keeps it. Keyed by the Choice key.
AISLE_OVERRIDES = {
    # Baking supplies sit under "Baked Products", "Spices and Herbs" or "Sweets"
    "baking_powder": "dry_goods", "bicarbonate_of_soda": "dry_goods",
    "cream_of_tartar": "dry_goods", "dried_yeast": "dry_goods",
    "vanilla_extract": "dry_goods", "breadcrumbs": "dry_goods",
    # Jars and bottles
    "honey": "tins_jars", "maple_syrup": "tins_jars", "corn_syrup": "tins_jars",
    "molasses": "tins_jars", "jam": "tins_jars", "peanut_butter": "tins_jars",
    "soy_sauce": "tins_jars", "tamari": "tins_jars", "ketchup": "tins_jars",
    "mayonnaise": "tins_jars", "vinegar": "tins_jars", "cider_vinegar": "tins_jars",
    "red_wine_vinegar": "tins_jars", "balsamic_vinegar": "tins_jars",
    "lemon_juice": "tins_jars", "lime_juice": "tins_jars", "coconut_milk": "tins_jars",
    # Tinned and cooked (the USDA file lists them with the dried or fresh food)
    "tinned_chickpeas": "tins_jars", "tinned_tomatoes": "tins_jars",
    "tomato_puree": "tins_jars", "passata": "tins_jars",
    "cooked_rice": "dry_goods", "cooked_lentils": "tins_jars",
    # Frozen
    "frozen_spinach": "frozen", "frozen_peas": "frozen",
    # Dried or powdered things filed under fresh or dairy
    "raisins": "dry_goods", "sultanas": "dry_goods", "tamarind": "dry_goods",
    "sweetened_coconut": "dry_goods", "skimmed_milk_powder": "dry_goods",
    "whole_milk_powder": "dry_goods", "ghee": "tins_jars",
    # Chilled, and in the fruit and veg section
    "tofu": "veg_fruit",
    # Drinks section
    "instant_coffee": "drinks", "water": "drinks",
    # Cocoa and chocolate are baking
    "cocoa": "dry_goods", "chocolate_chips": "dry_goods",
}  # fmt: skip


def aisle_for(key: str, category: str) -> str:
    """The starting aisle for a bundled food: its override, else its USDA category's aisle."""
    if key in AISLE_OVERRIDES:
        return AISLE_OVERRIDES[key]
    try:
        return CATEGORY_AISLE[category]
    except KeyError:
        raise SystemExit(
            f"{key}: USDA category {category!r} has no aisle in CATEGORY_AISLE"
        ) from None


def check_aisle_tables() -> None:
    for aisle in [*CATEGORY_AISLE.values(), *AISLE_OVERRIDES.values()]:
        if aisle not in AISLE_KEYS:
            raise SystemExit(f"Not an aisle: {aisle!r}")


def check_overrides_known(choices: list[Choice]) -> None:
    unknown = set(AISLE_OVERRIDES) - {choice.key for choice in choices}
    if unknown:
        raise SystemExit(f"AISLE_OVERRIDES names foods that aren't in CHOICES: {sorted(unknown)}")


class Choice(NamedTuple):
    key: str
    fdc_id: str
    counted_as: str  # how the pantry usually counts it: weight, volume or count
    names: str  # names a household's food is matched by, "|"-separated, first is the main one
    volume: str | None  # USDA portion "amount|modifier" to take weight per ml from
    item: str | None  # USDA portion "amount|modifier" to take the weight of one item from


W, V, C = "weight", "volume", "count"

# fmt: off
CHOICES: list[Choice] = [
    # Flours, sugars and baking
    Choice("plain_flour", "168894", W, "plain flour|all-purpose flour|flour|maida", "1|cup", None),
    Choice("self_raising_flour", "168895", W, "self-raising flour|self-rising flour", "1|cup", None),
    Choice("bread_flour", "168896", W, "strong white flour|bread flour|strong flour", "1|cup", None),
    Choice("wholemeal_flour", "168893", W, "wholemeal flour|whole wheat flour|wholewheat flour|atta|chapati flour", "1|cup", None),
    Choice("cornflour", "169698", W, "cornflour|cornstarch|corn starch", "1|cup", None),
    Choice("semolina", "169715", W, "semolina|sooji|suji|rava", "1|cup", None),
    Choice("rice_flour", "169714", W, "rice flour", "1|cup", None),
    Choice("gram_flour", "174288", W, "gram flour|besan|chickpea flour", "1|cup", None),
    Choice("cornmeal", "168867", W, "cornmeal|polenta|maize meal", "1|cup", None),
    Choice("sugar", "169655", W, "sugar|granulated sugar|white sugar", "1|cup", None),
    Choice("brown_sugar", "168833", W, "brown sugar|soft brown sugar|light brown sugar|dark brown sugar", "1|cup packed", None),
    Choice("icing_sugar", "169656", W, "icing sugar|powdered sugar|confectioners sugar", "1|cup unsifted", None),
    Choice("raw_sugar", "170674", W, "demerara sugar|turbinado sugar|raw sugar", "1|cup", None),
    Choice("honey", "169640", W, "honey", "1|cup", None),
    Choice("maple_syrup", "169661", V, "maple syrup", "1|cup", None),
    Choice("corn_syrup", "168837", V, "corn syrup|light corn syrup", "1|cup", None),
    Choice("molasses", "168820", W, "molasses", "1|cup", None),
    Choice("cocoa", "169593", W, "cocoa powder|cocoa", "1|cup", None),
    Choice("baking_powder", "172804", W, "baking powder", "1|tsp", None),
    Choice("bicarbonate_of_soda", "175040", W, "bicarbonate of soda|baking soda|bicarb", "1|tsp", None),
    Choice("cream_of_tartar", "175041", W, "cream of tartar", "1|tsp", None),
    Choice("dried_yeast", "175043", W, "dried yeast|active dry yeast|dry yeast", "1|tbsp", None),
    Choice("chocolate_chips", "167976", W, "chocolate chips|plain chocolate chips|semisweet chocolate chips", "1|cup chips (6 oz package)", None),
    Choice("breadcrumbs", "174928", W, "breadcrumbs|dried breadcrumbs|dry breadcrumbs", "1|cup", None),
    Choice("vanilla_extract", "173471", V, "vanilla extract|vanilla essence", "1|tbsp", None),
    Choice("skimmed_milk_powder", "170877", W, "skimmed milk powder|dried skimmed milk|nonfat dry milk", "1|cup", None),
    Choice("whole_milk_powder", "173454", W, "whole milk powder|milk powder|dried milk", "1|cup", None),
    Choice("sweetened_coconut", "168586", W, "sweetened desiccated coconut|sweetened shredded coconut", "1|cup, shredded", None),
    Choice("fresh_coconut", "170169", W, "fresh coconut|grated coconut|coconut", "1|cup, shredded", None),
    # Rice, grains and pasta
    Choice("long_grain_rice", "168877", W, "rice|white rice|long grain rice|basmati rice|basmati", "1|cup", None),
    Choice("medium_grain_rice", "168879", W, "medium grain rice|arborio rice|risotto rice", "1|cup", None),
    Choice("short_grain_rice", "168881", W, "short grain rice|pudding rice|sushi rice", "1|cup", None),
    Choice("brown_rice", "169703", W, "brown rice|long grain brown rice", "1|cup", None),
    Choice("glutinous_rice", "168883", W, "glutinous rice|sticky rice", "1|cup", None),
    Choice("parboiled_rice", "169707", W, "parboiled rice|easy cook rice", "1|cup", None),
    Choice("cooked_rice", "168878", W, "cooked rice|boiled rice", "1|cup", None),
    Choice("oats", "173904", W, "oats|rolled oats|porridge oats|oatmeal", "1|cup", None),
    Choice("quinoa", "168874", W, "quinoa", "1|cup", None),
    Choice("couscous", "169699", W, "couscous", "1|cup", None),
    Choice("bulgur", "170688", W, "bulgur wheat|bulgur|bulgar wheat", "1|cup", None),
    Choice("pearl_barley", "170284", W, "pearl barley|barley", "1|cup", None),
    Choice("millet", "169702", W, "millet", "1|cup", None),
    Choice("buckwheat", "170685", W, "buckwheat|buckwheat groats|kasha", "1|cup", None),
    Choice("spaghetti", "169736", W, "spaghetti", "1|cup spaghetti", None),
    Choice("penne", "169736", W, "penne", "1|cup penne", None),
    Choice("macaroni", "169736", W, "macaroni|elbow macaroni", "1|cup elbows", None),
    Choice("farfalle", "169736", W, "farfalle|pasta bows", "1|cup farfalle", None),
    Choice("fusilli", "169736", W, "fusilli|rotini|pasta twists", "1|cup rotini", None),
    Choice("pasta_shells", "169736", W, "pasta shells|conchiglie", "1|cup shells", None),
    # Pulses
    Choice("red_lentils", "174284", W, "red lentils|split red lentils|masoor dal", "1|cup", None),
    Choice("lentils", "172420", W, "lentils|green lentils|brown lentils", "1|cup", None),
    Choice("cooked_lentils", "172421", W, "cooked lentils", "1|cup", None),
    Choice("chickpeas", "173756", W, "chickpeas|dried chickpeas|garbanzo beans|kabuli chana", "1|cup", None),
    Choice("tinned_chickpeas", "173801", W, "tinned chickpeas|canned chickpeas", "1|cup drained, rinsed", None),
    Choice("kidney_beans", "173744", W, "kidney beans|red kidney beans|rajma", "1|cup", None),
    Choice("black_beans", "173734", W, "black beans|black turtle beans", "1|cup", None),
    Choice("pinto_beans", "175199", W, "pinto beans", "1|cup", None),
    Choice("haricot_beans", "173745", W, "haricot beans|navy beans", "1|cup", None),
    Choice("white_beans", "175202", W, "white beans", "1|cup", None),
    Choice("adzuki_beans", "173727", W, "adzuki beans|aduki beans", "1|cup", None),
    Choice("mung_beans", "174256", W, "mung beans|whole moong|green gram", "1|cup", None),
    Choice("urad_beans", "174259", W, "urad beans|whole urad|black gram", "1|cup", None),
    Choice("split_peas", "172428", W, "split peas|green split peas", "1|cup", None),
    Choice("soya_beans", "174270", W, "soya beans|soybeans|soy beans", "1|cup", None),
    Choice("pigeon_peas", "172436", W, "pigeon peas|dried pigeon peas|red gram", "1|cup", None),
    Choice("peanuts", "172430", W, "peanuts|groundnuts|raw peanuts", "1|cup", None),
    # Nuts, seeds and dried fruit
    Choice("almonds", "170567", W, "almonds|whole almonds", "1|cup, whole", None),
    Choice("ground_almonds", "170567", W, "ground almonds|almond flour|almond meal", "1|cup, ground", None),
    Choice("flaked_almonds", "170567", W, "flaked almonds|sliced almonds", "1|cup, sliced", None),
    Choice("cashews", "170571", W, "cashews|cashew nuts", "1|cup, halves and whole", None),
    Choice("walnuts", "170187", W, "walnuts|walnut halves", "1|cup shelled (50 halves)", None),
    Choice("chopped_walnuts", "170187", W, "chopped walnuts", "1|cup, chopped", None),
    Choice("pistachios", "170184", W, "pistachios|pistachio nuts", "1|cup", None),
    Choice("sesame_seeds", "170150", W, "sesame seeds|til", "1|cup", None),
    Choice("sunflower_seeds", "170562", W, "sunflower seeds", "1|cup", None),
    Choice("pumpkin_seeds", "170556", W, "pumpkin seeds|pepitas", "1|cup", None),
    Choice("flaxseed", "169414", W, "flaxseed|linseed|flax seeds", "1|cup, whole", None),
    Choice("peanut_butter", "174266", W, "peanut butter|smooth peanut butter", "1|cup", None),
    Choice("raisins", "168165", W, "raisins", "1|cup (not packed)", None),
    Choice("sultanas", "168164", W, "sultanas|golden raisins", "1|cup (not packed)", None),
    Choice("tamarind", "167763", W, "tamarind|tamarind pulp", "1|cup, pulp", None),
    # Milk, cream, cheese, eggs and fats
    Choice("milk", "171265", V, "milk|whole milk|full fat milk", "1|cup", None),
    Choice("semi_skimmed_milk", "171267", V, "semi skimmed milk|reduced fat milk|2% milk", "1|cup", None),
    Choice("skimmed_milk", "171269", V, "skimmed milk|skim milk|fat free milk", "1|cup", None),
    Choice("one_percent_milk", "170872", V, "1% milk", "1|cup", None),
    Choice("double_cream", "170859", V, "double cream|heavy cream|heavy whipping cream", "1|cup, fluid (yields 2 cups whipped)", None),
    Choice("whipping_cream", "170858", V, "whipping cream|light whipping cream", "1|cup, fluid (yields 2 cups whipped)", None),
    Choice("single_cream", "170857", V, "single cream|light cream|table cream", "1|cup", None),
    Choice("half_and_half", "171255", V, "half and half", "1|cup", None),
    Choice("sour_cream", "171257", W, "soured cream|sour cream", "1|cup", None),
    Choice("yoghurt", "171284", W, "yoghurt|yogurt|plain yoghurt|natural yoghurt|whole milk yoghurt|curd|dahi", "1|cup (8 fl oz)", None),
    Choice("low_fat_yoghurt", "170886", W, "low fat yoghurt|low fat yogurt", "1|cup (8 fl oz)", None),
    Choice("butter", "173410", W, "butter|salted butter", "1|cup", None),
    Choice("unsalted_butter", "173430", W, "unsalted butter", "1|cup", None),
    Choice("ghee", "173412", W, "ghee|clarified butter|butter oil", "1|cup", None),
    Choice("cream_cheese", "173418", W, "cream cheese|soft cheese", "1|cup", None),
    Choice("cheddar", "173414", W, "cheddar|cheddar cheese|grated cheddar", "1|cup, shredded", None),
    Choice("mozzarella", "170845", W, "mozzarella|grated mozzarella", "1|cup, shredded", None),
    Choice("parmesan", "171247", W, "parmesan|grated parmesan|parmesan cheese", "1|cup", None),
    Choice("feta", "173420", W, "feta|feta cheese", "1|cup, crumbled", None),
    Choice("ricotta", "170851", W, "ricotta", "1|cup", None),
    Choice("cottage_cheese", "172179", W, "cottage cheese", "1|cup, small curd (not packed)", None),
    Choice("eggs", "171287", C, "egg|eggs", "1|cup (4.86 large eggs)", "1|large"),
    Choice("olive_oil", "171413", V, "olive oil|extra virgin olive oil", "1|cup", None),
    Choice("sunflower_oil", "172338", V, "sunflower oil", "1|cup", None),
    Choice("vegetable_oil", "172370", V, "vegetable oil|soybean oil|cooking oil", "1|cup", None),
    Choice("rapeseed_oil", "172336", V, "rapeseed oil|canola oil", "1|cup", None),
    Choice("coconut_oil", "171412", W, "coconut oil", "1|cup", None),
    Choice("sesame_oil", "171016", V, "sesame oil|gingelly oil", "1|cup", None),
    Choice("groundnut_oil", "171410", V, "groundnut oil|peanut oil", "1|cup", None),
    # Sauces, tins and liquids
    Choice("coconut_milk", "170173", V, "coconut milk|tinned coconut milk", "1|cup", None),
    Choice("vinegar", "172237", V, "vinegar|white vinegar|distilled vinegar|spirit vinegar", "1|cup", None),
    Choice("cider_vinegar", "173469", V, "cider vinegar|apple cider vinegar", "1|cup", None),
    Choice("red_wine_vinegar", "172240", V, "red wine vinegar", "1|cup", None),
    Choice("balsamic_vinegar", "172241", V, "balsamic vinegar|balsamic", "1|cup", None),
    Choice("soy_sauce", "174277", V, "soy sauce|shoyu", "1|cup", None),
    Choice("tamari", "174278", V, "tamari", "1|tbsp", None),
    Choice("tomato_puree", "170459", W, "tomato puree|tomato paste", "1|cup", None),
    Choice("passata", "170054", V, "passata|tomato sauce", "1|cup", None),
    Choice("tinned_tomatoes", "170051", W, "tinned tomatoes|canned tomatoes|chopped tomatoes", "1|cup", None),
    Choice("ketchup", "168556", W, "ketchup|tomato ketchup|catsup", "1|cup", None),
    Choice("mayonnaise", "171009", W, "mayonnaise|mayo", "1|cup", None),
    Choice("jam", "169641", W, "jam|preserves", "1|tbsp", None),
    Choice("lemon_juice", "167747", V, "lemon juice", "1|cup", None),
    Choice("lime_juice", "168156", V, "lime juice", "1|cup", None),
    Choice("water", "174158", V, "water", "1|cup", None),
    Choice("salt", "173468", W, "salt|table salt", "1|cup", None),
    # Spices and dried herbs
    Choice("black_pepper", "170931", W, "black pepper|ground black pepper|pepper", "1|tbsp, ground", None),
    Choice("black_peppercorns", "170931", W, "black peppercorns|peppercorns|whole black pepper", "1|tsp, whole", None),
    Choice("white_pepper", "170933", W, "white pepper|ground white pepper", "1|tbsp, ground", None),
    Choice("cayenne", "170932", W, "cayenne pepper|cayenne", "1|tbsp", None),
    Choice("chili_powder", "171319", W, "chili powder|chili powder blend", "1|tbsp", None),
    Choice("cinnamon", "171320", W, "cinnamon|ground cinnamon", "1|tbsp", None),
    Choice("ground_cloves", "171321", W, "ground cloves", "1|tbsp", None),
    Choice("cumin_seeds", "170923", W, "cumin seeds|cumin|jeera|whole cumin", "1|tbsp, whole", None),
    Choice("coriander_seeds", "170922", W, "coriander seeds|whole coriander", "1|tbsp", None),
    Choice("turmeric", "172231", W, "turmeric|ground turmeric|haldi", "1|tbsp", None),
    Choice("curry_powder", "170924", W, "curry powder", "1|tbsp", None),
    Choice("ground_ginger", "170926", W, "ground ginger|ginger powder|dried ginger", "1|tbsp", None),
    Choice("garlic_powder", "171325", W, "garlic powder", "1|tbsp", None),
    Choice("onion_powder", "171327", W, "onion powder", "1|tbsp", None),
    Choice("paprika", "171329", W, "paprika|smoked paprika|sweet paprika", "1|tbsp", None),
    Choice("nutmeg", "171326", W, "nutmeg|ground nutmeg", "1|tbsp", None),
    Choice("ground_cardamom", "170919", W, "ground cardamom|cardamom powder", "1|tbsp, ground", None),
    Choice("fennel_seeds", "171323", W, "fennel seeds|fennel seed|saunf", "1|tbsp, whole", None),
    Choice("fenugreek_seeds", "171324", W, "fenugreek seeds|methi seeds", "1|tbsp", None),
    Choice("mustard_powder", "170929", W, "mustard powder|ground mustard", "1|tbsp", None),
    Choice("poppy_seeds", "171330", W, "poppy seeds|khus khus", "1|tbsp", None),
    Choice("caraway_seeds", "170918", W, "caraway seeds", "1|tbsp", None),
    Choice("celery_seeds", "170920", W, "celery seeds|celery seed", "1|tbsp", None),
    Choice("allspice", "171315", W, "allspice|ground allspice", "1|tbsp", None),
    Choice("anise_seeds", "171316", W, "aniseed|anise seeds", "1|tbsp, whole", None),
    Choice("dried_oregano", "171328", W, "dried oregano|oregano", "1|tsp, leaves", None),
    Choice("dried_thyme", "170938", W, "dried thyme|thyme", "1|tbsp, leaves", None),
    Choice("dried_basil", "171317", W, "dried basil", "1|tbsp, leaves", None),
    Choice("dried_rosemary", "171333", W, "dried rosemary|rosemary", "1|tbsp", None),
    Choice("dried_parsley", "170930", W, "dried parsley", "1|tbsp", None),
    Choice("dried_dill", "171322", W, "dried dill|dill weed", "1|tbsp", None),
    Choice("dried_sage", "170935", W, "dried sage|ground sage|sage", "1|tbsp", None),
    Choice("dried_coriander_leaf", "170921", W, "dried coriander leaf|dried cilantro", "1|tbsp", None),
    Choice("dried_tarragon", "170937", W, "dried tarragon|tarragon", "1|tbsp, leaves", None),
    Choice("saffron", "170934", W, "saffron", "1|tbsp", None),
    Choice("instant_coffee", "171893", W, "instant coffee|instant coffee powder", "1|tsp", None),
    # Vegetables
    Choice("onion", "170000", C, "onion|brown onion|yellow onion|white onion", "1|cup, chopped", "1|medium (2-1/2\" dia)"),
    Choice("spring_onion", "170005", C, "spring onion|scallion|green onion", "1|cup, chopped", "1|medium (4-1/8\" long)"),
    Choice("garlic", "169230", C, "garlic|garlic clove|clove of garlic", "1|cup", "1|clove"),
    Choice("ginger", "169231", W, "ginger|fresh ginger|ginger root", "1|tsp", None),
    Choice("tomato", "170457", C, "tomato|tomatoes|fresh tomato", "1|cup, chopped or sliced", "1|medium whole (2-3/5\" dia)"),
    Choice("cherry_tomatoes", "170457", W, "cherry tomatoes", "1|cup cherry tomatoes", None),
    Choice("potato", "170028", C, "potato|white potato", "0.5|cup, diced", "1|medium (2+-1/4\" to 3-1/4\" dia.)"),
    Choice("sweet_potato", "168482", C, "sweet potato", "1|cup, cubes", "1|sweetpotato, 5\" long"),
    Choice("carrot", "170393", C, "carrot", "1|cup chopped", "1|medium"),
    Choice("celery", "169988", C, "celery|celery stick", "1|cup chopped", "1|stalk, medium (7-1/2\" - 8\" long)"),
    Choice("red_pepper", "170108", C, "red pepper|red bell pepper|bell pepper|capsicum|red capsicum", "1|cup, chopped", "1|medium (approx 2-3/4\" long, 2-1/2 dia.)"),
    Choice("green_pepper", "170427", C, "green pepper|green bell pepper|green capsicum", "1|cup, chopped", "1|medium (approx 2-3/4\" long, 2-1/2\" dia)"),
    Choice("green_chilli", "170497", C, "green chilli|green chili|hari mirch", "0.5|cup, chopped or diced", "1|pepper"),
    Choice("red_chilli", "170106", C, "red chilli|fresh red chilli|red chili", "0.5|cup, chopped or diced", "1|pepper"),
    Choice("jalapeno", "168576", W, "jalapeno|jalapeno pepper", "1|cup, sliced", None),
    Choice("aubergine", "169228", C, "aubergine|eggplant|brinjal", "1|cup, cubes", "1|eggplant, unpeeled (approx 1-1/4 lb)"),
    Choice("courgette", "169291", C, "courgette|zucchini", "1|cup, chopped", "1|medium"),
    Choice("cucumber", "169225", C, "cucumber", "1|cup, sliced", "1|medium"),
    Choice("mushrooms", "169251", W, "mushrooms|button mushrooms|white mushrooms", "1|cup, pieces or slices", "1|medium"),
    Choice("cauliflower", "169986", C, "cauliflower", "1|cup chopped (1/2\" pieces)", "1|head medium (5-6\" dia.)"),
    Choice("broccoli", "170379", W, "broccoli", "1|cup chopped", None),
    Choice("cabbage", "169975", W, "cabbage|white cabbage|green cabbage", "1|cup, chopped", None),
    Choice("red_cabbage", "169977", W, "red cabbage", "1|cup, chopped", None),
    Choice("spinach", "168462", W, "spinach|fresh spinach|baby spinach|palak", "1|cup", None),
    Choice("frozen_spinach", "169287", W, "frozen spinach", "1|cup", None),
    Choice("frozen_peas", "170016", W, "frozen peas|peas|garden peas|green peas", "1|cup", None),
    Choice("sweetcorn", "168398", W, "sweetcorn|sweet corn|frozen sweetcorn|corn kernels", "1|cup", None),
    Choice("green_beans", "169961", W, "green beans|french beans", "1|cup 1/2\" pieces", None),
    Choice("okra", "169260", W, "okra|bhindi|ladies fingers", "1|cup", None),
    Choice("beetroot", "169145", C, "beetroot|beet", "1|cup", "1|beet (2\" dia)"),
    Choice("radish", "169276", C, "radish", "1|cup slices", "1|medium (3/4\" to 1\" dia)"),
    Choice("mooli", "168451", W, "mooli|daikon|white radish", "1|cup slices", None),
    Choice("leek", "169246", C, "leek", "1|cup", "1|leek"),
    Choice("romaine_lettuce", "169247", C, "romaine lettuce|cos lettuce|romaine", "1|cup shredded", "1|head"),
    Choice("iceberg_lettuce", "169248", C, "iceberg lettuce|iceberg", "1|cup shredded", "1|head, medium (6\" dia)"),
    Choice("coriander", "169997", W, "coriander|fresh coriander|coriander leaves|cilantro|dhania", "0.25|cup", None),
    Choice("parsley", "170416", W, "parsley|fresh parsley|flat leaf parsley", "1|cup chopped", None),
    Choice("basil", "172232", W, "basil|fresh basil", "0.25|cup leaves, whole", None),
    Choice("mint", "173475", W, "mint|fresh mint|spearmint", "2|tbsp", None),
    Choice("drumsticks", "170483", C, "drumsticks|drumstick|moringa|moringa pods", "1|cup slices", None),
    Choice("tofu", "172475", W, "tofu|firm tofu", "0.5|cup", None),
    # Fruit
    Choice("apple", "171688", C, "apple", "1|cup slices", "1|medium (3\" dia)"),
    Choice("banana", "173944", C, "banana", "1|cup, mashed", "1|medium (7\" to 7-7/8\" long)"),
    Choice("lemon", "167746", C, "lemon", "1|cup, sections", "1|fruit (2-1/8\" dia)"),
    Choice("lime", "168155", C, "lime", None, "1|fruit (2\" dia)"),
    Choice("orange", "169097", C, "orange", "1|cup, sections", "1|fruit (2-5/8\" dia)"),
    Choice("mango", "169910", C, "mango", "1|cup pieces", "1|fruit without refuse"),
    Choice("avocado", "171706", C, "avocado|hass avocado", "1|cup, pureed", "1|fruit, without skin and seed"),
    Choice("pear", "169118", C, "pear", "1|cup, slices", "1|medium"),
    Choice("peach", "169928", C, "peach", "1|cup slices", "1|medium (2-2/3\" dia)"),
    Choice("plum", "169949", C, "plum", "1|cup, sliced", "1|fruit (2-1/8\" dia)"),
    Choice("kiwi", "168153", C, "kiwi|kiwi fruit|kiwifruit", "1|cup, sliced", "1|fruit (2\" dia)"),
    Choice("grapes", "174683", W, "grapes", "1|cup", None),
    Choice("strawberries", "167762", W, "strawberries|strawberry", "1|cup, whole", "1|medium (1-1/4\" dia)"),
    Choice("blueberries", "171711", W, "blueberries", "1|cup", None),
    Choice("raspberries", "167755", W, "raspberries", "1|cup", None),
    Choice("pineapple", "169124", C, "pineapple", "1|cup, chunks", "1|fruit"),
    Choice("pomegranate_seeds", "169134", W, "pomegranate seeds|pomegranate arils", "0.5|cup arils (seed/juice sacs)", None),
]
# fmt: on


def volume_ml(amount: float, modifier: str) -> float:
    """The volume of a USDA portion such as "1|cup, chopped" or "1|tbsp, whole"."""
    for unit in sorted(VOLUME_ML, key=len, reverse=True):
        if modifier == unit or modifier.startswith((unit + ",", unit + " ")):
            return amount * VOLUME_ML[unit]
    raise SystemExit(f"Not a volume portion: {amount}|{modifier}")


def portion_grams(
    portions: dict[tuple[str, str], float], choice: Choice, spec: str
) -> tuple[float, float]:
    """The amount and gram weight of one of a food's USDA portions, given as "amount|modifier"."""
    amount, modifier = spec.split("|", 1)
    found = portions.get((choice.fdc_id, f"{float(amount):g}|{modifier}"))
    if found is None:
        raise SystemExit(f"{choice.key}: no portion {spec!r} in USDA food {choice.fdc_id}")
    return float(amount), found


def read_csv(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    with archive.open(FOLDER + name) as raw:
        return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")))


def build(zip_path: Path, choices: list[Choice] | None = None) -> list[dict[str, str]]:
    with zipfile.ZipFile(zip_path) as archive:
        foods = {row["fdc_id"]: row for row in read_csv(archive, "food.csv")}
        categories: dict[str, str] = {}
        for row in read_csv(archive, "food_category.csv"):
            categories[row["id"]] = row["description"]
            categories.setdefault(row.get("code", ""), row["description"])
        portions: dict[tuple[str, str], float] = {}
        for row in read_csv(archive, "food_portion.csv"):
            spec = f"{float(row['amount']):g}|{row['modifier']}"
            portions[(row["fdc_id"], spec)] = float(row["gram_weight"])

    check_aisle_tables()
    if choices is CHOICES:
        check_overrides_known(choices)
    seen_keys: set[str] = set()
    seen_names: dict[str, str] = {}
    rows = []
    choices = CHOICES if choices is None else choices
    for choice in choices:
        if choice.key in seen_keys:
            raise SystemExit(f"Key used twice: {choice.key}")
        seen_keys.add(choice.key)
        for name in choice.names.split("|"):
            if name != name.strip().lower() or not name:
                raise SystemExit(f"Names must be lower case and trimmed: {name!r}")
            if name in seen_names:
                raise SystemExit(f"{name!r} is in both {seen_names[name]} and {choice.key}")
            seen_names[name] = choice.key
        food = foods.get(choice.fdc_id)
        if food is None or food["data_type"] != "sr_legacy_food":
            raise SystemExit(f"{choice.key}: no SR Legacy food {choice.fdc_id}")

        category = categories.get(food.get("food_category_id", ""))
        if category is None:
            raise SystemExit(f"{choice.key}: USDA food {choice.fdc_id} has no known category")

        mg_per_ml = item_mg = ""
        if choice.volume:
            amount, weight = portion_grams(portions, choice, choice.volume)
            modifier = choice.volume.split("|", 1)[1]
            mg_per_ml = str(round(weight * 1000 / volume_ml(amount, modifier)))
        if choice.item:
            amount, weight = portion_grams(portions, choice, choice.item)
            item_mg = str(round(weight * 1000 / amount))
        if not mg_per_ml and not item_mg:
            raise SystemExit(f"{choice.key}: nothing to convert with")
        rows.append(
            {
                "key": choice.key,
                "names": choice.names,
                "counted_as": choice.counted_as,
                "mg_per_ml": mg_per_ml,
                "item_weight_mg": item_mg,
                "fdc_id": choice.fdc_id,
                "usda_description": food["description"],
                "volume_portion": choice.volume or "",
                "item_portion": choice.item or "",
                "aisle": aisle_for(choice.key, category),
                "usda_category": category,
            }
        )
    return rows


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = build(Path(sys.argv[1]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as out:
        out.write(
            "# Food conversions for Mealwright. Built by scripts/build_conversions.py; do not edit.\n"
            "# Source: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central,\n"
            "# SR Legacy, April 2018 (FoodData_Central_sr_legacy_food_csv_2018-04). Public domain (CC0 1.0).\n"
            "# Cups are US cups (236.6 ml), as in the USDA household measures.\n"
        )
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} foods to {OUT}")


if __name__ == "__main__":
    main()
