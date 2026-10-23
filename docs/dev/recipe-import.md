# Recipe import: fetching and reading a page

How Mealwright fetches a recipe page (and its main photo) safely, and reads the recipe out of
it. The rules come from spec section 6, "Recipe import, decided for 0.5", and section 7,
"Recipe links on your own network". The last section says how the import's API joins them to the
screens.

Six modules:

| Module | What it does |
| --- | --- |
| `mealwright.page_fetch` | `fetch_page()` and `download_photo()`: every check below, then the request through the outbound gate |
| `mealwright.own_network` | the household's "Your own network" list (table `own_network_entry`), and which addresses need listing or are always blocked |
| `mealwright.page_reader` | `read_page()`: a page's text in, a `PageRecipe` (or `None`) out; never goes online |
| `mealwright.page_budget` | `read_within_budget()`: `read_page()` in a short-lived child process, stopped past its processor-time, clock or memory limit, at most two at once (below, "The work budget") |
| `mealwright.network_guard` | the audit hook that refuses connections made outside the gate; small on purpose, so the page-reading child can switch it on too |
| `mealwright.recipe_import` | the import itself: the one box, the review, Save (last section) |

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
     carry one of these inside them (IPv4-mapped, IPv4-compatible, NAT64 and local NAT64
     64:ff9b:1::/48, 6to4, Teredo) are blocked too.
   - **Needs listing:** anything that isn't an ordinary public address (private, shared
     100.64.0.0/10, unique-local, multicast, reserved and the like, in either form) is
     refused unless the household's list holds the name or that address.
4. **The port.** 80 and 443 only, unless the list holds the name or every one of its
   addresses. Port 0 is never a link.
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
   shrinks it and removes hidden data, the same as an upload. The user agent is just
   "Mealwright"; no cookies are sent.
8. **Time.** Each connection has at most the gate's 15 seconds in all. That is per address
   tried, not per hop: if a name's first address can't be reached, the next one gets a fresh
   15 seconds. The whole fetch, every redirect included, has at most 30
   (`page_fetch.MAX_FETCH_SECONDS`; decided by cabledrawer, see spec). A watchdog closes the
   connection when the time runs out, so a site that sends one byte at a time can't hold it
   open: a socket's own timeout only counts the wait for each byte. The 30 seconds don't
   cover the name look-up: a look-up can't be cut once it has started, so a slow one can run
   past the 30 by its own length (the system resolver's own timeout bounds it). The time
   left is checked before each look-up, so at most one look-up runs past, and nothing is
   fetched after it.

A page's text is decoded with the charset the site names (in the header, else in the page's
first 4 KB), else UTF-8; bytes that don't fit are replaced, never refused. Only real text
charsets count: a name Python knows but that isn't one (zlib, base64, rot13, idna, utf-7),
UTF-16 and UTF-32, or an unknown name, means UTF-8. A page can be sent in UTF-16 with a
byte-order mark at the start; it is read as UTF-8 too, so no recipe is found in it.

A refusal raises `FetchRefused`, with `problem` (a `Problem` code the API will send) and
`message` (the sentence a screen shows; see words.md section 18). Log lines name only the
connection ("recipe import") and the kind of problem, **never the page's address or host**: a
site name shows what someone was cooking.

`download_photo` returns the cleaned photo; it doesn't store it.

### The "Your own network" list

One table, `own_network_entry`, owned by the household like the Privacy switches. Each
entry is a host name, one address, or a range (CIDR), with who added it and when. It starts
empty. `own_network.add()` tidies an entry (lower-case name, the address or range in its
usual form; a /32 or /128 range is stored as its one address, so "192.168.1.5/32" and
"192.168.1.5" are the same entry) and refuses:

- anything always blocked, or a range that holds an always-blocked address. So the whole of
  100.64.0.0/10 (it holds 100.100.100.200) or fd00::/8 (it holds fd00:ec2::254) can't be
  listed: list the part in use, such as 100.64.0.0/11 or fd12:3456:789a::/48;
- ranges wider than /8 (IPv4) or /32 (IPv6);
- IPv6 ranges that carry IPv4 addresses inside them, or any part of one: IPv4-mapped
  ("::ffff:192.168.1.0/120"), IPv4-compatible, NAT64 (64:ff9b::/96 and the local
  64:ff9b:1::/48), 6to4 (2002::/16) and Teredo (2001::/32). Write IPv4 ranges as IPv4;
- the same entry twice;
- a 101st entry: a list holds at most 100 (`MAX_ENTRIES`; decided by cabledrawer, see spec).

A listed name opens every address that name has (except the always-blocked ones). A listed
address or range opens those addresses, whatever name reaches them. One household's list
never opens another's fetches. If an install ever has more than one household, the list
becomes a server-level setting (spec section 6); a comment on the table says so.

### The API and the screen (0.5 PR 4)

Settings → Privacy (`/settings/privacy`) uses `api/v1/privacy.py`. Everyone in the household
can read; only an admin can change (a member gets 403 `admins_only`). Two places on the
screen can be linked to: `/settings/privacy#outside-connections` (the import screen's "Photo
not downloaded" and "switched off" links) and `/settings/privacy#your-own-network`.

- `GET /privacy/switches` gives `{switches: [{connection, on}], can_change}` for
  `recipe_import` and `recipe_photos` (the other connections arrive with 0.8). Both start off.
- `PUT /privacy/switches/{connection}` with `{on}` (admins only). The outbound gate reads the
  switch each time it is about to connect, so the next connection follows at once.
- `GET /privacy/own-network` gives `{entries, limit, can_change}`, oldest first. An entry is
  `{id, kind, value, addresses, added_by, added_on}`; `addresses` counts an IPv4 range.
- `POST /privacy/own-network` with `{value}` (admins only) gives 201 and the entry. A refusal
  carries `own_network`'s own sentence and a `code`: `bad_entry`, `always_blocked`,
  `too_wide` (422); `already_listed`, `list_full` (409).
- `DELETE /privacy/own-network/{id}` (admins only) gives 204; an entry of another household
  is "not found", like one that doesn't exist.

Log lines say only "Privacy: recipe import switched on" and "Your own network: added" or
"removed", never an entry.

## What the reader gives back

`read_page(html: str, url: str) -> PageRecipe | None`. `url` is where the page was in the end
(`FetchedPage.url`), used to make relative photo addresses absolute. `None` means no recipe:
the page has no schema.org Recipe with ingredients or steps (the screen offers pasted text
instead). The import must call it through `page_budget.read_within_budget(html, url)`,
never directly, so that every page is read within the work budget (`recipe_import` does).

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
  cookies") gives Makes. A range takes its first number ("Serves 4–6" is Serves 4; decided
  by cabledrawer, see spec). A bare number that equals the Makes amount next to it
  (`["24", "24 cookies"]`) is the Makes, not Serves.
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
inside lists are flattened to a depth of 4. A start tag longer than 65,536 characters is
skipped whole (the standard parser would hold about 100 bytes of memory for each byte of
one), and a method is walked through at most 10,000 parts, counting repeats, so sections
that list themselves can't make it endless. An object referenced many times by `@id` is
read once per field (and once in the whole method), so referencing one big text thousands of
times costs no more than reading it once, and each different text is tidied once per page,
however many fields use it. In microdata, an element's text includes every property inside
it, so properties nested in properties would read the same text again at each level; the
text read for microdata is limited to the page's length (or a million characters and
elements, for a smaller page). A number longer than 20 characters in a time, a yield or a
nutrition value is left out before it's converted: converting a long run of digits takes
time that grows with the square of its length (a million digits took 8.6 seconds), and a
real one is a few characters. A JSON-LD block is
skipped, unread, if it would take the page's blocks past 50,000 objects and lists in all
(counted as `{` and `[`, before parsing; a real recipe has a few hundred): read, each tiny
object takes about 50 times its size in memory.

The time grows in step with the page's size. Measured on 5 MB pages after these limits
(without Python's memory counting, which slows it): the slowest found so far are plain valid
tags (about 1.7 million `<p>`, or `x<i></i>` runs), in the page's body, in one JSON-LD field
or in one text that eight fields use, which take about 3.4 to 3.6 seconds on a fast PC. 250 nested microdata properties take about 1 second, and one JSON-LD field of 2.6
million "<a" or "< x " under 2 seconds. Memory peaks at about 120 MB (as Python counts it;
about 177 MB for the whole process, Python itself included): 5 MB of plain words with one
emoji in one field, since the emoji makes every character of that text take 4 bytes. The
same words without the emoji take about 70 MB, and the other pages tried about 60 MB or
less.

### The work budget

The limits above answer every slow or greedy page found so far. As a safety net for the ones
nobody has found yet (spec section 6, "A work budget for each page"), the import reads each
page with `page_budget.read_within_budget`, which runs `read_page` in a short-lived child
process and stops it past any of these limits:

| Limit | Value | Why |
| --- | --- | --- |
| Processor time (`MAX_CPU_SECONDS`) | 12 seconds, the child's own processor time (`RLIMIT_CPU`) | Counts the work a page needs, not how busy the machine is (a Raspberry Pi doing other things reads the same page in the same processor time). The realistic big test page needs about 1.2 seconds on a fast PC (measured 23 Oct, 6-core desktop processor: 1.1 to 1.25 s in all, 0.08 s of it to start the child), so perhaps 5 to 6 seconds on a Raspberry Pi 4 class board (an estimate, not measured). 12 is more than twice that. |
| The clock (`MAX_WALL_SECONDS`) | 15 seconds from starting the child to its answer, or what is left of the import's 30 seconds when that is less | The backstop for a child that is stuck rather than working, or a machine so busy that processor time runs slowly. The import passes what it has left (`within_seconds`), so the fetch, the wait for a place and the read together never pass the 30 seconds. |
| Memory (`MAX_MEMORY`) | 384 MB, all the child's memory, Python itself included | The realistic big test page needs 88 MB; Python alone is about 30 MB. |
| At once (`MAX_AT_ONCE`) | 2 pages, for the whole server | cabledrawer 23 Oct, question 22: each child may use 384 MB, so a third waits its turn. |

Before this (PR 1) the limit was 5 seconds of clock; the realistic page took 1.3 s on a fast PC, so a
Raspberry Pi could have refused a real page (#54, round 5, item 24). The figures, measured on the
fast PC: the realistic big page 1.1 to 1.25 s of processor time; the slowest known 5 MB page (about
1.7 million `<p>`) 3.0 to 3.5 s; a tiny page 0.08 s; memory about 88 MB for the realistic page and
177 MB for the greediest.

The limits are never less than 10 seconds of processor time and 256 MB (a test checks the floor), and
the clock is always the wider of the two time limits. The realistic big test page is built in
`tests/test_page_budget.py`: 5 MB shaped like a big recipe blog post, with stylesheets and
scripts in the head, a JSON-LD graph with a 200-ingredient, 100-step recipe, a long menu,
3,000 paragraphs and thousands of comments. The largest page in `tests/import_pages/` is
3.5 KB and takes under 0.1 second and 30 MB.

How it works:

- The child is started with "spawn", a fresh Python, never "fork": the server has threads,
  and a fork can copy a lock another thread holds. It imports only `page_reader` and
  `network_guard` (no gate and no database code), gets the page's text and address, and sends
  back the result through a pipe.
- **Processor time:** before reading, the child limits its own processor time (`RLIMIT_CPU`, 12
  seconds; a hard limit 2 seconds later). The system ends it with SIGXCPU, and the import says
  the page couldn't be read.
- **The clock:** the server waits at most 15 seconds for the answer (less if the import has less
  left, see below), then kills the child and waits for it to end, so no process is left behind.
  After an answer it waits at most 2 seconds (and no longer than the time left) for the child to
  end by itself, then kills it.
- **Memory:** before reading, the child limits its own memory (`RLIMIT_AS`) to 384 MB. Past it,
  Python raises MemoryError, and the child answers "memory" (or ends, if it can't).
- **No core file** (`RLIMIT_CORE` 0), and **the network guard is switched on in the child**
  (cabledrawer 23 Oct, defence in depth): it starts fresh, so it doesn't have the server's guard. A
  test shows a connection from the child is refused.
- **Two at a time:** a place is taken before the child starts and always given back, however the
  read ends. A third read waits its turn; the wait counts within the import's own 30 seconds. If
  it can't start in time the import says "Mealwright is busy reading another page. Try again in a
  moment." (`page_budget.BUSY`).
- **The import's 30 seconds:** one deadline, set when the import
  starts, and every step is given only what is left of it. The fetch gets what is left (at most
  30). If the fetch leaves less than `MIN_READ_SECONDS` (2 seconds; a typical page needs about
  1.2 on a fast PC), the page isn't read and the answer is "That site took too long to answer.
  Try again later." (`timeout`). The reader gets what is left as `within_seconds`: the wait for a
  place and the read share it, the clock limit is cut to what is left once a place is free, and
  if the wait left less than 2 seconds the answer is the busy sentence. With no time left after
  the read, the photo isn't downloaded and the review says "Photo not downloaded" with the
  timeout sentence. The one thing the clock doesn't time is shrinking a photo that has already
  arrived; the photo's own limits (15 MB, 50 megapixels) keep that short.
- Over any limit, `read_within_budget` raises `PageUnreadable` (`reason` "time", "memory" or
  "crash"); a result that is too big to send or can't be pickled, or a child that dies without
  answering (a crash), is "crash". The screen shows "Couldn’t read that page. Paste the recipe’s
  text instead." (`page_fetch.Problem.CANT_READ`; approved by cabledrawer 23 Oct). The log line names
  only the connection and the reason ("Couldn't read a page: recipe import, over its time limit"),
  never the address. Anything else the reader raises is raised in the server as if it had read the
  page itself, and the import turns it into the same sentence (below).
- Standard library only (`multiprocessing`, `resource`, `threading`). `resource` is Unix only, like
  the server's container.

What it can't stop:

- The server itself still holds the page's text (up to 5 MB, about 20 MB in Python at worst) and a
  copy sent to the child, and decodes the page before the budget starts.
- The memory limit counts all the child's memory, so it's a limit on the whole process, not just
  the page; a much bigger Python could need it raised.
- Starting the child also starts Python's own small helper process for multiprocessing (the
  "resource tracker"), once, which stays while the server runs.
- If the server is killed while a child is reading, the child stops at its own processor limit.
- The answer comes back from our own child as a pickled object; that's safe only because nothing
  else can write to the pipe.

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

## The import's API

`POST /api/v1/recipes/import` (`recipe_import.start`) and `POST /api/v1/recipes/import/save`
(`recipe_import.save`), both in the OpenAPI (`/api/v1/openapi.json`). The web app uses only these.

**Start.** The body is `{"text": "...", "again": false}`. One box: a link (one word with no spaces
that starts `http://`, `https://` or `www.`, or names another kind of address such as `ftp://`) or
pasted text (anything else). Mealwright works out which. The answer is the review: the name,
description, author, time, serves, makes, tags and nutrition; the photo (`state` `downloaded`,
`off`, `none` or `failed`); every ingredient line as `written`, then what the saved line will hold
(`words`, `amount`, `unit`, `size`, `note`), its `label` (`matched`, `to_confirm`, `needs_you` or
`staple`), the ingredient it is (or the best guess), where it lives, whether it counts, the first
guess for a new ingredient and the name "Same as" would learn; the steps; the counts; `lines_cut`
and `steps_cut` (a page with more than 200 lines or 100 steps keeps the first ones),
`steps_shortened` (steps over 5,000 characters, cut by the review) and `left_out` (the Notes and
Tips of pasted text: "4 lines after “Tips” were left out"). **Nothing is saved** except a
downloaded photo, which waits like an uploaded one until Save (the hourly tidy-up drops one no
recipe took in 24 hours; at most 10 wait per household). `makes` is in plain units (`{"amount":
24, "unit": "cookies"}`, never thousandths), and Save takes it back the same way.

A link with "Recipe import from links" off is refused with 403 `import_switched_off` ("Importing
from links is switched off"; `admin` says whether the person can switch it on, and a member's
sentence adds "An admin can switch it on."), before anything is looked up or fetched. Pasted text
never goes online and works with the switch off. A link goes through `page_fetch` only, its page is
read only with `page_budget.read_within_budget`, and the fetch, a wait for a place to read, the
read and the photo share one 30-second deadline set when the import starts (see "The import's 30
seconds" above). Every refusal is 422 with a `code` and a sentence from
`words.md` section 18: `bad_link`, `always_blocked`, `own_network`, `odd_port`,
`too_many_redirects`, `cant_reach` (also anything the fetch did not expect), `timeout`, `site_error`, `not_a_page`, `page_too_big`,
`cant_read` (over a budget, a crash, or anything the reader did not expect: the log has the
connection's label and the kind of error, never an address), `busy`, `no_recipe` (a page without a
recipe, or text without one), `text_too_long`, `nothing_given`. The photo never stops an import:
if its switch is off the review says "Photo not downloaded" (`off`), and if the download is
refused or fails it says why (`failed`).

**The same link twice.** A link the household already has a recipe from (not a deleted one) answers
409 `already_imported` with the recipe, the site, the date and the photo, before anything is fetched
(and again after a redirect, if the address it ended on is one already imported). Send `again:
true` to import it again as a copy.

**Save.** The body is the review's recipe as the screen has it (name, serves and minutes can be
changed there), each line with its `link`:

- `{"kind": "ingredient", "food_id": 7, "learn": "red onion"}`: tie the line to an ingredient the household
  has; `learn` adds that name as another name of the ingredient ("Same as Onions"). A name the
  ingredient or any other ingredient already has is skipped, never stolen.
- `{"kind": "new", "name": "Hing", "counted_as": "weight", "place_id": 3}`: a new ingredient, made on
  Save; nothing is added to the pantry. Two lines asking for the same name make it once; a name the
  household already has is refused at that line (409 `name_taken`, `line`).
- `{"kind": "staple", ...}`: a new staple ("Treat as staple"): the line never counts.
- No `link`: the line is saved with its words only ("not linked"). The review says how many lines
  that will be; the spec does not say Save must wait for every choice, so it does not.

One transaction creates the recipe, the new ingredients, the staples and the learned names, and
records **one** change, `recipe_imported`, in Ingredients → Recent changes (summary: "Imported
Sambar, with 2 new ingredients and 1 other name"). Its Undo hides the recipe (like a deleted one:
gone for good after 7 days, photo and all) and takes back the new ingredients and the names, as
one. The server checks the recipe again as the editor's own save does (limits, units, the loops
guard, the household of every id): an ingredient, place, size or photo of another household is a
404 at its line. The recipe keeps its web address, import date and author (`recipe.source` in the
recipe's answer; the address must be `http` or `https`). A retry with the same `Idempotency-Key`
saves once.

**The screens.** `/recipes/import`: the box (`ImportStart`), "You already have this recipe"
(`AlreadySheet`) and the review (`ReviewScreen`, `ReviewLineRow`). Online only: offline, the box
says it needs the server, and nothing is queued. Leaving the review just leaves for now ("Save as
a draft?" comes with Drafts). "Save & plan it" is hidden until 0.6.
