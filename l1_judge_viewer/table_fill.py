"""
Blank-cell filling for tables, so the viewer shows what the MODEL was shown.

A MIRROR of `LineBasedDocFormatter._fill_table_cells` in
`nlp_backend/core/agents/doc_agent/doc_formatter/line_based_segment.py`. It is copied rather
than imported because that module reaches into the nlp_backend package (relative imports,
and a dependency chain that pulls in torch), which this viewer deliberately does not depend
on. KEEP THE TWO IN SYNC -- if they drift, the document on screen stops being the document
the extractor read, which is the one thing this page exists to show.

Why the formatter does this at all: a blank cell carries no token, so the model cannot
attend to it and has to INFER its column position. That inference is what produces borrowed
values and run-to-run inconsistency. A `-` makes the gap readable.

Line COUNT is untouched, so citation line numbers still line up.
"""
from __future__ import annotations

import re

# the word `empty` was tried here and made no difference -- see the note in
# LineBasedDocFormatter. Keep in sync with it.
EMPTY_CELL = "-"

# a separator row -- every cell is dashes, with or without alignment colons
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")

# mirrors LineBasedDocFormatter.MARK_DATE_COLUMNS -- keep the two the same
MARK_DATE_COLUMNS = True

# mirrors LineBasedDocFormatter.DATE_IN_CELL: write `<date>, <measure> = <value>` in every
# data cell instead of the `[n]` numbers, so nothing has to be looked up in the header
DATE_IN_CELL = True

# a cell holding a date: THREE parts only, so the decimals filling these tables (1.3, 0.70)
# and two-part forms like 112/67 are not read as dates
_DATE_CELL = re.compile(
    r"\b\d{1,4}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{1,4}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{1,2}\s*,?\s*\d{4}\b",
    re.IGNORECASE,
)


def _used_width(cells: list[str]) -> int:
    """
    How many columns the row actually USES -- trailing blanks do not count.

    `| a | b | c ||` is one pipe too many and parses as four cells whose last is empty;
    taking the table's width from the widest row would invent a fourth column across every
    row. A cell past the last one holding anything is punctuation, not a column.
    """
    used = len(cells)
    while used and not cells[used - 1].strip():
        used -= 1
    return used


def _date_columns(cells: list[str]) -> int | None:
    """
    The column index where this row's DATES begin, or None when it is not a date row.

    A header commonly names a few things before it starts naming dates -- `Component`, then
    `Ref Range & Units`, then one date per column. Those leading columns are real; what they
    are NOT is dates. What must hold is that once the dates START they run UNBROKEN to the
    end -- a gap or a stray label mid-run means the row is not describing what follows it.
    """
    head, rest = cells[0], [cell.strip() for cell in cells[1:]]

    # a header shorter than the body is padded out later; those tail cells are an artifact
    # of the fill, not columns the row declined to date
    while rest and not rest[-1]:
        rest.pop()

    # the first cell NAMES what the rows record, so it is not itself a date
    if _DATE_CELL.search(head):
        return None

    first = next((i for i, cell in enumerate(rest) if _DATE_CELL.search(cell)), None)
    if first is None:
        return None

    # unbroken to the end, and at least two -- a lone dated column is already unambiguous
    if len(rest) - first < 2 or not all(_DATE_CELL.search(c) for c in rest[first:]):
        return None

    return first + 1               # as an index into the whole row


def _column_labels(header: list[str], first_date: int) -> list:
    """
    What each column past the first BINDS its values to.

    A dated column contributes the date itself, lifted out of whatever else the heading says
    -- `1 d ago (5/28/25)` binds to `5/28/25`, leaving the relative expression behind. A
    leading column contributes its own heading, so a reference range stays visibly a
    reference range. A blank heading contributes nothing and its cells are left untouched.
    """
    labels = []
    for position, cell in enumerate(header[1:], 1):
        if position >= first_date:
            found = _DATE_CELL.search(cell)
            labels.append(found.group(0) if found else None)
        else:
            labels.append(cell if cell != EMPTY_CELL else None)
    return labels


def _row_cells(line: str) -> list[str] | None:
    """The cells of a table row, or None when the line is not one."""
    stripped = line.strip()

    # two pipes, not two cells: `| WBC |` is a real row of a two-column table whose value is
    # blank, and it yields ONE cell
    if not stripped.startswith("|") or stripped.count("|") < 2:
        return None

    body = stripped[1:]
    if body.endswith("|"):
        body = body[:-1]

    return body.split("|")


def fill_table_cells(text: str) -> str:
    """
    Give every blank cell in a table a visible `-`, and pad short rows out.

    EVERY block of consecutive pipe rows is treated on its OWN terms: its width is its own
    widest row, and nothing is carried in from the block before it -- no borrowed width, no
    page-break continuation, no date written into a cell that did not already hold one. So a
    table naming no dates is filled and padded like any other.
    """
    lines = text.split("\n")

    index = 0
    while index < len(lines):
        if _row_cells(lines[index]) is None:
            index += 1
            continue

        start = index
        while index < len(lines) and _row_cells(lines[index]) is not None:
            index += 1

        block = [_row_cells(line) for line in lines[start:index]]

        # a lone pipe line is not a table -- nothing to be consistent with, nothing to pad to
        if len(block) < 2:
            continue

        # separator rows say nothing about how many columns the table HAS -- they are drawn
        # by the html converter and routinely miscount -- so the width comes from the content
        # rows, and from what each of them actually uses
        content = [cells for cells in block
                   if not all(_SEPARATOR_CELL.match(c.strip()) for c in cells)]
        if not content:
            continue

        width = max(_used_width(cells) for cells in content)

        # a CLEAN date row -- a measure name and then dates all the way across -- gets its
        # cells numbered, so a value and its date carry the same `[n]` and matching them is
        # a lookup rather than a pipe count. It must also COVER the table: where a row carries
        # a value in a column the header never dated, numbering misplaces every value after
        top = content[0]
        first_date = _date_columns(top) if MARK_DATE_COLUMNS else None
        bound = first_date is not None and _used_width(top) == width

        # `[n]` numbers stay on the tables they always applied to -- dates from the second
        # column on. Written-in bindings also take the leading-label tables, because there
        # the leading column names ITSELF and cannot be mistaken for a date
        mark = bound and (DATE_IN_CELL or first_date == 1)

        # dates are taken VERBATIM -- month-first versus day-first is a whole-document
        # judgement the prompt makes, not this code
        labels = []
        if mark and DATE_IN_CELL:
            header = [cell.strip() or EMPTY_CELL for cell in top[:width]]
            header += [EMPTY_CELL] * (width - len(header))
            labels = _column_labels(header, first_date)

        for offset, cells in enumerate(block):
            if all(_SEPARATOR_CELL.match(cell.strip()) for cell in cells):
                continue               # a separator row keeps its own dashes

            # `cells[:width]` drops the stray-pipe tail; nothing past `width` is anything
            filled = [cell.strip() or EMPTY_CELL for cell in cells[:width]]
            filled += [EMPTY_CELL] * (width - len(filled))

            if mark and not DATE_IN_CELL:
                filled = [filled[0]] + [f"[{position}] {cell}"
                                        for position, cell in enumerate(filled[1:], 1)]
            elif mark and cells is not top:
                # every data cell restates what binds it and the measure it records; the
                # header row is left alone, it IS the row the labels came from
                measure = filled[0]
                filled = [measure] + [f"{label}, {measure} = {cell}" if label else cell
                                      for label, cell in zip(labels, filled[1:])]

            lines[start + offset] = "| " + " | ".join(filled) + " |"

    return "\n".join(lines)
