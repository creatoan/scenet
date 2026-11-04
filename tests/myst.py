"""Headings and sections of the documentation's Markdown, as MyST reads them.

`docs/conf.py` sets `myst_heading_anchors = 3`: every heading down to `###` has an anchor,
which a link and a gallery example's `doc:` name. A `####` heading has none, and belongs to
the section above it.
"""

import re
from dataclasses import dataclass
from pathlib import Path

#: The deepest heading with an anchor of its own.
DEEPEST = 3


@dataclass(frozen=True)
class Heading:
    """A heading: its level, its text as written, and the line it is on, counted from 0."""

    level: int
    text: str
    line: int

    @property
    def anchor(self) -> str:
        """Its anchor, as MyST makes it."""
        return slug(self.text)


@dataclass(frozen=True)
class Section:
    """A heading with an anchor, and its own text: what comes before the next such heading."""

    heading: Heading
    text: str


def slug(heading: str) -> str:
    """A heading's anchor as MyST makes it, by the rule `mdit_py_plugins.anchors` applies.

    Less its range of CJK ideographs, which no page here has. GitHub makes the same.
    """
    return re.sub(r"[^\w\- ]", "", heading.strip().lower().replace(" ", "-"))


def headings(text: str) -> list[Heading]:
    """Every heading down to `###` outside a fenced block, in order.

    A fence closes only on a run of its own character at least as long as the one that
    opened it, so a `#` comment in an example, or a script's own heading shown as its source,
    is not a heading.
    """
    found: list[Heading] = []
    fence = ""
    for number, line in enumerate(text.splitlines()):
        if fence:
            if re.fullmatch(rf"\s*{re.escape(fence[0])}{{{len(fence)},}}\s*", line):
                fence = ""
        elif opening := re.match(r"\s*(`{3,}|~{3,})", line):
            fence = opening.group(1)
        elif match := re.match(rf"(#{{1,{DEEPEST}}}) (.+)", line):
            found.append(Heading(len(match.group(1)), match.group(2), number))
    return found


def anchors(page: Path) -> set[str]:
    """The anchors a page has."""
    return {heading.anchor for heading in headings(page.read_text(encoding="utf-8"))}


def sections(text: str) -> list[Section]:
    """Each `##` and `###` section, with its own text, its `####` subsections included."""
    lines = text.splitlines()
    found = headings(text)
    ends = [heading.line for heading in found[1:]] + [len(lines)]
    return [
        Section(heading, "\n".join(lines[heading.line + 1 : end]))
        for heading, end in zip(found, ends, strict=True)
        if heading.level > 1
    ]
