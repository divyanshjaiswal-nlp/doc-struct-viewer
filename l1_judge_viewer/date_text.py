"""
Dates written in PROSE, and the partial-ISO key each one stands for.

The date-events and doc-to-struct plates match dates that are already normalised. A
summary is not: it says `July 2024`, `7/28/24`, `2024-07-28` and `in 2024`, all in the same
paragraph. This module finds those spans and reduces each to the key it can be looked up
by -- `YYYY`, `YYYY-MM` or `YYYY-MM-DD` -- so a mention of a date and a date key in the
merged anchor index can be compared at whatever granularity each was written.

Two things it deliberately does NOT do:

  * a two-part numeric date with no four-digit year (`7/28`) is skipped. It is either
    mm/dd or mm/yy and the text alone cannot say which; guessing here would put a
    confident highlight on a date that may be a year out.
  * a bare four-digit number is only read as a year when it looks like one (19xx / 20xx)
    and is not carrying a unit -- `2000 mg` is a dose.

Everything it does find is validated as a real calendar date before it is returned, so
`13/45/2024` and `2024-02-30` are dropped rather than highlighted.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

# Month names and abbreviations -> number. `calendar` runs in the C locale here, so these
# are the English names; `sept` is the one common abbreviation it does not carry.
MONTH_NUMBERS: dict[str, int] = {
    name.lower(): number
    for source in (calendar.month_name, calendar.month_abbr)
    for number, name in enumerate(source)
    if name
}
MONTH_NUMBERS["sept"] = 9

# longest first: alternation is ordered, so without this `jan` would match and leave
# `uary` sitting outside the span
_MONTHS = "|".join(sorted((re.escape(name) for name in MONTH_NUMBERS), key=len, reverse=True))

# a four-digit number carrying one of these is a dose or a count, not a year
_UNITS = "mg|mcg|ug|g|kg|ml|cc|mm|cm|gy|iu|units?|cells|copies"

# Every dash a model writes, not just the ASCII one: L1 puts NON-BREAKING hyphens (U+2011)
# between the parts of a date so it does not wrap, and en/em dashes turn up too. An
# ASCII-only class silently misses `04‑23‑2024` entirely, which looks identical on
# screen to a date that simply has no key.
_DASHES = "‐‑‒–—―−"
_SEP = f"[-/.{_DASHES}]"        # inside a three-part date
_LINK = f"[-/{_DASHES}]"        # between a year and a month, where `.` would be a full stop
_RDASH = f"[-{_DASHES}]"        # between the two ends of a range -- a dash, never a slash

# Alternatives are ordered most specific first, and `finditer` never returns overlapping
# matches -- which is what keeps the `2024` inside `2024-07-28` from being found again as a
# bare year.
#
# The leading guard also excludes `/` and `.`, so a fragment of `112/1998` or `1.2024` is
# not read as a date. `-` is left out of it on purpose: a range written `2024-2025` should
# still yield both years.
_PATTERN = r"""
    (?<![\w/.])
    (?:
      (?P<rm1>\d{1,2}) \s*/\s* (?P<rd1>\d{1,2}) \s*RDASH\s*
      (?P<rm2>\d{1,2}) \s*/\s* (?P<rd2>\d{1,2}) \s*/\s* (?P<ry>\d{2,4})
    | (?P<y1>\d{4}) \s*SEP\s* (?P<m1>\d{1,2}) \s*SEP\s* (?P<d1>\d{1,2})
    | (?P<a2>\d{1,2}) \s*SEP\s* (?P<b2>\d{1,2}) \s*SEP\s* (?P<y2>\d{2,4}) (?!\s*/\s*\d)
    | (?P<m3>MONTHS)\.?\s+ (?P<d3>\d{1,2})(?:st|nd|rd|th)? \s*,?\s* (?P<y3>\d{4})
    | (?P<d4>\d{1,2})(?:st|nd|rd|th)?\s+ (?P<m4>MONTHS)\.?\s*,?\s* (?P<y4>\d{4})
    | (?P<m5>MONTHS)\.?\s*,?\s* (?P<y5>\d{4})
    | (?P<m6>\d{1,2}) \s*/\s* (?P<y6>\d{4})
    | (?P<y7>\d{4}) \s*LINK\s* (?P<m7>\d{1,2})
    | (?P<y8>(?:19|20)\d{2}) (?!\s*(?:UNITS)\b)
    )
    (?!\w)
"""

DATE_IN_TEXT = re.compile(
    _PATTERN.replace("MONTHS", _MONTHS).replace("UNITS", _UNITS)
            .replace("RDASH", _RDASH).replace("SEP", _SEP).replace("LINK", _LINK),
    re.IGNORECASE | re.VERBOSE,
)

# A two-digit year at or below this is 20xx, above it 19xx. Fixed rather than derived from
# today's date, so the same summary reads the same way next year.
CENTURY_PIVOT = 30

# a key already in the form this module produces
IS_KEY = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")


@dataclass(frozen=True)
class Mention:
    """One date as it was written, and the key it reduces to."""

    start: int
    end: int
    raw: str
    key: str

    @property
    def kind(self) -> str:
        """`year`, `month` or `day` -- how precisely the text gave it."""
        return {1: "year", 2: "month", 3: "day"}[len(self.key.split("-"))]


def _year(text: str) -> int | None:
    """A two- or four-digit year as a full one. Anything else is not a year."""
    if len(text) == 4:
        value = int(text)
        return value if 1900 <= value <= 2099 else None
    if len(text) == 2:
        value = int(text)
        return 2000 + value if value <= CENTURY_PIVOT else 1900 + value
    return None


def _key(year: int | None, month: int | None = None, day: int | None = None) -> str | None:
    """The lookup key, or None when the parts are not a real date."""
    if year is None:
        return None
    if month is None:
        return f"{year:04d}"
    if not 1 <= month <= 12:
        return None
    if day is None:
        return f"{year:04d}-{month:02d}"
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _month_day(first: int, second: int) -> tuple[int, int] | None:
    """
    (month, day) from a numeric pair.

    Month-first, because these are US oncology charts. Day-first is only read when the
    first number cannot be a month, which is the one case where the order is not a guess.
    """
    if 1 <= first <= 12 and 1 <= second <= 31:
        return first, second
    if 1 <= second <= 12 and 1 <= first <= 31:
        return second, first
    return None


def _month(name: str) -> int | None:
    return MONTH_NUMBERS.get(name.lower())


def _from_match(match: re.Match) -> str | None:
    """The key for whichever alternative matched, or None when it is not a date."""
    group = match.group

    if group("y1"):
        return _key(_year(group("y1")), int(group("m1")), int(group("d1")))

    if group("y2"):
        pair = _month_day(int(group("a2")), int(group("b2")))
        return _key(_year(group("y2")), *pair) if pair else None

    if group("y3"):
        return _key(_year(group("y3")), _month(group("m3")), int(group("d3")))

    if group("y4"):
        return _key(_year(group("y4")), _month(group("m4")), int(group("d4")))

    if group("y5"):
        return _key(_year(group("y5")), _month(group("m5")))

    if group("y6"):
        return _key(_year(group("y6")), int(group("m6")))

    if group("y7"):
        return _key(_year(group("y7")), int(group("m7")))

    if group("y8"):
        return _key(_year(group("y8")))

    return None


def _range_mentions(match: re.Match, text: str) -> list[Mention]:
    """
    The TWO dates in `01/14-01/23/2026`, each marked over its own span.

    A range writes the year once, at the far end, and the near end borrows it. Read as one
    date it becomes nonsense -- `01/14-01` parses as 14 January 2001, a confident highlight
    on a date 25 years from the right one, and the real dates are lost. Both ends are
    returned separately so each is marked and matched on its own.
    """
    year = _year(match.group("ry"))
    ends = (("rm1", "rd1", "rd1"), ("rm2", "rd2", "ry"))
    mentions = []

    for month_group, day_group, last_group in ends:
        key = _key(year, int(match.group(month_group)), int(match.group(day_group)))
        if not key:
            continue
        start, end = match.start(month_group), match.end(last_group)
        mentions.append(Mention(start, end, text[start:end], key))

    return mentions


def find_dates(text: str) -> list[Mention]:
    """Every date in `text`, in the order it is written, each with its lookup key."""
    text = text or ""
    mentions = []

    for match in DATE_IN_TEXT.finditer(text):
        if match.group("ry"):
            mentions.extend(_range_mentions(match, text))
            continue

        key = _from_match(match)
        if key:
            mentions.append(Mention(match.start(), match.end(), match.group(0), key))

    return mentions


def as_key(value: object) -> str:
    """
    A merged-index key in the same form the mentions carry.

    The anchors are supposed to be normalised already, so this is usually a no-op. When a
    key arrives as `07/28/2024` it is converted, and when it is not a date at all it is
    returned untouched -- an unparseable key still has to appear on screen.
    """
    text = str(value or "").strip()
    if IS_KEY.match(text):
        return text

    found = find_dates(text)
    return found[0].key if len(found) == 1 and found[0].raw == text else text
