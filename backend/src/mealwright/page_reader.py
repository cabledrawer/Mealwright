"""Reading a recipe from a web page (spec section 6, "Recipe import, decided for 0.5").

This is the one place that knows how recipe pages are written, so it can be swapped for
another reader (recipe-scrapers is the spec's planned fallback, for 0.7 if pages still
fail) without touching anything else: a replacement only has to provide `read_page` and
return `PageRecipe`.

It reads schema.org `Recipe` data, which almost every recipe site includes for search
engines: JSON-LD first (`<script type="application/ld+json">`, including `@graph`, several
blocks, `@type` lists, `@id` references, `HowToSection` and `HowToStep`, and
`NutritionInformation`), then microdata (`itemscope` and `itemprop`, on older pages).
Python's standard library only (`html.parser`, `json`); nothing here goes online.

The page isn't the user's typing, so text is tidied rather than refused: HTML tags and
entities are removed, hidden characters (`names.has_hidden`) are taken out, and runs of
spaces become one. What can't be used is left out (a time over 10 days, a yield of 500
servings, a tag over 40 characters), never guessed.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from mealwright import names

# The recipe editor's limits (api/v1/recipe_schemas.py and spec section 6).
MAX_LINES = 200  # ingredient lines and headings together
MAX_STEPS = 100  # steps and headings together
MAX_STEP_WORK = 10_000  # parts of a method looked at, counting repeats (a real one: ~200)
MAX_TAGS = 20
MAX_TAG_CHARS = 40
MAX_NAME = 200
MAX_DESCRIPTION = 200
MAX_AUTHOR = 200
MAX_MINUTES = 14_400  # 10 days
MAX_SERVES = 99
MAX_MAKES = Decimal(1_000_000)
MAX_MAKES_UNIT = 30
MAX_NUTRIENT = Decimal(100_000)
MAX_HEADING = 60  # an ingredient line this short, ending in ":", is a section name
MAX_DEPTH = 256  # elements nested deeper than this are read as if they were siblings
MAX_NODES = 200_000  # elements and runs of text kept from one page (a real one has ~10,000)
MAX_START_TAG = 65_536  # characters in one start tag; a longer one is skipped whole
NUTRIENTS = ("kcal", "protein", "carbs", "fat", "fibre")


@dataclass(frozen=True)
class PageLine:
    """An ingredient line or a method step."""

    text: str  # as written on the page, whitespace tidied, HTML entities and tags removed
    heading: bool = False  # a section name ("For the tadka")


@dataclass(frozen=True)
class PageRecipe:
    name: str  # "" if the page names nothing at all
    description: str | None  # cut at 200 characters, at a word, with "…"
    author: str | None
    total_minutes: int | None  # totalTime, or prep + cook; ISO 8601 durations; ≤ 14,400
    serves: int | None  # 1 to 99, from recipeYield when it's servings or a bare number
    makes: tuple[Decimal, str] | None  # from recipeYield otherwise ("12 cookies")
    nutrition: dict[str, Decimal | None]  # kcal, protein, carbs, fat, fibre per serving
    tags: tuple[str, ...]  # recipeCategory + recipeCuisine only, never keywords; ≤ 20
    photo_url: str | None  # the main image, as an absolute address
    ingredients: tuple[PageLine, ...]  # ≤ 200 including headings
    steps: tuple[PageLine, ...]  # ≤ 100 including headings
    lines_cut: bool  # the page had more than 200 ingredient lines; the rest were dropped
    steps_cut: bool  # the page had more than 100 steps; the rest were dropped


def read_page(html: str, url: str) -> PageRecipe | None:
    """The recipe on a page, or None if the page has no recipe data (the screen then offers
    to paste the recipe's text). `url` is where the page came from, for relative links."""
    page = _parse(html, url)
    recipe = _from_json_ld(page) or _from_microdata(page)
    if recipe is None:
        return None
    return _build(recipe, page)


# --- The page as a tree -------------------------------------------------------------------

_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param"}
    | {"source", "track", "wbr"}
)
_BLOCK = frozenset(
    {"address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption"}
    | {"figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li"}
    | {"main", "nav", "ol", "p", "pre", "section", "table", "tbody", "td", "tfoot", "th"}
    | {"thead", "tr", "ul"}
)
_SKIP = frozenset({"script", "style", "template", "noscript", "svg"})


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node | str]


@dataclass
class _Page:
    root: _Node
    json_ld: list[str]
    base: str
    title: str
    og: dict[str, str]  # og:title, og:image


_NO_ATTRS: dict[str, str] = {}  # shared, never changed

# Where a start tag ends: the standard parser's own pattern (html.parser.locatetagend, Python
# 3.14), copied because it isn't public.
_TAG_END = re.compile(
    r"""
  [a-zA-Z][^\t\n\r\f />]*           # tag name
  [\t\n\r\f /]*                     # optional whitespace before attribute name
  (?:(?<=['"\t\n\r\f /])[^\t\n\r\f />][^\t\n\r\f /=>]*  # attribute name
    (?:[\t\n\r\f ]*=[\t\n\r\f ]*    # value indicator
      (?:'[^']*'                    # LITA-enclosed value
        |"[^"]*"                    # LIT-enclosed value
        |(?!['"])[^>\t\n\r\f ]*     # bare value
       )
     )?
    [\t\n\r\f /]*                   # possibly followed by a space
   )*
   >?
""",
    re.VERBOSE,
)


class _TreeBuilder(HTMLParser):
    """The page as a tree of elements and text, for microdata and the page's title. Past
    MAX_NODES (far more than any real page has) the tree stops growing, so a hostile page
    can't use up the server's memory; JSON-LD blocks are still collected to the end."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, [])
        self.stack = [self.root]
        self.json_ld: list[str] = []
        self._script: list[str] | None = None  # the JSON-LD block being read
        self._raw = False  # inside <script> or <style>: not page text
        self._overflow = 0  # elements opened past MAX_DEPTH, not on the stack
        self._room = MAX_NODES

    def check_for_whole_start_tag(self, i: int) -> int:
        # The standard check, looking no further than MAX_START_TAG characters. Unbounded, its
        # pattern keeps ~100 bytes of memory per attribute it passes, so one endless tag of tiny
        # attributes (`<a x='<a x='...`) would cost 100 times the page's size.
        rawdata = self.rawdata
        match = _TAG_END.match(rawdata, i + 1, i + MAX_START_TAG)
        if match and rawdata[match.end() - 1] == ">":
            return match.end()
        return -1

    def parse_starttag(self, i: int) -> int:
        edge = i + MAX_START_TAG
        if len(self.rawdata) > edge and self.check_for_whole_start_tag(i) < 0:
            # Longer than any real tag (a real one is a few thousand characters at most): skip
            # it whole, unread, to the next ">".
            end = self.rawdata.find(">", edge)
            return -1 if end < 0 else end + 1
        return super().parse_starttag(i)

    def _node(self, tag: str, attrs: list[tuple[str, str | None]]) -> _Node | None:
        if self._room <= 0:
            return None
        self._room -= 1
        node = _Node(tag, {k: v or "" for k, v in reversed(attrs)} if attrs else _NO_ATTRS, [])
        self.stack[-1].children.append(node)
        return node

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._raw = True
            kinds = [v or "" for k, v in attrs if k == "type"]
            kind = kinds[0].split(";")[0].strip().lower() if kinds else ""
            self._script = [] if tag == "script" and kind == "application/ld+json" else None
        node = self._node(tag, attrs)
        if tag in _VOID:
            return
        if node is not None and len(self.stack) < MAX_DEPTH:
            self.stack.append(node)
        else:
            self._overflow += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._node(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            if self._script is not None:
                self.json_ld.append("".join(self._script))
            self._script = None
            self._raw = False
        if self._overflow:
            self._overflow -= 1
            return
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth].tag == tag:
                del self.stack[depth:]
                return

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)
        elif not self._raw and self._room > 0:
            self._room -= 1
            self.stack[-1].children.append(data)


def _parse(html: str, url: str) -> _Page:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    root = builder.root
    base = url
    title = ""
    og: dict[str, str] = {}
    for node in _walk(root):
        if node.tag == "base" and base == url and node.attrs.get("href"):
            joined = urljoin(url, node.attrs["href"].strip())
            if urlsplit(joined).scheme in {"http", "https"}:
                base = joined
        elif node.tag == "title" and not title:
            title = _text_of(node)
        elif node.tag == "meta":
            key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
            if key in {"og:title", "og:image"} and key not in og:
                og[key] = node.attrs.get("content", "")
    return _Page(root, builder.json_ld, base, title, og)


def _walk(node: _Node) -> Iterator[_Node]:
    """Every element under `node`, in page order (without recursion)."""
    pending: list[_Node] = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(c for c in reversed(current.children) if isinstance(c, _Node))


def _text_of(node: _Node) -> str:
    """An element's text, with a line break around each block (paragraphs, list items)."""
    parts: list[str] = []

    def add(current: _Node) -> None:
        if current.tag in _SKIP:
            return
        block = current.tag in _BLOCK
        if block:
            parts.append("\n")
        for child in current.children:
            if isinstance(child, str):
                parts.append(child)
            else:
                add(child)
        if block:
            parts.append("\n")

    add(node)
    return "".join(parts)


# --- JSON-LD ------------------------------------------------------------------------------

_JSON_WRAPPERS = re.compile(
    r"^\s*(?:<!--|//\s*<!\[CDATA\[|<!\[CDATA\[)|(?:-->|//\s*\]\]>|\]\]>)\s*$"
)

type _Item = dict[str, object]


def _short(key: str) -> str:
    """A property name without its vocabulary: "schema:name" or "http://schema.org/name" →
    "name". Keys starting with "@" are kept as they are."""
    if key.startswith("@"):
        return key
    return re.split(r"[/:#]", key.rstrip("/"))[-1]


def _normalised(value: object) -> object:
    if isinstance(value, dict):
        return {_short(str(k)): _normalised(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalised(v) for v in value]
    return value


def _types(item: _Item) -> set[str]:
    kinds = item.get("@type")
    found = kinds if isinstance(kinds, list) else [kinds]
    return {_short(k) for k in found if isinstance(k, str)}


def _from_json_ld(page: _Page) -> _Recipe | None:
    blocks: list[object] = []
    for raw in page.json_ld:
        try:
            blocks.append(_normalised(json.loads(_JSON_WRAPPERS.sub("", raw), strict=False)))
        except ValueError, RecursionError:
            continue  # a broken block: the others may still hold the recipe
    ids: dict[str, _Item] = {}
    recipes: list[_Item] = []
    for item in _items(blocks):
        if isinstance(item.get("@id"), str) and len(item) > 1:
            ids.setdefault(str(item["@id"]), item)
        if "Recipe" in _types(item):
            recipes.append(item)
    if not recipes:
        return None
    # The first recipe with ingredients or a method (a page can list others it links to).
    best = next(
        (r for r in recipes if r.get("recipeIngredient") or r.get("recipeInstructions")),
        recipes[0],
    )
    return _Recipe(best, ids)


def _items(value: object, depth: int = 0) -> Iterator[_Item]:
    """Every object inside the JSON-LD (in @graph, lists, or as another object's value)."""
    if depth > 64:
        return
    if isinstance(value, list):
        for v in value:
            yield from _items(v, depth + 1)
    elif isinstance(value, dict):
        yield value
        for v in value.values():
            if isinstance(v, (dict, list)):
                yield from _items(v, depth + 1)


# --- Microdata -------------------------------------------------------------------------------

_SRC_TAGS = frozenset({"audio", "embed", "iframe", "img", "source", "track", "video"})
_HREF_TAGS = frozenset({"a", "area", "link"})


def _from_microdata(page: _Page) -> _Recipe | None:
    scopes = [
        node
        for node in _walk(page.root)
        if "itemscope" in node.attrs
        and any(_short(t) == "Recipe" for t in node.attrs.get("itemtype", "").split())
    ]
    if not scopes:
        return None
    recipes = [_microdata_item(node, page.base) for node in scopes]
    best = next(
        (r for r in recipes if r.get("recipeIngredient") or r.get("ingredients")),
        recipes[0],
    )
    return _Recipe(best, {})


def _microdata_item(scope: _Node, base: str, depth: int = 0) -> _Item:
    """An itemscope as a JSON-LD-like object: {"@type": [...], "name": ["…"], …}."""
    found: dict[str, list[object]] = {}
    pending = [c for c in reversed(scope.children) if isinstance(c, _Node)]
    while pending:
        node = pending.pop()
        props = node.attrs.get("itemprop", "").split()
        nested = "itemscope" in node.attrs
        if props:
            value: object
            if nested and depth < 16:
                value = _microdata_item(node, base, depth + 1)
            else:
                value = _microdata_value(node, base)
            for prop in props:
                found.setdefault(_short(prop), []).append(value)
        if not nested:  # a nested item's properties are its own
            pending.extend(c for c in reversed(node.children) if isinstance(c, _Node))
    item: _Item = {"@type": [_short(t) for t in scope.attrs.get("itemtype", "").split()]}
    item.update(found)
    return item


def _microdata_value(node: _Node, base: str) -> str:
    attrs = node.attrs
    if node.tag == "meta":
        return attrs.get("content", "")
    if node.tag in _SRC_TAGS:
        return urljoin(base, attrs.get("src", "").strip())
    if node.tag in _HREF_TAGS:
        return urljoin(base, attrs.get("href", "").strip())
    if node.tag == "object":
        return urljoin(base, attrs.get("data", "").strip())
    if node.tag in {"data", "meter"} and "value" in attrs:
        return attrs["value"]
    if node.tag == "time" and "datetime" in attrs:
        return attrs["datetime"]
    if "content" in attrs:  # not in the standard, but common on older pages
        return attrs["content"]
    return _text_of(node)


# --- From recipe data to PageRecipe ---------------------------------------------------------


class _Recipe:
    """A Recipe object from JSON-LD or microdata, with `@id` references followed."""

    def __init__(self, item: _Item, ids: dict[str, _Item]) -> None:
        self.item = item
        self.ids = ids

    def values(self, *keys: str) -> list[object]:
        found: list[object] = []
        for key in keys:
            found.extend(self.flat(self.item.get(key)))
        return found

    def flat(self, value: object, depth: int = 0) -> list[object]:
        """A value as a list, with nested lists opened (a few deep) and references
        followed."""
        if value is None:
            return []
        if not isinstance(value, list):
            return [self.follow(value)]
        out: list[object] = []
        for v in value:
            if not isinstance(v, list):
                out.append(self.follow(v))
            elif depth < 4:
                out.extend(self.flat(v, depth + 1))
        return out

    def follow(self, value: object) -> object:
        if isinstance(value, dict) and set(value) <= {"@id", "@type"}:
            target = self.ids.get(str(value.get("@id")))
            if target is not None:
                return target
        return value

    def text(self, *keys: str) -> str | None:
        for value in self.values(*keys):
            if isinstance(value, dict):
                value = _field(value, "name", "text")
            if _is_text(value):
                text = _one_line(value)
                if text:
                    return text
        return None


def _is_text(value: object) -> bool:
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def _field(item: _Item, *keys: str) -> object:
    """The first of `keys` an object has, as one value (microdata gives lists: the first
    text in the list)."""
    for key in keys:
        value = item.get(key)
        if isinstance(value, list):
            value = next((v for v in value if _is_text(v) and str(v).strip()), None)
        if value is not None and value != "":
            return value
    return None


def _build(recipe: _Recipe, page: _Page) -> PageRecipe | None:
    ingredients = _ingredients(recipe)
    steps = _steps(recipe)
    if not ingredients and not steps:
        return None
    name = recipe.text("name", "headline") or _one_line(page.og.get("og:title", ""))
    name = name or _one_line(page.title)
    description = recipe.text("description")
    serves, makes = _yield(recipe)
    return PageRecipe(
        name=_cut(name, MAX_NAME),
        description=_cut(description, MAX_DESCRIPTION) if description else None,
        author=_author(recipe),
        total_minutes=_total_minutes(recipe),
        serves=serves,
        makes=makes,
        nutrition=_nutrition(recipe),
        tags=_tags(recipe),
        photo_url=_photo(recipe, page),
        ingredients=tuple(ingredients[:MAX_LINES]),
        steps=tuple(steps[:MAX_STEPS]),
        lines_cut=len(ingredients) > MAX_LINES,
        steps_cut=len(steps) > MAX_STEPS,
    )


# --- Text ----------------------------------------------------------------------------------

_TAG = re.compile(r"<[A-Za-z/!][^<>]*>")  # never runs across another "<": linear time
_WHITESPACE_BREAKS = "\t\r\x0b\x0c\x85\u2028\u2029"


def _clean(value: object) -> str:
    """Text as shown on the page: entities decoded (sites often encode them twice), tags
    removed (with a line break around paragraphs and list items) and hidden characters
    taken out. Line breaks are kept; the caller decides what they mean."""
    text = value if isinstance(value, str) else str(value)
    for _ in range(2):
        if "&" not in text:
            break
        text = unescape(text)
    if _TAG.search(text):
        builder = _TreeBuilder()
        builder.feed(text)
        builder.close()
        text = _text_of(builder.root)
    return _strip_hidden(text)


def _strip_hidden(text: str) -> str:
    """Hidden characters taken out (`names.has_hidden`: control and invisible formatting
    characters), with a space for the ones that break lines or words. Joiners and flag
    emoji (🏴 with its tag letters) are kept, as `names` allows them."""
    if not names.has_hidden(text, newlines=True):
        return text
    kept: list[str] = []
    index = 0
    while index < len(text):
        end = names._flag_end(text, index)  # the same rule as has_hidden
        if end > index:
            kept.append(text[index:end])
            index = end
            continue
        char = text[index]
        index += 1
        if char in _WHITESPACE_BREAKS:
            kept.append(" ")
        elif char == "\n" or not names.has_hidden(char):
            kept.append(char)
    return "".join(kept)


def _one_line(value: object) -> str:
    return " ".join(_clean(value).split())


def _lines(value: object) -> list[str]:
    return [line for line in (" ".join(p.split()) for p in _clean(value).split("\n")) if line]


def _cut(text: str, limit: int) -> str:
    """At most `limit` characters, cut at a word with "…"."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-\u2013\u2014") + "…"


# --- Ingredients and method ------------------------------------------------------------------

_HAS_DIGIT = re.compile(r"\d")


def _ingredients(recipe: _Recipe) -> list[PageLine]:
    lines: list[PageLine] = []
    for value in recipe.values("recipeIngredient") or recipe.values("ingredients"):
        if isinstance(value, dict):
            value = _field(value, "name", "text")
        if not _is_text(value):
            continue
        for text in _lines(value):
            if text.endswith(":") and len(text) <= MAX_HEADING and not _HAS_DIGIT.search(text):
                heading = text.rstrip(":").strip()
                if heading:
                    lines.append(PageLine(heading, heading=True))
            else:
                lines.append(PageLine(text))
        if len(lines) > MAX_LINES:
            break
    return lines


def _steps(recipe: _Recipe) -> list[PageLine]:
    steps: list[PageLine] = []
    work = [MAX_STEP_WORK]
    for value in recipe.values("recipeInstructions"):
        _add_steps(recipe, value, steps, 0, work)
        if len(steps) > MAX_STEPS:
            break
    return steps


def _add_steps(
    recipe: _Recipe, value: object, steps: list[PageLine], depth: int, work: list[int]
) -> None:
    """`work` counts down the parts looked at. A section can list itself, or another
    section many times, by reference; without a limit, a few nameless ones would be walked
    billions of times while adding no step."""
    if len(steps) > MAX_STEPS or depth > 8 or work[0] <= 0:
        return
    work[0] -= 1
    if isinstance(value, str):
        steps.extend(PageLine(text) for text in _lines(value))
        return
    if not isinstance(value, dict):
        return
    kinds = _types(value)
    children = recipe.flat(value.get("itemListElement"))
    work[0] -= len(children)
    if "HowToSection" in kinds or ("HowToStep" not in kinds and children):
        heading = _one_line(_field(value, "name") or "")
        if heading:
            steps.append(PageLine(heading, heading=True))
        for child in children:
            _add_steps(recipe, recipe.follow(child), steps, depth + 1, work)
        return
    text = _one_line(_field(value, "text", "name") or "")
    if text:
        steps.append(PageLine(text))
    else:  # a step made of directions
        parts = [
            _one_line(_field(c, "text") or "")
            for c in (recipe.follow(c) for c in children)
            if isinstance(c, dict)
        ]
        joined = " ".join(p for p in parts if p)
        if joined:
            steps.append(PageLine(joined))


# --- Times ------------------------------------------------------------------------------------

_NUMBER = r"(\d+(?:[.,]\d+)?)"
_DURATION = re.compile(
    rf"^P(?:{_NUMBER}W)?(?:{_NUMBER}D)?(?:T(?:{_NUMBER}H)?(?:{_NUMBER}M)?(?:{_NUMBER}S)?)?$",
    re.IGNORECASE,
)
_DURATION_MINUTES = (Decimal(10_080), Decimal(1_440), Decimal(60), Decimal(1), Decimal(1) / 60)


def _minutes(value: object) -> int | None:
    """An ISO 8601 duration ("PT1H30M", "P1DT2H", "PT0.5H") in whole minutes. A bare number
    counts as minutes."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        total = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            total = Decimal(text)
        else:
            match = _DURATION.match(text)
            if not match or not any(match.groups()) or text.upper().endswith("T"):
                return None
            total = sum(
                (
                    Decimal(part.replace(",", ".")) * size
                    for part, size in zip(match.groups(), _DURATION_MINUTES, strict=True)
                    if part
                ),
                Decimal(0),
            )
    else:
        return None
    if not total.is_finite():
        return None
    minutes = int(total.to_integral_value(ROUND_HALF_UP))
    return minutes if 0 < minutes <= MAX_MINUTES else None


def _total_minutes(recipe: _Recipe) -> int | None:
    total = _first_minutes(recipe, "totalTime")
    if total is not None:
        return total
    parts = [m for m in (_first_minutes(recipe, k) for k in ("prepTime", "cookTime")) if m]
    if not parts or sum(parts) > MAX_MINUTES:
        return None
    return sum(parts)


def _first_minutes(recipe: _Recipe, key: str) -> int | None:
    for value in recipe.values(key):
        minutes = _minutes(value)
        if minutes is not None:
            return minutes
    return None


# --- Serves and Makes ----------------------------------------------------------------------------

_YIELD = re.compile(
    r"^(?:(serves|makes|yields?|for)\s*:?\s*)?(?:about\s+|approx\.?\s+)?"
    r"(\d+(?:[.,]\d+)?)(?:\s*(?:-|\u2013|\u2014|to)\s*\d+(?:[.,]\d+)?)?\s*(.*)$",
    re.IGNORECASE,
)
_SERVINGS = frozenset(
    {"serving", "servings", "serves", "portion", "portions", "people", "person", "persons"}
    | {"pax"}
)


def _yield(recipe: _Recipe) -> tuple[int | None, tuple[Decimal, str] | None]:
    """Serves (servings, portions or people, or a bare number) and Makes (anything else,
    "12 cookies"), from the first yield that gives each. In a range the first number is
    used ("Serves 4 to 6" → 4). A bare number that only repeats the Makes amount (["24",
    "24 cookies"]) isn't taken as Serves."""
    serves: int | None = None
    bare: int | None = None
    makes: tuple[Decimal, str] | None = None
    for value in recipe.values("recipeYield", "yield"):
        if not _is_text(value):
            continue
        match = _YIELD.match(_one_line(value))
        if not match:
            continue
        prefix = (match.group(1) or "").lower()
        amount = Decimal(match.group(2).replace(",", "."))
        unit = re.split(r"[(\[]", match.group(3))[0].strip(" .,;:")
        first_word = unit.split(" ")[0].lower() if unit else ""
        whole = amount == amount.to_integral_value() and 1 <= amount <= MAX_SERVES
        if prefix in {"serves", "for"} or first_word in _SERVINGS:
            if serves is None and whole:
                serves = int(amount)
        elif not unit:
            if bare is None and whole and prefix != "makes":
                bare = int(amount)
        elif (
            makes is None
            and 0 < amount <= MAX_MAKES
            and len(unit) <= MAX_MAKES_UNIT
            and any(c.isalpha() for c in unit)
        ):
            makes = (_three_places(amount), unit)
    if serves is None and bare is not None and (makes is None or makes[0] != bare):
        serves = bare
    return serves, makes


# --- Nutrition ------------------------------------------------------------------------------------

_NUTRITION_KEYS = {
    "kcal": "calories",
    "protein": "proteinContent",
    "carbs": "carbohydrateContent",
    "fat": "fatContent",
    "fibre": "fiberContent",
}
_AMOUNT = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:[.,](\d+))?(?:[eE]([+-]?\d+))?\s*([a-zA-Zµμ]*)"
)


def _nutrition(recipe: _Recipe) -> dict[str, Decimal | None]:
    found: dict[str, Decimal | None] = dict.fromkeys(NUTRIENTS)
    facts = next((v for v in recipe.values("nutrition") if isinstance(v, dict)), None)
    if facts is None:
        return found
    for key, field in _NUTRITION_KEYS.items():
        for value in recipe.flat(facts.get(field)):
            amount = _nutrient(value, energy=key == "kcal")
            if amount is not None:
                found[key] = amount
                break
    return found


def _nutrient(value: object, energy: bool) -> Decimal | None:
    """The first number in "250 kcal", "12.5 g", "1,200 kcal", "1.5e2 kcal" or 12. Kilojoules
    become kilocalories, milligrams grams. Unknown is None, never 0."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = Decimal(str(value))  # str(1e300) is "1e+300": never read as text
        unit = ""
        if not amount.is_finite():
            return None
    elif isinstance(value, str):
        match = _AMOUNT.search(_one_line(value))
        if not match:
            return None
        whole, fraction, power = match.group(1).replace(",", ""), match.group(2), match.group(3)
        if power and len(power.lstrip("+-")) > 2:
            return None  # "1e300": far too big or too small to be real
        amount = Decimal((f"{whole}.{fraction}" if fraction else whole) + f"e{power or 0}")
        unit = match.group(4).lower()
    else:
        return None
    if energy and unit == "kj":
        amount /= Decimal("4.184")
    elif not energy and unit in {"mg"}:
        amount /= 1000
    elif not energy and unit in {"µg", "μg", "mcg"}:
        amount /= 1_000_000
    if amount < 0 or amount > MAX_NUTRIENT:
        return None
    return _three_places(amount)


def _three_places(amount: Decimal) -> Decimal:
    """Rounded to 3 decimal places, without trailing zeros ("12.500" → 12.5, 100 → 100)."""
    rounded = amount.quantize(Decimal("0.001"), ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return rounded.quantize(Decimal(1))
    return rounded.normalize()


# --- Author, tags and photo ----------------------------------------------------------------------


def _author(recipe: _Recipe) -> str | None:
    for value in recipe.values("author", "creator"):
        if isinstance(value, dict):
            value = _field(value, "name")
        if isinstance(value, str):
            text = _one_line(value)
            if text:
                return _cut(text, MAX_AUTHOR)
    return None


def _tags(recipe: _Recipe) -> tuple[str, ...]:
    """The page's categories, then its cuisines; never its keywords."""
    tags: list[str] = []
    seen: set[str] = set()
    for value in recipe.values("recipeCategory", "recipeCuisine"):
        if isinstance(value, dict):
            value = _field(value, "name")
        if not isinstance(value, str):
            continue
        for part in _one_line(value).split(","):
            tag = part.strip()
            if not tag or len(tag) > MAX_TAG_CHARS or tag.casefold() in seen:
                continue
            seen.add(tag.casefold())
            tags.append(tag)
            if len(tags) == MAX_TAGS:
                return tuple(tags)
    return tuple(tags)


def _photo(recipe: _Recipe, page: _Page) -> str | None:
    """The recipe's first image (a link, a list, or an ImageObject), else the page's own
    preview image, as an absolute http or https address."""
    candidates: list[object] = []
    for value in recipe.values("image", "thumbnailUrl"):
        if isinstance(value, dict):
            candidates.extend(recipe.flat(value.get("url") or value.get("contentUrl")))
        else:
            candidates.append(value)
    candidates.append(page.og.get("og:image"))
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        text = _one_line(candidate)
        if not text:
            continue
        address = urljoin(page.base, text)
        parts = urlsplit(address)
        if parts.scheme in {"http", "https"} and parts.hostname:
            return address
    return None
