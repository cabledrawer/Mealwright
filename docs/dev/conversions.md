# The bundled food-conversion table

Mealwright converts between cups, spoons, grams and items using two layers (spec section 6, "Foods and units"): this built-in table, with the household's own "ask once" answers on top. Household answers always win, and app updates never change them.

## Source and licence

- **Dataset:** USDA FoodData Central, **SR Legacy**, April 2018 release (the final release of the USDA National Nutrient Database for Standard Reference, Legacy). File: `FoodData_Central_sr_legacy_food_csv_2018-04.zip` (CSV), downloaded 17 Oct 2026 from `https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip`. SHA-256 of the file used: `b80817294b8850530aaedf2e515c02593b1824f763a0ff356e5c2081643e6fd0`.
- **Licence:** public domain, under **CC0 1.0** (FoodData Central's own licence statement). No values come from any other source. Rejected (cabledrawer 17 Oct): Open Food Facts (ODbL), FAO density tables (licence unclear).
- **Credit** (USDA asks for it; shown here and later in Settings → About): "Food conversion data: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy, 2018. fdc.nal.usda.gov."

## What's in it

`backend/src/mealwright/data/food-conversions.csv`, about 220 common foods. Columns:

| Column | Meaning |
|---|---|
| `key` | Mealwright's own id for the row (`plain_flour`). Stored on a food as `table_key`. |
| `names` | Names a household's food is matched by, `|`-separated (matching ignores case, accents, brackets, hyphens and simple plurals). |
| `counted_as` | How a new food with this name is counted in the pantry by default: weight, volume or count. |
| `mg_per_ml` | Weight per millilitre in milligrams (0.8 g/ml → 800). Empty if USDA gives no volume measure. |
| `item_weight_mg` | Weight of one item in milligrams (a medium onion, 110 g → 110000). Empty if not given. |
| `fdc_id`, `usda_description` | The USDA food each row comes from. |
| `volume_portion`, `item_portion` | The exact USDA "household measure" each number was worked out from. |

How the numbers are made (by the build script only):

- **Weight per ml** = the gram weight of the chosen USDA portion ÷ its volume. USDA household measures are **US customary**: 1 cup = 8 US fl oz = 236.59 ml, 1 tbsp = 14.79 ml, 1 tsp = 4.93 ml. The app then shows "Weight of 1 cup" in the household's own cup (240 or 250 ml).
- **Weight of one item** = the gram weight of the chosen portion ÷ its count. These are USDA's (US) sizes: an egg is a US "large" egg without its shell (50 g), an onion a US "medium" (110 g).
- Nothing is typed in or estimated by hand. The script holds only the *choice* of USDA food and portion for each row; it stops if a chosen food or portion isn't in the file exactly as written.

Many Indian ingredients aren't in SR Legacy (toor dal, curry leaves, jaggery…). The app asks once for those, as the spec says.

## Rebuilding it

Run this in WSL, from the repo root. Each command says what it does.

```sh
# Make a fresh, empty folder for the download (it's untrusted data, so keep it apart).
mkdir -p ~/usda-download && cd ~/usda-download
# Download the USDA file (about 6 MB).
curl -fLO https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip
# Check it's the same file as before (should print the SHA-256 above).
sha256sum FoodData_Central_sr_legacy_food_csv_2018-04.zip
# Go back to the repo and build the table. -I keeps Python from loading anything from the download folder.
cd -  && cd backend
python3 -I scripts/build_conversions.py ~/usda-download/FoodData_Central_sr_legacy_food_csv_2018-04.zip
# See what changed.
git diff --stat src/mealwright/data/food-conversions.csv
```

The script only reads the zip; it never unpacks or runs anything from it. To add or change a food, edit the `CHOICES` list in `backend/scripts/build_conversions.py` (pick a USDA food and one of its listed portions) and rebuild. Tests check the table loads, that no two rows share a name, and that every row has something to convert with.

## Checking by hand

Before 1.0 (spec section 8), the table is checked by hand. A quick way: weigh one level cup of a few foods from the samples given in the pull request, using a 240 ml or 250 ml measuring cup, and compare.
