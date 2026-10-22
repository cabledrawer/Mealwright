# Recipe import: fetching and reading a page

How Mealwright fetches a recipe page (and its main photo) safely, and reads the recipe out of
it. The rules come from spec section 6, "Recipe import, decided for 0.5", and section 7,
"Recipe links on your own network". This is the server side only: the API addresses and
screens that use it come later in 0.5.

Three modules:

| Module | What it does |
| --- | --- |
| `mealwright.page_fetch` | `fetch_page()` and `download_photo()`: every check below, then the request through the outbound gate |
| `mealwright.own_network` | the household's "Your own network" list (table `own_network_entry`), and which addresses need listing or are always blocked |
| `mealwright.page_reader` | `read_page()`: a page's text in, a `PageRecipe` (or `None`) out; never goes online |

## How fetching is checked

Nothing is looked up, read or sent until all of these pass, in this order:

1. **The switch.** "Recipe import from links" (`Connection.RECIPE_IMPORT`) for a page, "Download
   recipe photos" (`Connection.RECIPE_PHOTOS`) for a photo. Both start off. While a switch is
   off the fetch is refused before any name look-up, and the gate checks the switch again
   before each look-up and each connection, so turning it off mid-fetch stops it.
2. **The link.** `http` or `https` only, with a host, no user name or password, and no `%` in
   the host. The host is tidied to lower-case ASCII (international names become punycode),
   the fragment is dropped, and the path and query are %-encoded.
3. **The name.** `localhost` and names under it are refused by name. Any other name is looked
   up inside the gate (`OutboundGate.look_up`), and **every** address it has is checked:
   - **Always blocked, even if listed:** this server itself (127.0.0.0/8, ::1, and 0.0.0.0/8
     and ::, which also reach it), link-local (169.254.0.0/16, fe80::/10) and the cloud
     "metadata" addresses (169.254.169.254, 100.100.100.200, fd00:ec2::254). IPv6 forms that
     carry one of these inside them (IPv4-mapped, IPv4-compatible, NAT64, 6to4, Teredo) are
     blocked too.
   - **Needs listing:** anything that isn't an ordinary public address (private, shared
     100.64.0.0/10, unique-local, multicast, reserved and the like, in either form) is
     refused unless the household's list holds the name or that address.
4. **The port.** 80 and 443 only, unless the list holds the name or every one of its
   addresses.
5. **Pinned.** The request goes to exactly the address that was checked
   (`OutboundGate.get_pinned`), while the Host header and the TLS name (SNI and the
   certificate check) stay the host name. So a name can't pass the check with a public
   address and then be fetched from a private one (DNS rebinding). If an address can't be
   reached, the name's next checked address is tried.
6. **Redirects.** The gate never follows one by itself. `page_fetch` follows at most 5 by
   hand, and every hop goes through steps 2 to 5 again.
7. **The answer.** Pages: `text/html` or `application/xhtml+xml` only ("This link isn't a web
   page."), and reading stops past 5 MB. Photos: any `image/` type, reading stops past
   15 MB, then `photos.clean` decides what it really is, refuses more than 50 megapixels,
   shrinks it and removes hidden data, the same as an upload. Each hop has the gate's 15
   seconds. The user agent is just "Mealwright"; no cookies are sent.

A page's text is decoded with the charset the site names (in the header, else in the page's
first 4 KB), else UTF-8; bytes that don't fit are replaced, never refused.

A refusal raises `FetchRefused`, with `problem` (a `Problem` code the API will send) and
`message` (the sentence a screen shows; see words.md section 18). Log lines name only the
connection ("recipe import") and the kind of problem, **never the page's address or host**: a
site name shows what someone was cooking.

`download_photo` returns the cleaned photo; it doesn't store it.

### The "Your own network" list

One table, `own_network_entry`, owned by the household like the Privacy switches. Each
entry is a host name, one address, or a range (CIDR), with who added it and when. It starts
empty. `own_network.add()` tidies an entry (lower-case name, the address or range in its
usual form) and refuses:

- anything always blocked, or a range that holds an always-blocked address. So the whole of
  100.64.0.0/10 (it holds 100.100.100.200) or fd00::/8 (it holds fd00:ec2::254) can't be
  listed: list the part in use, such as 100.64.0.0/11 or fd12:3456:789a::/48;
- ranges wider than /8 (IPv4) or /32 (IPv6);
- IPv4 ranges written in IPv6 form ("::ffff:192.168.1.0/120"): write them as IPv4;
- the same entry twice.

A listed name opens every address that name has (except the always-blocked ones). A listed
address or range opens those addresses, whatever name reaches them. One household's list
never opens another's fetches. If an install ever has more than one household, the list
becomes a server-level setting (spec section 6); a comment on the table says so.

## What the reader gives back

`read_page(html: str, url: str) -> PageRecipe | None`. `url` is where the page was in the end
(`FetchedPage.url`), used to make relative photo addresses absolute. `None` means no recipe:
the page has no schema.org Recipe with ingredients or steps (the screen offers pasted text
instead).

```python
@dataclass(frozen=True)
class PageLine:
    text: str              # as written, whitespace tidied, HTML tags and entities removed
    heading: bool = False  # a section name ("For the tadka")

@dataclass(frozen=True)
class PageRecipe:
    name: str                                 # "" if the page names nothing at all
    description: str | None                   # cut at 200 characters, at a word, with "…"
    author: str | None
    total_minutes: int | None                 # totalTime, or prep + cook; up to 14,400
    serves: int | None                        # 1 to 99
    makes: tuple[Decimal, str] | None         # (12, "cookies")
    nutrition: dict[str, Decimal | None]      # kcal, protein, carbs, fat, fibre per serving
    tags: tuple[str, ...]                     # category + cuisine, never keywords; up to 20
    photo_url: str | None                     # the main image, absolute, http(s)
    ingredients: tuple[PageLine, ...]         # up to 200, headings included
    steps: tuple[PageLine, ...]               # up to 100, headings included
    lines_cut: bool                           # the page had more than 200 lines
    steps_cut: bool                           # the page had more than 100 steps
```

Where it looks:

- **JSON-LD** first (`<script type="application/ld+json">`): several blocks, `@graph`,
  `@type` lists, `@id` references, `HowToSection` and `HowToStep`, `NutritionInformation`.
  Broken blocks and blocks wrapped in comments or CDATA are handled; the first Recipe with
  ingredients or steps wins. Then **microdata** (`itemscope`/`itemprop`) on older pages.
- **Name:** the recipe's name, else the page's `og:title`, else its `<title>`; cut at 200.
- **Photo:** the recipe's image (a string, a list, or an `ImageObject`), else `og:image`;
  relative addresses are made absolute against `<base href>` or the page address.
- **Yield:** "Serves 4", "4 servings" or a bare number give Serves; anything else ("12
  cookies") gives Makes. A range takes its first number. A bare number that equals the
  Makes amount next to it (`["24", "24 cookies"]`) is the Makes, not Serves.
- **Nutrition:** the first number in each value; kJ becomes kcal, mg and µg become grams.
- **Ingredient headings:** a line with no digits that ends in ":" and is up to 60 characters
  ("For the dressing:") becomes a heading.
- **Tags:** category then cuisine, split on commas; a tag over 40 characters is left out, and
  duplicates (ignoring case) are dropped.
- **Text:** the page isn't the user's typing, so it's tidied rather than refused: tags and
  entities (even twice encoded) removed, hidden characters taken out (flag emoji and the
  joiners Tamil and Hindi need are kept), runs of spaces made one.
- What can't be used is left out, never guessed: a time over 10 days, a yield of 500
  servings, a negative nutrition number.

### Hostile pages

A page is anyone's text, so the reader has limits of its own: elements nested deeper than 256
are read as siblings, at most 200,000 elements and text runs are kept from one page (a real
page has about 10,000), JSON-LD is searched to a depth of 64 and microdata to 16, and lists
inside lists are flattened to a depth of 4. A 5 MB page built to be awkward reads in about 2
to 3 seconds, with under 100 MB of memory at its peak.

## Swapping the reader

`page_reader` is the one place that knows how recipe pages are written. The spec plans
recipe-scrapers as a fallback for 0.7, if real pages still fail; that would be a new
dependency, so it needs cabledrawer's OK first. To swap:

1. Write a module that provides `read_page(html: str, url: str) -> PageRecipe | None` with the
   same `PageLine` and `PageRecipe` (import them from `page_reader`, or move them to their
   own module).
2. Keep the rules above: the same limits and cut flags, keywords never tags, `None` for a
   page with no recipe, and **no network access**. The reader gets the page's text from
   `fetch_page` and must never fetch anything itself (recipe-scrapers can be given HTML
   rather than a link; use it that way).
3. Run `tests/test_page_reader.py` against it. Its tests use only `read_page` and the test
   pages, so they work unchanged on a new reader.

Nothing else changes: `page_fetch` doesn't know about the reader, and the import code only
sees `PageRecipe`.

## The test pages

`backend/tests/import_pages/` holds made-up pages for `tests/test_page_reader.py`. Each copies
only the *structure* one kind of recipe site uses (how its schema.org data is laid out), with
our own text, no photos and `.example` addresses. No real page was copied or looked at for
them, and the tests never go online. Real pages are never committed.

| File | Shaped like | What it tries |
| --- | --- | --- |
| `big_magazine.html` | BBC Good Food | one JSON-LD block, ImageObject, nutrition in "kcal" and "g", a bare-number yield, keywords |
| `wp_recipe_maker.html` | WordPress, WP Recipe Maker with Yoast | `@graph`, `@id` references, image list, yield list, HowToSection, nutrition without fibre |
| `tasty_recipes.html` | WordPress, Tasty Recipes | entities in the text (twice encoded), HTML in steps, "Makes" yield, image as a string |
| `dotdash.html` | Allrecipes / Dotdash Meredith | `@type` as a list, the recipe inside an array, several authors, duration with days and hours |
| `south_indian_blog.html` | a South Indian vegetarian blog | Tamil and Hindi names, joiners kept, hidden characters taken out, ingredient section headings, kJ |
| `newspaper.html` | the Guardian / Jamie Oliver | long description with HTML, no nutrition, no times, "Serves 4–6", headings in the ingredients |
| `old_microdata.html` | an older microdata-only page | `itemscope`/`itemprop`, `<base href>`, relative image, `ingredients`, nested nutrition and author |
| `no_recipe.html` | an ordinary article | JSON-LD that isn't a recipe: no recipe found |
| `several_blocks.html` | any site | a broken block, comment-wrapped JSON, an unrelated block, then the recipe; image as an object list |

The fetching tests (`tests/test_page_fetch.py`) fake every name look-up and connection, so
they never go online either.
