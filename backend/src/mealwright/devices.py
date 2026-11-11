"""A short, plain name for the device a sign-in came from: "iPhone · Safari" (PR A2).

Made once, from the browser's User-Agent, when someone signs in, for Settings' "Where you're
signed in" list. Only this short name is kept; the User-Agent itself is never stored or
logged. A part that isn't recognised is left out; with neither, there is no name.
"""

import re

# Checked in order: the first that matches wins (an iPad's Safari also says "Mac OS X",
# Edge also says "Chrome", Chrome also says "Safari").
_DEVICES: tuple[tuple[str, str], ...] = (
    (r"iPhone|iPod", "iPhone"),
    (r"iPad", "iPad"),
    (r"Android.*Mobile", "Android phone"),
    (r"Android", "Android tablet"),
    (r"CrOS", "Chromebook"),
    (r"Windows", "PC"),
    (r"Macintosh|Mac OS X", "Mac"),
    (r"Linux|X11", "Linux"),
)
_BROWSERS: tuple[tuple[str, str], ...] = (
    (r"Edg(e|A|iOS)?/", "Edge"),
    (r"OPR/|Opera", "Opera"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"Chrome/|CriOS/|Chromium/", "Chrome"),
    (r"Safari/", "Safari"),
)

LONGEST = 60  # the database column's length


def device_label(user_agent: str | None) -> str | None:
    """ "iPhone · Safari", "PC · Chrome", "Firefox", or None when nothing is recognised."""
    if not user_agent:
        return None
    text = user_agent[:512]  # nobody's real User-Agent is longer; keeps matching cheap
    device = next((name for pattern, name in _DEVICES if re.search(pattern, text)), None)
    browser = next((name for pattern, name in _BROWSERS if re.search(pattern, text)), None)
    parts = [part for part in (device, browser) if part]
    return " · ".join(parts)[:LONGEST] or None
