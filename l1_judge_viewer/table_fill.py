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

EMPTY_CELL = "-"

# a separator row -- every cell is dashes, with or without alignment colons
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")


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

        width = max(len(cells) for cells in block)

        for offset, cells in enumerate(block):
            if all(_SEPARATOR_CELL.match(cell.strip()) for cell in cells):
                continue               # a separator row keeps its own dashes

            filled = [cell.strip() or EMPTY_CELL for cell in cells]
            filled += [EMPTY_CELL] * (width - len(filled))

            lines[start + offset] = "| " + " | ".join(filled) + " |"

    return "\n".join(lines)
