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
| `mealwright.drafts` | drafts: an import left unfinished, kept for 15 days (the section after the API) |


## On one page (read this, then grep)

Added 25 Oct (cabledrawer 25 Oct), so nobody reads the whole file: read this page and the module table above, then only the sections your pull request needs (`grep -n '^##' docs/dev/recipe-import.md`). This page only repeats what is below; where they differ, the section wins.

- **Fetching (How fetching is checked):** nothing is looked up or sent unless the Privacy switch is on ("Recipe import from links", "Download recipe photos"; both start off). Then the link (http/https only), the name and **every** address it has (this server, link-local and cloud metadata addresses always blocked; private addresses only if on the household's "Your own network" list), the port (80/443 unless listed), a request pinned to the checked address, at most 5 redirects each checked again, size limits (5 MB page, 15 MB photo), and 15 s per connection, 30 s in all. Everything goes through the outbound gate.
- **Logs** name only the connection and the kind of problem, never the page's address.
- **Reading (What the reader gives back, Hostile pages):** `read_page` turns a page into a `PageRecipe` (or `None`) and never goes online. It is always called through `page_budget.read_within_budget`, a child process with processor-time, clock and memory limits (The work budget).
- **Photos** are cleaned like an upload (type checked, at most 50 megapixels, shrunk, hidden data removed) and stored locally, never hotlinked.
- **The API (The import's API):** `POST /api/v1/recipes/import` takes one box (a link or pasted text) and returns the review; `POST /api/v1/recipes/import/save` saves it.
- **Drafts:** an unfinished import, kept for 15 days (Drafts).
- **Tests:** The real-recipe check and The test pages.

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
   open: a socket's own timeout only counts the wait for each byte. The name look-up is timed
   too (spec section 6, question 40): every `look_up` is given the import's deadline, and
   past it the answer is the same `timeout`. A look-up can't be cut once it has started, so
   `OutboundGate.look_up` runs it on a daemon worker thread (inside the gate) and stops
   waiting for it; a late answer is thrown away, and the thread itself ends when the system
   resolver's own limit does. With no time left nothing is looked up. (Proposed, for
   cabledrawer: one import leaves at most two such threads behind, its page's and its photo's,
   because a timeout on the page ends the import.)

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
  timeout sentence. The name look-up is timed like every other step. Two things are not:
  shrinking a photo that has already arrived (the photo's own limits, 15 MB and 50
  megapixels, keep that short), and a stuck look-up's worker thread, which can finish in the
  background after the import has given up on it (proposed, for cabledrawer; the fetch section
  above says more).
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

`page_reader` is the one place that knows how recipe pages are written. recipe-scrapers is not used in 0.7
(cabledrawer 28 Oct: "okay for now, revisit after 0.9.0 real world testing"); it would be a new
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

## The real-recipe check

`backend/scripts/import_check.py` is a dev-only tool (spec section 6, "Real-recipe test"): it
fetches the real pages on cabledrawer's list, reads them, and reports what the reader found. It is
run by hand, never by `./check`, and is not in the Docker image (the image holds only the
installed package and the web app; `tests/test_test_clock.py` and `tests/test_import_check.py`
read the Dockerfile to prove it). It has no pass mark.

```bash
cd backend
uv run python scripts/import_check.py
# or, with other files:
uv run python scripts/import_check.py --list /path/to/urls.md --report /path/to/report.md
```

- **The list** (default `import-check/urls.md` in the sync folder, which is `$MEALWRIGHT_SYNC_DIR` or `./repo-sync`, outside the repo; no
  address is ever committed): `## ` headings are groups (sites), `- <address> — <note>` lines
  are recipes. Blank lines and lines starting with `>` or `# ` are skipped quietly; any other
  line is ignored and counted in the report.
- **Fetching:** one address at a time, at most one request every 5 seconds per site (counted
  from the end of the last one). Each goes through `page_fetch.fetch_page` with a real
  `OutboundGate`, on a throwaway database where only "Recipe import from links" is on, so the
  user agent, limits and address checks are the app's own. Redirects are followed by
  `page_fetch` as in the app. The page is read with `page_budget.read_within_budget`, then each
  ingredient line with `ingredient_reader.read_line`. **No photo is downloaded**; the report
  says only whether the page names one.
- **The report** (default `import-check-0.5.md` in the sync folder): a summary table
  with one row per address (group, result, whether a title was found and its first 40
  characters, ingredients read and not read, steps, photo named yes/no, the address); a count
  line per group; then, per recipe, the ingredient lines the reader couldn't read and the
  number or unit words that probably stopped it finding an amount. The result is one of read,
  no recipe data, refused by the site, blocked or couldn't read, with the app's own problem
  code beside it. No page text, HTML or photo address is written, and nothing of a page is
  saved.
- **What it leaves out:** a "what it read" column (JSON-LD or microdata), because `read_page`
  doesn't say which it used and the check doesn't change the reader. The "words not known" list
  is a guide: the reader doesn't report the words it didn't know, so the check lists the number
  and the word after it on lines that start with a number but got no amount.
- **One failure never stops the run:** each is a row. Ctrl-C stops it and writes what it has
  so far, marked "Stopped early".

`tests/test_import_check.py` tests it with made-up pages and a fake fetcher or fake network;
it never goes online.

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

**Threads.** The import is an ordinary (not async) endpoint, so each import holds one of the
server's worker threads for its whole length, up to 30 seconds: the fetch, any wait for a place to
read, the read and the photo. The server has the library's usual 40 worker threads, shared by every
request, not only imports. Two pages are read at a time, so the others wait for a place in their
thread; only an unusual number of imports at once (about 40 within the same 30 seconds) uses the
threads up. Then new requests of any kind wait in line for a thread to come free (they aren't
refused, and nothing is lost); each import ends within its 30 seconds (the fetch, the name
look-up, the wait for a place and the read are all timed; shrinking a photo that has arrived
is the one step that isn't, and its limits keep it short), so the line moves. A stuck name
look-up also keeps a small background thread of its own until the system resolver gives up;
that thread isn't one of the server's 40 worker threads (proposed, for cabledrawer). There is no
cap on waiting imports: it would be new scope, and a household of the size this is made for
doesn't get near it. A cancelled request doesn't stop its thread, which finishes its 30 seconds at
most and gives its place back.

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
  household already has (made by another draft meanwhile, say) is used for the line instead, as
  that ingredient is, so Save is never refused for it (F213, cabledrawer 10 Nov).
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
says it needs the server, and nothing is queued. Leaving the review without saving asks "Save as a
draft?" (below). "Save & plan it" is hidden until 0.6.

## Drafts (0.5 PR 5)

An import left unfinished, kept so the household can carry on (spec section 6, "Drafts (cabledrawer 21
Oct)", "Drafts: how long they last (cabledrawer 22 Oct, question 8)" and "Size limits (cabledrawer 22 Oct,
question 9)"). `mealwright.drafts`, `api/v1/drafts.py`, table `import_draft`, and
`recipe_photo.draft_id`; one migration (`d7a4c2e81f56`, tested up, down and up).

**What a draft keeps.** The box's text (the link or the pasted text, up to 100,000 characters),
the review exactly as the server sent it (`review`), every choice so far (`choices`: the Name,
Serves and Minutes boxes as typed, `null` for "as read", and a choice for each line the person has
settled: Same as an ingredient, New ingredient, Treat as staple), who started it and when, when it
was last changed, and, through `recipe_photo.draft_id`, the downloaded photo. The server checks the
shape and the size (at most 200 lines, 100 steps of 5,000 characters, 20 tags, 2 MB of review) and
that a photo is the household's own, and that every whole number in the request fits what the
database stores (too big is 422 `bad_number`, like any other number in the API); **Save checks
everything again**, so a draft is only a place to
carry on from. The server rebuilds the list's words from it: the ingredient lines, and how many are
tied to an ingredient (matched or staple lines, and any line with a choice), kept in
`lines_total` and `lines_checked` ("6 of 9 ingredients checked · 3 need you").

**Nothing in a draft touches Ingredients.** Keeping, changing, reading, deleting, undoing and
tidying a draft makes no ingredient, staple or other name and writes no Recent changes entry
(`test_drafts.py`, `test_nothing_in_a_draft_touches_ingredients_until_save`). The new ingredients,
staples and learned names it holds are made on Save, as for any import.

**The API** (all under `/api/v1`, all for the signed-in household only; another household's draft
is a plain 404):

| | |
| --- | --- |
| `GET /recipes/drafts` | the household's drafts, the one changed last first: name, where from, who started it, `days_left`, `lines_total`, `lines_checked` |
| `POST /recipes/drafts` | keep a review as a draft (`text`, `review`, `choices`); 201. At 50 drafts: 409 `too_many_drafts`, "You have 50 drafts. Finish or delete one first." A retry with the same `Idempotency-Key` makes no second draft |
| `GET /recipes/drafts/{id}` | carry on: the text, the review and the choices. Opening changes nothing |
| `PUT /recipes/drafts/{id}` | replace what it keeps (the same body); counts as a change |
| `DELETE /recipes/drafts/{id}` | hide it at once; the answer has the change whose Undo (`POST /changes/{id}/undo`) brings it back |
| `POST /recipes/import/save` with `draft_id` | Save as always (one transaction, one `recipe_imported` change, one Undo), and the draft is removed in the same transaction; its photo becomes the recipe's |

**The 15 days** count from the last change (`updated_at`): a draft that someone changes does not
vanish, and the days left grow back to 15. **Looking** at a draft (opening it, listing) is not a
change. A draft past its 15 days is no longer listed, can't be opened or saved from, and doesn't
count towards the 50, even before the hourly tidy-up (`jobs.purge_removed_ingredients`, which
calls `drafts.purge`) deletes it, with its photo, quietly. **Delete** hides a draft at once
(`removed_at`) and records `draft_removed` (not in Recent changes; found by Ctrl+Z through the
server's list of your own changes, like a deleted recipe). It is kept hidden for the undo window
(7 days, plus an hour so an offered Undo can't vanish), then deleted for good with its photo. **Undo**
brings it back counted as just changed (its 15 days start again, so it isn't back for a moment and
then gone). At 50 drafts an Undo is refused with the same sentence as keeping a 51st: no old draft
is ever deleted to make room.

**Undo of a Save from a draft** (spec section 6, question 36). The Save keeps what it deletes in its own
change record (`undo_data.draft`: the box's text, what was read, every choice, the name and who
started it, and the id of the photo it took), so nothing new is stored in the database and there is
no migration. Undo takes the recipe back as for any import (hidden, with its new ingredients and
other names), then makes the draft again **with the same id**, counted as just changed (its 15 days
start again), and moves the photo back from the recipe to the draft (the same file; the recipe's
copy goes with the recipe). Details that are mine, **proposed, for cabledrawer**:

- **At 50 drafts the whole Undo is refused** with the 50-drafts sentence ("You have 50 drafts.
  Finish or delete one first."), checked before anything is done, so nothing is half undone and
  there are never 51. Make room, and the same Undo works.
- **If the recipe's photo was removed or replaced after the Save**, that file is no longer the
  draft's to take back: the draft comes back without it, saying "The photo wasn’t kept." (the
  sentence a draft already uses). Nothing else is lost.
- **If the recipe is already deleted** (so the Undo has nothing to take back), no draft is made.
- **When the copy goes.** The record holds the draft's review and choices (at most 2 MB, counted as
  stored) and its text (at most 100,000 characters), but only until the Save's Undo is used or its
  undo window (7 days by default; the household's own setting) has passed, whichever comes first.
  Then only that copy (`undo_data.draft`) is dropped: an Undo drops it in the same transaction, and
  the hourly tidy-up (`drafts.purge`, through `drop_save_copies`) drops it for a Save past its
  window. The rest of the change stays for as long as changes are kept (12 months by default),
  Recent changes still shows it as before, and an Undo of a Save past its window is still refused
  as "too long ago".
- Only this household's recipe and photo are looked at; a record naming another household's recipe
  or photo does nothing.

**Two people at once.** The spec doesn't say, so the last save wins: `PUT` replaces the draft whole
and neither person is told. Both can still carry on and Save; whoever Saves first makes the recipe
(the draft goes), and the other's Save is then a plain 404 "That draft isn’t here any more." with
the recipe already in Recipes.

**The photo.** A downloaded photo is a waiting photo (24 hours) until a draft takes it:
`recipe_photo.draft_id` makes it the draft's. A draft's photo is not deleted after 24 hours and
**does not count towards the 10 that can wait** (spec, "Size limits"); it can't be attached to a
recipe by the editor, taken by another draft or deleted on its own; it is shown only while its
draft is there to see; it goes with the draft (the files once the delete is committed), and on Save
it becomes the recipe's. If the photo has already been deleted when the draft is kept (a review
left open for more than a day), the draft is kept without it and the review says "Photo not
downloaded — The photo wasn’t kept."

**Ingredients that changed since.** A draft can wait 15 days. When it is opened, an ingredient that
was renamed shows its new name, one that was merged into another shows that one, and one that was
removed is no longer offered: a line that was tied to it goes back to "needs you", and a choice
that pointed at it is dropped (`drafts.freshen`; what is stored is not rewritten by looking). Save
would refuse them anyway, line by line. **Drafts from one batch (F213, F215; cabledrawer 10 Nov;
`drafts.rematch`, run on opening, nothing stored is rewritten):** a line still waiting ("needs you"
or "to confirm") with no choice is read again against the ingredients as they are now, so an
ingredient made since by another draft or person is found; a line set to a *new* ingredient whose
name now exists is set to that ingredient; and a line that another waiting draft of the household
was told "Same as X" (with "adds the name") takes the same answer. Save no longer refuses a *new*
ingredient whose name exists: the line uses that ingredient and nothing is made
(`recipe_import.save`, `reused`). No API change.

**Logs** never hold a draft's link or text (`test_logs_never_hold_a_drafts_link_or_text`): nothing
here logs anything but a count of how many old drafts the hourly tidy-up deleted.

**The screens.** Leaving the review without saving (Cancel, the back link, a tab, the browser's
Back) asks "Save as draft?" with the mockup's words (`LeaveSheet`, guarded in `ReviewScreen` by
`beforeNavigate`). Closing or reloading the tab can't be asked about. Save draft goes to Drafts when
the person was going to Recipes, and otherwise where they were going. A draft that was opened and
left alone just leaves; one that was changed asks again in other words (proposed, for cabledrawer:
"Save your changes?", "Discard changes"). `/recipes/drafts` is the Drafts screen (`DraftsScreen`:
cards on a phone, a table on a computer), `/recipes/drafts/{id}` carries on (`ImportFlow.load`).
Each row has a visible Carry on and Delete; a draft whose ingredients are all checked also has
Save recipe (as the mockup has it), which makes the recipe exactly as Save on the review does.
Online only: offline, Drafts shows what it last had, says it can't be changed, and the Delete and
Save recipe buttons are off. The numbers beside Drafts in the sidebar and on the phone's All recipes
page are asked for once when the app opens, when the connection comes back and after a change made
here; another person's drafts show on the next look at Drafts. There are no swipes yet (0.5 PR 7).

## Import fixes and pints (0.6 PR 7)

Written by Claude Code on 27 Oct. cabledrawer OK'd every choice here on 27 Oct, including the three reading rules after the review. The sources: the 0.5 real-recipe report (`import-check-0.5.md`), cabledrawer's kickoff step 7 ("Import fixes ... and pints (answers 3 and 5), then the second real-recipe run") and his answers 3 and 5.

**Reader fixes (`ingredient_reader.py`).** Each is tested on the real line from the report.

- **Number words:** `half`, `two` to `twelve` at the start of a line (after "about" and the like) are digits: "half a lemon" is 0.5 lemon (the "a" goes), "two to three cloves" is 3 (a range, the higher one), "two 400g tins" is a pack multiple (800 g). `one` is left to the article rule that already reads "one 14 oz can". "half and half" (cream) and words that only start with one ("twofold") are left alone. **"a dozen" is not read** (it stays the size word `dozen` with an amount of 1, as before); `NUMBER_WORDS` is the one place to add words.
- **Lengths:** "1 inch ginger", "4 cm ginger", "⅓ inch ginger", "½ inch piece ginger" keep the length **in the note, as written, with no amount** (so the line never counts towards stock). A length can't be compared with a stock kept in grams, and a count of 1 would mean "one ginger". `LENGTH_UNITS` names them; to count a length as a plain count later, change the branch where `other` is dropped in `read_line`. An "a piece" size word stays as it was (kept, no amount).
- **A size word before the name:** "3 large (ripe bananas, well mashed (about 1 1/2 cups))": when what is left of the line has no name but a bracket does, the first bracket is read as the rest of the line. The amount is 3, the name is bananas, and "large", "ripe", "well mashed" and "about 1 1/2 cups" go to the note.
- **A label at the start:** "optional: 50g pecans", "To serve: ...", "For serving: ...", "To garnish: ..." (`optional`, `to serve`, `for serving`, `to garnish`, `for garnish(ing)`, `garnish`, `for the garnish / topping`): the rest of the line is read as usual, and the label (lower case) goes **first in the note**. A label with nothing after it is not a line. The report's "to serve: lots of pan-fried tofu cubes, toasted almonds, ..." is now one line named "lots of pan-fried tofu cubes" with the rest in the note; it is not split into separate ingredients.
- **Optional (R3, F151; cabledrawer 6 and 9 Nov):** the word "optional" in a line (from "(optional)", ", optional", "optional: " or the doubled "((optional))") is taken out of the note and the review line is `optional: true` (`ReadLine.optional`); a line under a "For serving", "To garnish" or "Optional" heading (F19) gets the same flag instead of the word "optional" in its note. In a step, "(optional)" anywhere or an "Optional:" / "Optional step -" label at the start sets `optional: true` on the review step and is taken out of the text (`line_prep.optional_step`); the word inside a sentence stays. The review's switches are sent to Save (`lines[].optional`, `steps[].optional`) and kept in a draft.
- **Steps that wait (M1, F124; cabledrawer 31 Oct and 9 Nov):** `step_waits.read_wait` suggests a wait from a step's words: a wait word (marinate, soak, ferment, rest, chill or refrigerate, prove) with, after it in the same sentence, a length of 30 minutes or more ("4 hours or overnight", "8-12 hours", "1 day") or "overnight". "Soaked chickpeas" is not "soak", and a short rest ("rest 5 minutes") is part of the step. One step gets one wait (the first sentence that has one). The review step says `wait` (not saved) and `wait_confirmed` (false; kept with a draft); Save sends back `wait` as the person left it. A page's total time loses the waits it counts (`active_time`: the longest waits if the total could hold them, else the shortest, else it is left alone), so "745 min" is 25 min and a night. Pasted text gets the same suggestions.
- **After the review (decided, cabledrawer 27 Oct):** a number word is not read when the next word shows it is part of a name or a fraction (`NOT_A_COUNT`: "five spice", "half fat", "Ten Acre", "two thirds", and the like), so those lines keep their name as written. A size word before a bracket is read as above only when the bracket starts with a name: "3 medium (about 1 lb)" reads like "3 medium" (no ingredient, so the review asks), never as an ingredient called "about 1 lb". A number word before a length ("Twelve 1 cm cubes butter") is left as written, with no amount and no "12 cm" note.
- **One-card list pages (#76): not changed.** The report shows a dinner round-up read as one card ("Coconut Oats Dinner", 15 ingredients, 14 steps). The reader takes the first recipe in the page's JSON-LD that has ingredients or a method; whether that page has several full recipes, a list of them, or one recipe plus links needs the page itself. What the fix needs: the page's JSON-LD block types and, per `Recipe` item, whether it has `recipeIngredient`. If it has several full recipes, the fix is "more than one distinct full recipe means no single recipe" (a plain message and paste-text); a rule written without the page could refuse real pages that carry the same recipe twice (WP Recipe Maker, Yoast).
- **Allrecipes refusals:** the request is not changed. A reply of 401, 403 or 429 to a **page** is now `site_refused`: "That site wouldn't let Mealwright read the page. Paste the recipe's text instead." (the same sentence in `page_fetch.MESSAGES`). Other errors, and any error on a photo, stay `site_error` ("That site didn't send the page. Check the link, or try again later."). The check script reports both as "refused by the site".

**Pints (cabledrawer 24 Oct, answers 3 and 5).** A pint is 568 ml in the UK and 473 ml in the US (`pints.PINT_ML`).

- **The setting:** `household.pints`, "uk" (default) or "us". Settings → Amounts → "Read pints as US pints" (a switch, off = UK). Admins change it (`PATCH /api/v1/household`); a member sees it and a note. It is the household's, so another household's choice is never used (the importer reads `kitchen.household`).
- **The reader:** `read_line(text, size_words, pint_ml)`. With `pint_ml`, "pint", "pints" and "pt" are an amount in ml ("2 pints milk" is 1,136 ml with UK pints, 946 ml with US), kept as written (`chosen`), and the line reports how many pints it said (`ReadLine.pints`). Without `pint_ml` a pint stays in the note as in 0.5. Next to a metric amount ("1 pint (568 ml) milk") the metric one is still the amount. **Quarts, gallons and fluid ounces are not read** (they stay in the note, as in 0.5): nobody asked, and a quart would need its own pair of sizes.
- **Pasted text** is read with the household's pint, always.
- **A US site** (`pints.looks_american`): the link's host is on `US_RECIPE_SITES` (a short list in `pints.py`, sub-domains count), or the page says `<html lang="en-US">` (`PageRecipe.language`, lower case, not part of what makes two recipes equal). Both are in one file so they are easy to change. A listed site is US whatever its page says. A US household needs no card.
- **On the review:** `review.pints = {household, us_site, reading}`. A US site read for a UK household is read with **US pints** (`reading` "us") and the screen shows the card "This looks like a US recipe", with the switch on. Each line that says pints has `pint_ml = {uk_ml, us_ml}`; the switch picks one and the screen sets the line's amount from it (the match doesn't change, because it uses the name). Save sends the amount shown. For this recipe only: the household's setting is never changed by it.
- **Drafts** keep the switch (`choices.pints`, null when it is as the review read). A draft kept before 0.6 has neither field and loads as the review read.


## Importer consistency, the reader (0.7.0, C1)

Written by Claude Code on 30 Oct from cabledrawer's 28 and 30 Oct decisions ("the importer lacks consistency"; "the same thing written two ways must give the same result"). Every rule has a test in `backend/tests/test_import_consistency.py` that writes the thing two ways. Things marked "proposed, for cabledrawer" wait for his OK.

- **`line_prep.py`** (new, pure text): `strip_footnotes` (F17, runs inside `working_text`), `is_page_junk` (F33), `is_ingredient_heading` / `is_step_heading` / `serving_heading` (F34, F23, F19), `clean_recipe_name` (F9, "How to Make …", "(Authentic … Recipe)"), `tidy_tags` (capitals plus the `TAG_SYNONYMS` table), `tidy_ingredient_name` (on save), `kitchen_round` (340 g; two decimals only below 10).
- **Reader (`ingredient_reader.py`):** `_spoken` ("one and a half"), `_OR_SO`, `_amount_after_name` (an amount written after the name moves to the front, only with a unit or size word), `_packs` ("1 14-ounce can"), `_QUALIFIER` ("1 heaped tsp"), `LOOSE_SIZE_WORDS` (a size word with no number or "a"), `PINT_FAMILY` and `pints.UNIT_ML` (quarts, gallons and fluid ounces, UK or US like pints; `ReadLine.pint_unit` says which, so the US switch works on them), `MODIFIER_WORDS` and `_with_shared_noun` (alternatives share a noun), `_VARIETY` (F32), `WEAK_WORDS` (F35), `split_line` / `read_lines` (F26: a spaced "+", or "and" in a line that ends "to taste" with no amounts), `FIXED_COUNTS` (a dozen is 12, a clove is 1, applied by the review when the ingredient has no such size).
- **Review (`recipe_import.py`):** junk and headings are decided for pasted text and pages alike; lines under a serving heading get the note "optional"; the review's `words` is the name without its prep words (the note carries them: F7); `pints.us_site` is false when no line says pints (F15); `more_links` (new field).
- **Kept in (`ingredient_match.py`):** `FRIDGE_WORDS` / `NOT_FRIDGE` choose the Fridge for milk, cream, raw meat and the like; chicken bouillon and corned beef are Cupboard, fish fingers Freezer (cabledrawer 31 Oct: "C1 readings: OK, but fix the Fridge list: chicken bouillon → Cupboard, (tinned) corned beef → Cupboard, fish fingers → Freezer").
- **Add an item:** `frontend/src/lib/shopping/addAmount.ts` reads the ways an ingredient is sold in front of a name ("2 packets milk"). It works offline, so it mirrors the reader's container words in a short list there rather than asking the server.

## Alpha 2 fixes (0.7, PR A3; F87, F88, F91)

Reading choices below are proposed, for cabledrawer.

- **F87 (proposed, for cabledrawer):** a word before "cloves" or "sprigs" that is in `WEAK_WORDS` (whole, dried, ground, red...) is part of the name, so "8 whole cloves" reads as the name "whole cloves", amount 8, no size word (F103 then takes "whole" out of the name: the name is "cloves" and the note "whole"). The matcher then finds Cloves as a "to confirm" best guess, or "Whole cloves" exactly if it exists. "2 garlic cloves" and "2 whole garlic cloves" still read the clove as the size word.
- **F88:** `_review_line` kept moving the amount of a line with a size word into the note when the ingredient had no such size, even when the amount was a weight or volume ("three 14-ounce cans" is 1,191 g). It now does that only when the line has no unit, the same test `size_ok` and the matcher use. The line as written stays in the note.
- **F91 (proposed, for cabledrawer):** `clean_recipe_name` also drops a "How to Make ..." part after a comma, colon, dash or bar. "Recipe" goes only where it is clearly a label, in this order: (1) the start, always: "Recipe for [a|an|the] ..." ("Recipe for Banana Bread" is "Banana Bread"), "Recipe: ..." and "Recipe - ..." as the first word ("Recipe: My Dal" is "My Dal"); a dash needs spaces round it, so "Recipe—My Dal" is kept. (2) A "Recipe" bracket, "Recipe" just before a bracket ("Lemon Rice Recipe (Chitranna)"), a bracket of puff words ("(Easy)"), then the end of the name ("The Best Recipe" is "The Best"); a dash separates only with spaces round it ("Gluten-Free Banana Bread Recipe" is "Gluten-Free Banana Bread", "New York–Style Cheesecake Recipe" is "New York–Style Cheesecake", "Butter chicken - the best curry recipe" is "Butter chicken"). (3) Whose recipe it is stays: after a possessive with or without s, also past one quoted word ("Mum's Recipe", "Kids' Recipe", "Grandma’s “Secret” Recipe"), and when the leftover is short and is a pronoun (my, our, your, his, her, their) alone or with family, secret, special, favourite, favorite, own, famous or original: step 2 is undone ("My Recipe", "Our Family Recipe", "Recipe: My Recipe" is "My Recipe", "Recipe for My Recipe (Authentic)" is "My Recipe"). A longer name loses its end label ("My Favourite Dal Recipe" is "My Favourite Dal", "Your Dal Recipe" is "Your Dal"). The two-word limit is a reading choice. "Recipe" stays inside a name ("The Recipe Tin lasagne", "Recipe Box Brownies", "My Recipe: Dal", "Secret Recipe - Chili", "Recipe-tested Chili"), before an apostrophe, before a comma, and when what is left is empty or only for/a/an/the: the name is kept as found. Every source of a name goes through the one call in `recipe_import`.
- **F97 search order (proposed, for cabledrawer):** `names.search_match` ranks a name or other name that is exactly the typed text first (-1), with case, accents and inner spaces ignored on both sides ("jalapeno" finds "Jalapeño", "weisswurst" finds "Weißwurst", "chilli  flakes" finds "Chilli flakes"), so the Ingredients page, which looks at its first page only, never offers "+ New ingredient" for a name that exists. The same order reaches every screen that searches `GET /foods?q=`: Shopping's Add an item box (`store.svelte.ts:796`, 8 results), Plan's add box (`PlanAdd.svelte:65`) the recipe editor's ingredient search (`RecipeEditor.svelte:143` and `:157`), `FoodPicker.svelte:44` (the ingredient editor, the import walk sheet and review line, Add to pantry, the Pantry page) and Pantry's "also called" lookup (`pantry.svelte.ts:104`, 500 results): an exact name now comes first there too. The inner-space and accent rule also applies to Pantry search, which only asks whether there is a match, so its order is not changed. Known limit: the page's `\p{Mn}` also drops some Hindi vowel signs (ु ू े ै ं) that Python's `combining()` keeps, so "मूंग" is read as "मग" there; this only affects whether the "+ New ingredient" offer shows, never the results.
- **F89 (cabledrawer 31 Oct; A3 half):** "clove" is no longer in `FIXED_COUNTS` (only "dozen" is: 12 of the thing itself). "2 cloves garlic", "2 garlic cloves" and "garlic, 2 cloves, minced" take the same branch as "1 bunch coriander" in `_review_line`: an ingredient with no "clove" size gets no amount, the note says "2 cloves", and the line is not counted. With a "clove" size on the ingredient the line is 2 of that size, as before. Every other size word (bunch, sprig, slice, stick, head, rasher, fillet ...) already took that branch, so nothing else changed. Learning a "clove" size from the line is K3's (cabledrawer's F106 rule).

## Import Check fixes from real use (0.7, PR A4; F103, F104, F105, F109, F112, F115)

cabledrawer's decisions are in the spec ("From cabledrawer's real use of v0.7.0-alpha.2"). Reading choices are proposed, for cabledrawer.

- **F103, "whole":** `read_line` takes "whole" out of the name wherever it stands and puts it in the note ("8 whole cloves" is 8 cloves, note "whole"; "whole black peppercorns" is Black peppercorns). It is one step on from the F87 rule (a word before "cloves" is part of the name): "whole" is no longer one of those words. It is not taken out of a name that is only "whole". "whole milk" is Milk with the note "whole" (cabledrawer said every "whole X"), but "whole" stays when the next word is wheat, grain, urad, moong, mung, masoor, chana or meal (`WHOLE_IS_PART_OF_NAME`; proposed, for cabledrawer): "whole urad dal", "whole wheat flour" and "whole grain mustard" keep their name. Other words the reader takes out of a name (`PREP_WORDS`, `DESCRIPTOR_WORDS`: fresh, large, firm, skinless, boneless...) are unchanged from before and go to the note. The other `WEAK_WORDS` (dried, ground, red...) stay in the name. "also called" is built in one place on Check (`ReviewLineRow.svelte`, `alsoCalled`): it is not shown when the name it would show is the name already in bold. The pantry search and the recipe line's picker build their own "also called" from the ingredient's other names and never from the line's own name.
- **F109, one amount for two ingredients:** `read_lines` also calls `_share_amount`: one line with an amount and a unit or size word, one " and " between two short names (at most six words each), no other number in the name, no other names, and not a name that is one thing (`ONE_THING_WITH_AND`: half and half, pork and beans, mac and cheese...; `_one_name`: "black and white beans") gives two lines with no amount, the note "4½ cups together" first, then the line's own note, and the line as written on both. A bare count ("3 carrots and onions") is not split. Other joiners: "+" and "and ... to taste" already split (F26) and are unchanged; "or" is unchanged (F11); "&" and "plus" are not split (follow-up).
- **F109, learning:** a name that has " and ", " & ", " plus " or " + " in it (`joins_two_names`) is never learned as another name: `ReviewLine.learn_name` is null for it, and Save skips it too (a draft kept earlier may still carry one). "Same as" is still offered; it just learns nothing.
- **F115:** `site_refused` is the only refusal that gets the how-to steps, because it is the only one where the page opens fine in the person's own browser and the site only turned the server away. The other refusals keep their one sentence (and "Paste text instead" where they had it). The link is cleared on `site_refused` only; every other cause keeps the link so it can be fixed.
- **F105 and F109 on Check** change `review.lines` itself (a removed line is gone from the list, a split line is replaced by two), and move the choices of the lines after it, so a draft keeps them with no change to the API.
- **F108, Made in this recipe (proposed, for cabledrawer):** a fourth kind of draft choice, `here` (`DraftChoice.kind`; the API's one shape change in this PR, no database change). Save needs nothing new: the line is sent with `link: null`, which is words only, so nothing is made, learned or taken from stock. The screen counts it as settled (`counts.matched`, drafts' `lines_checked`) and leaves it out of `unlinked`. It is offered first (`ImportFlow.offersMadeHere`) when the line's note has "from the" or its name (or the guess for a new ingredient) equals a heading of the same recipe with a leading "For the" / "To make" taken off.

## Wave 4 import fixes (0.8 W4a; F110, F171, F174, F186)

- **Several links (F110, cabledrawer 31 Oct):** the screen sends each pasted link as its own `POST /recipes/import`, one after another (`importLinks.svelte.ts`; never two at once), and keeps each review as a draft with `POST /recipes/drafts`. A link that fails shows its own sentence; the rest carry on. Nothing changed in the API: a box with several links sent straight to the API still reads the first and says `more_links`. The state lives in a module, so leaving the screen inside the app doesn't stop the reading; closing the tab does.
- **Serves and time in pasted text (F171, cabledrawer 7 Nov):** `pasted_recipe.read_pasted` reads lines made only of facts (`Serves 4`, `Serves: 4-6` as 6, `Takes 1 hour 15 minutes`, `Total time: 45 min`, `Ready in 1h 10m`, `Prep time` / `Cook time`, several on one line such as `Serves 4. Prep 10 min.`) into `PastedRecipe.serves` and `time_minutes`, and takes them out of the lines. A total beats the parts; prep and cook together add up; a lone cook time stands in for the total; a lone prep time gives no time (proposed, for cabledrawer). A sentence (`Serves 4 with rice.`, `Cook for 30 minutes.`) is not a fact line. **Round 1:** only the lines above the first Ingredients or Method heading may use the loose forms (`Prep 10 min`, `Cook 25 min`, `Total 30 min`); below a heading, and in text with no headings, only the clear forms count (`Serves …`, `Takes …`, `Total time …`, `Ready in …`, `Prep time …` / `Cook time …` or with a colon), so a method step such as `Cook 20 minutes.` stays a step. Other places that drop lines before they become ingredients or steps: `line_prep.is_page_junk` (whole ingredient lines that are the page's own buttons or labels: Print, Metric, Servings, Method…; never steps), `_steps_of` (an ABBREVIATED method is left out when a FULL one follows), the Notes/Tips parts of pasted text (left out and counted: `left_out`), and `_split_by_look` (no headings: a line above the first amount-like line is taken as a description and dropped).
- **A colon heading after a numbered step (cabledrawer 10 Nov):** in `_step_texts`, an unnumbered line straight after a numbered step used to carry on that step (a wrapped line), so "For the dosa:" was joined onto step 2 unless a blank line came first. A line that, once a bullet is taken off, starts with a capital letter, ends with ":" and `is_step_heading` is now its own entry (a heading, no step number, the bullet dropped) (`_colon_heading`). A wrapped line starts small ("following:") and still carries on, and so does a wrapped line in capitals with no colon ("GAS MARK 4"; FX2 review r1).
- **Close offline (F174, cabledrawer 7 Nov):** `ReviewScreen.close()` doesn't try to keep the draft with no connection (the page's note or the device's own word): it shows the toast `CLOSE_OFFLINE` and leaves for Recipes through the same exit as Discard (a waiting photo is let go when it can be; a draft already kept stays as last kept). Close is no longer greyed while a keep is on its way and the connection is gone.
- **One shared word (F186, cabledrawer 8 Nov):** `ingredient_match._closest` skips a food whose name is one word when the line has that word plus a word that is not a modifier (`MODIFIER_WORDS`, the colour/size/state words) or `PART_WORDS` (leaf, tinned, flaked, loose, baby, kinds of salt) (`_is_another_thing`). The comparison uses keys, so "baby" is "babi". The sweep over the 369 starter-pack names (each as a line, the rest as the household's ingredients) went from 119 suggestions to 79; the 40 that went include rice flour / rice vinegar / glutinous rice / basmati rice for Rice, spring onion for Onion, peanut butter for Butter, lemon juice and lime juice for Lemon and Lime, garlic powder and ginger garlic paste for Garlic, tomato puree and cherry tomatoes for Tomato, chicken drumsticks for Drumsticks, rice noodles and glass noodles for Noodles. Known and left alone: the colour/size check above still compares unkeyed words, so "baby" never counted as weak there.
- **Several links, round 1:** one paste reads at most 20 links and no more than Drafts has room for (`MOST_LINKS`, `DRAFT_LIMIT` in `importLinks.svelte.ts`); the count left out is said. The run stops, and the rows left say why, when a draft is refused for `too_many_drafts` or a link answers `import_switched_off`. Links are compared the way the server reads them (scheme added, host lower case, no `#` part, no trailing slash). The run stops and the list is forgotten when the session ends (`forgetWhenSessionEnds`, and the sign-out wipe).
- **F186 round 1:** cuts and parts of an animal or an egg (thigh, breast, mince, fillet, shoulder, leg, wing, drumstick, yolk, white, belly, loin, chop, rib, steak…) are `PART_WORDS`, so "chicken thighs" still offers Chicken. A second sweep (98 common line names against 49 one-word ingredients) went from 95 suggestions to 25; the price is in the PR body.
- **F186 middle way (cabledrawer 10 Nov):** `_is_another_thing(theirs, key)` now lets a one-word food through when its word is the line's main word (the last word that isn't in `_DESCRIBING`), and blocks it when it is only a side word. The main word decides even when a side word is itself a household ingredient ("chicken stock" with Stock and Chicken → Stock, to confirm). **Foods of their own (cabledrawer 10 Nov):** "coconut milk" is not Milk and "poha" is not Rice: `OWN_FOODS` lists the milks and creams of coconut, almond, oat, soy/soya, rice, cashew and hazelnut, coconut water and butter, peanut, almond, cashew and cocoa butter, ice cream, and flattened, beaten, puffed and pressed rice; a one-word food whose word is inside one of these names, in a line that holds the whole name, is never offered (`_is_another_thing`). An ingredient named for the food itself ("Coconut milk") still matches. Not swept in (follow-up): "sweet potato" (Potato) and "spring onions" (Onions) still match their main word, since "sweet" is a describing word and spring onions are onions. Same sweep (98 names, 49 foods, `f186-sweep.py`): **95** offers with no F186 rule, **25** with the first rule, **81** with this one. LOST against no rule (16), all side-word matches: butter beans, chicken stock cubes, chilli flakes, chilli powder, chocolate chips, cumin seeds, egg noodles, garlic paste, garlic powder, ginger paste, lemon juice, lemon zest, lime juice, mustard seeds, pork sausages, tomato puree. Before `OWN_FOODS`, still offered: almond milk, oat milk, coconut milk and condensed milk for Milk; peanut butter for Butter; chicken and beef stock for Stock. With `OWN_FOODS` only condensed milk is still offered Milk, and chicken and beef stock Stock; poha is never offered Rice (cabledrawer 10 Nov). Starter-pack sweep not re-run.
- **FX1 review H1 (10 Nov):** a one word that is only another name of a food whose own name has more words ("rice" for Basmati rice) keeps the strict first rule: any word of the line's own blocks it, so "poha (flattened rice)" and "jasmine rice" are never offered Basmati rice (cabledrawer 10 Nov). The price (FX1 review r2 L3): with Basmati rice / "rice", "cooked rice", "steamed rice", "leftover rice" and "long grain rice" get no suggestion either (those words aren't describing words); pick it by hand. The sweep foods all have one-word names, so its numbers stay 95 / 25 / 81. Known and harmless (to confirm only): "salt and pepper" offers Pepper, never Salt, because the last word decides; "brown rice" counts "brown" as a colour, so a Rice it is offered is a colour match, as before F186.
- **Lines on Check (W4d, F187 to F189, cabledrawer 8 Nov):** a line is added on the screen only (`ImportFlow.addLine`): a `ReviewLine` with `written: ""` and `words: ""` that the person names (`nameLine`, which looks the name up as a split line does). A line with no written words and no name (`isBlank`) is not counted, not saved and not counted in a draft's `lines_total`. **Made in another recipe** is a fifth kind of choice and of save link, `recipe`, additive in the API and with no database change: `ImportLinkIn { kind: "recipe", recipe_id, place_id? }` and `DraftChoice { kind: "recipe", recipe: Ref, place_id? }`. Save writes the recipe line with `recipe_id` (the same `sub_recipe_id` a line made in the editor has), refusing a recipe that is gone or not the household's (`404`, with the line's number). `place_id` goes on that recipe's made-ahead ingredient only when it has no usual place yet, inside the save's one `FoodEdit`, so the save's Undo takes it back; a recipe that isn't made ahead just links. A draft shows the recipe's new name, and no choice once the recipe is gone (`drafts.freshen`). The pick-list for a line (`PickLine.svelte`, loaded on first use) and the recipe editor's picker order what they find with `recipes/search.ts: arrange`: a recipe with exactly an ingredient's name comes first, both labelled Recipe and Ingredient. A line is never linked to a plain ingredient on its own when a recipe has exactly its name (the review found cabledrawer's own case still did): the reader's `match_line` (`KnownIngredients.recipe_names`, the household's recipes not in the trash) and the screen's exact look-up for a named or split line (`exactIngredient`) leave it *needs you*, so the person chooses and the pick-list offers the recipe first. An other name that is a recipe's name counts the same.

## Import reading (0.8 IM1; F210, F217, F218, F219)

How the reader now reads "each" lines, "or" lines, a pinch and a bracket word after a food is in `ingredient-reader.md`, "0.8 additions". The one API change: each review line (`ReviewLine`) has an optional `alternative` (another review line, or null) for an "or" line; Check's **Use this instead** swaps the two. Save is unchanged and there is no database change. A draft keeps the field with the rest of its review.

## Whole-0.8 review fixes: import (RF4, cabledrawer 11 Nov)

- **Drafts:** a line fixed by hand keeps its words, amount, unit and note when another draft makes its ingredient (`rematch` takes only the match from the fresh read). The Drafts list counts a draft with waiting lines through `rematch` too (`listing`), so its "n of m checked" and Save recipe agree with opening it.
- **Undo of an import's save** keeps a new ingredient that something else uses now (another recipe's line, the plan, the list, the pantry). The recipes the Undo takes back don't count as using it. The message names what stayed (`stays_sentence` in `api/v1/changes.py`); the result is still "done". No new field.
- **Several links:** pressing Read the recipes again reads only the links not read yet (a ready row whose draft is still in Drafts is kept); a failed row has its own Try again (`ImportLinks.retry`).
- **Reader (`ingredient_reader.py`, `docs/dev/ingredient-reader.md`):** what follows "or" is another food only when it is not talk about the amount (`_AMOUNT_TALK`: more, less, so, as much as needed, enough to cover, according to taste, a little more, to your liking, whatever you like…); "100 g or more cheese" notes "or more". "each" lines: a trailing "or to taste" goes to every food's note, a trailing "each" is read like a leading one, up to 24 foods, and "each" is never left in a name. "500g/1lb 2oz" is 500 g with "1lb 2oz" in the note. "1 tbsp + 1 tsp sugar" and "1 cup plus 2 tbsp flour" keep the first amount and note "plus 1 tsp" (proposed, for cabledrawer). "a generous pinch of salt" is a pinch of salt, note "generous". A slash with an amount and a name on both sides ("2 tbsp ghee / 2 tbsp oil") is read as an "or" line; a slash between names alone stays other names.
- **Small:** `optional_step` and the recipe-name label patterns take a long run of spaces in time proportional to its length (the "(optional)" and "Recipe" end-of-line searches used to take the square of it; names and ingredient lines are also tidied to single spaces before they run); Serves over 99 and a time over 14,400 minutes in pasted text are left out of the boxes (the line is not read as a fact); a typed 10/3 is ten thirds (Check, the amount box, Add an item); two sections can't make recipes with one name (the sheet says so).

## Import from Mealie (0.9.5; cabledrawer 13 Nov: file only, never a network fetch)

Code: `backend/src/mealwright/mealie_file.py` (the reader). Tests: `tests/test_mealie_file.py`.

**The layout we read (proposed, for cabledrawer: written from Mealie's own export code for its
1.x and 2.x backups; nobody has tried a real file yet, so cabledrawer's helper may test one).**
Mealie's backup (Settings › Admin Settings › Backups › Create Backup) is one `.zip`:

- `database.json` at the top of the zip: an object with one key per database table, each a
  list of rows (column name → value). A `database.json` anywhere else is not taken.
- Photos at `data/recipes/<recipe id>/images/original.webp` (or `.jpg`, `.jpeg`, `.png`).
  Mealie keeps smaller copies beside it (`min-original`, `tiny-original`); only `original`
  is read, and cleaned like an upload.

Tables and columns used (anything else is ignored; a row or value of the wrong type is
skipped, never an error):

| Table | Columns |
|---|---|
| `recipes` (must be there) | `id`, `name`, `description`, `total_time`, `prep_time`, `perform_time` (or `cook_time`), `recipe_yield`, `recipe_yield_quantity`, `recipe_servings`, `org_url` |
| `recipes_ingredients` | `recipe_id`, `position`, `title` (a heading before the line), `quantity`, `unit_id`, `food_id`, `note`, `original_text` |
| `recipe_instructions` | `recipe_id`, `position`, `title` (a heading), `text` |
| `ingredient_foods` | `id`, `name` |
| `ingredient_units` | `id`, `name`, `abbreviation`, `use_abbreviation` |
| `recipe_nutrition` | `recipe_id`, `calories`, `protein_content`, `carbohydrate_content`, `fat_content`, `fiber_content` |
| `tags`, `recipes_to_tags` | `id`, `name`; `recipe_id`, `tag_id` |
| `group_meal_plans`, `shopping_lists`, `users`, `cookbooks` | counted only, for "Not brought in" |

What we assumed (all proposed, for cabledrawer):

- Ids are compared lower case without dashes (Mealie writes them either way).
- An ingredient line with a food or unit is put together as "quantity unit food, note"
  ("200 g Red lentils, rinsed"); one without is its note, or else the text it was first
  typed as. A unit uses its abbreviation when Mealie is set to show it.
- Times are typed in by hand in Mealie: "PT1H30M", "45", "1 hour 30 minutes" and "1h 30m"
  are read; anything else is left empty. Total time, or else prep plus cook.
- Serves: Mealie 2's `recipe_servings` when it's a whole number from 1 to 99, else read from
  the yield text like a page's; a yield that isn't servings ("12 cookies") is Makes.
- Tags come across; Mealie's categories don't (cabledrawer's list says tags). Mealie's user who
  added a recipe is never brought in, so the author is left empty.
- Only the foods some recipe uses are offered.

**Hostile files.** Nothing is ever unpacked to disk and no name from the zip is used as a
path. Limits (proposed, for cabledrawer; no real file measured yet): the upload at most 1 GiB;
at most 50,000 members and 4 GiB unpacked in all (as the zip says); `database.json` at most
32 MiB unpacked and nested at most 16 deep; each photo at most 15 MB (the photo upload's
limit); at most 5,000 recipes. Every read stops at its limit whatever the zip claims, so a
zip bomb is cut off. Only stored and deflated members are read, never encrypted ones. The
zip's index and `database.json` are read in a child process with its own budget (60 s of
processor time, 90 s by the clock, 768 MB of memory, the network guard on), the same way
as a recipe page (`page_budget`), one file at a time for the whole server.

**Bringing it in (`mealie_import.py`, `api/v1/mealie.py`).** cabledrawer 13 Nov: you see what's
in the file before anything is added; recipes with every line read are saved straight away,
only ones with unread lines go to Drafts ("From Mealie"); "Save all as they are"; it runs on
the server; one Undo for the whole import (7 days; recipes changed or cooked since are kept).
The choices below are proposed, for cabledrawer:

- **Who:** anyone in the household, the same as importing a recipe from a link (no role
  check), and an API token may too. `POST /api/v1/mealie-imports` takes the `.zip` itself as
  the body (at most 1 GB, this route only; streamed to a file in the data folder, one upload
  at a time for the whole server). Signed-out uploads are refused before a byte is read.
- **The preview** is kept with the file until "Bring in" or Cancel; sending another file
  lets the earlier one go, and a file nobody brings in is deleted after a day. One import
  runs at a time in a household (409 `mealie_busy`).
- **Already here:** same name (folded) and same source link; no link on both counts as the
  same. A Mealie draft still waiting counts too, so the same file twice makes no second draft.
- **Read:** a recipe is saved when every ingredient line is matched or a staple. New Mealie
  foods become ingredients first, marked by the import (`food.mealie_import_id`), so a line
  that names a Mealie food is read. Waits the reader suggests aren't added; the file's own
  times are used. Mealie drafts don't count towards the 50-draft limit; the 15 days still
  apply.
- **The job:** one thread per import. It holds the database's write lock only in short
  stretches (about half a second, `HOLD_SECONDS`, then the lock is left free for a tenth of a
  second), so other households' writes, and the household's own, get in while it runs (round
  1, S-H1). Slow work happens with no lock held: the ingredients' names are read once, and
  recipes are read and their photos cleaned 25 at a time (`PREPARE`) before the lock is
  taken to add them. Each stretch commits what it added and the import's results together,
  so a restart carries on where it stopped (`resume()` at start-up) and saves nothing twice.
  A recipe that fails is skipped and counted (the log says only the kind of failure, never
  the recipe's words); the import never stops half-way for one bad recipe. The file is
  deleted when it ends. Progress is asked for every few seconds (`GET /mealie-imports/{id}`),
  not sent as a live event. Today shows a note for a day after it finishes.
- **At most 5,000 new ingredients per import** (`MAX_NEW_FOODS`, proposed, for cabledrawer;
  round 1): the rest aren't added, so their lines aren't read and those recipes wait in Drafts.
  The preview's `foods_left_out` says how many; a restart counts the ones already made.
- **Cancel while it runs** (`DELETE /mealie-imports/{id}`, proposed, for cabledrawer; no button
  for it yet): it stops between two stretches; what came in stays, with the import's Undo
  (the import ends "done", `choices.stopped`).
- **Undo** (`POST /mealie-imports/{id}/undo`, 7 days, 410 `too_old` after): takes out the
  recipes (to Removed, as a delete does), the import's drafts, and its new ingredients.
  Kept: recipes changed (their version moved), cooked, planned, or used in another recipe
  since; ingredients used anywhere (pantry, a list, the plan, a recipe kept). No Recent
  changes entries: the import's own screen holds its Undo. It runs in stretches of 500 rows
  (`CHUNK`), each checked again under the lock; a stop part-way leaves the import to be undone
  again, which carries on.
- **Save all as they are** (`POST /mealie-imports/drafts/save-all`): every Mealie draft is
  saved, read lines linked and the rest as plain text (no ingredient, so never on the
  shopping list). They join the import's Undo. Saved in short stretches too, each draft
  checked again (still there, not deleted) inside its stretch.
