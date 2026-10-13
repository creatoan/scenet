"""A frontend for comic script, the format writers already use.

Checked before building this: Fountain has no native panel, caption or SFX support,
and there is no standardised comic script format at all. But the informal industry
convention is stable across publishers -- `PANEL 1`, a prose description, a character
cue in capitals, the dialogue beneath it -- so that is what this parses.

**The honest limitation.** A prose description like "Alice and Bob face each other on
a rainy street corner" cannot be compiled. Turning that into staging needs natural
language understanding, and guessing would produce panels that are confidently wrong
-- far worse than refusing. So descriptions are preserved but not interpreted, and
anything the compiler must know is declared explicitly: cast and staging in a
front-matter block, per-panel settings as `@` directives.

    ---
    cast:
      ALICE: {reference: alice, at: left_third}
      BOB:   {reference: bob,   at: right_third}
    staging:
      - ALICE left_of BOB
    ---

    PANEL 1
    @shot: full_shot
    CAPTION: Midnight. The docks.
    Alice and Bob face each other on a rainy street corner.

    ALICE
    You forgot your umbrella!

    BOB (whisper)
    I know.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scenet.compose import merge
from scenet.errors import PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.common import errors_of, normalise, rule_for_pydantic, summarise
from scenet.ir import BalloonKind, CaptionKind, PanelIR, SfxSize
from scenet.safe_yaml import DuplicateKeyError, describe, load

# Leading blank lines are tolerated. A script pasted out of an editor or produced by a
# templating step very often starts with one, and refusing it would be a baffling
# failure for a file that looks identical to a working one.
FRONT_MATTER = re.compile(r"^\s*---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)
# The label is everything up to an optional trailing colon or full stop -- `PANEL 1:` and
# Dark Horse's `Panel 1.` both name panel `1`. A greedy `\S+` used to take the colon, so
# the panel was called `1:` and `scenet build` wrote a file Windows cannot hold.
PANEL_HEADING = re.compile(r"^PANEL\s+(?P<label>[^\s:]+?)\s*[.:]?\s*$", re.IGNORECASE)
# Dark Horse's `Panel 1. Alice and Bob on a corner.`: the description on the heading's own
# line, after a full stop, a colon, a dash or a spaced hyphen.
PANEL_WITH_DESCRIPTION = re.compile(
    r"^PANEL\s+(?P<label>[^\s.:\u2014\u2013-]+)\s*(?:[.:\u2014\u2013]|\s-)\s*(?P<description>\S.*)$",
    re.IGNORECASE,
)
# A label a panel with a description on its line may have: `1`, `4B`, `C`.
NUMBER_LIKE = re.compile(r"\d+[^\W\d_]?|[^\W\d_]")
# Dark Horse's `PAGE ONE (five panels)`. The label may be several words when they make a
# number, `PAGE TWENTY ONE`; the parenthetical may state the count, or be a note.
PAGE_HEADING = re.compile(
    r"^PAGE\s+(?P<label>[^\s:()]+(?:[\s-]+[^\s:()]+)*?)\s*(?:\((?P<note>[^)]*)\))?\s*[.:]?\s*$",
    re.IGNORECASE,
)
# The count in a PAGE heading's parenthetical: `five panels`, `1 panel`.
PANEL_COUNT = re.compile(r"^(?P<count>\w+(?:[\s-]\w+)?)\s+panels?$", re.IGNORECASE)
# Markdown a writer may put around a label: `## PANEL 2`, `**PANEL 2**`, `**ALICE:**`.
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+")
BOLD_LABEL = re.compile(r"^(\*\*|__)(\S(?:.*?\S)?)\1(.*)$")
# A Markdown horizontal rule, `---` or `* * *`, which reads as the blank line it looks like.
# `--` is two hyphens, Dark Horse's carry-over mark, and is not one.
HORIZONTAL_RULE = re.compile(r"^([-*_])(?:[ \t]*\1){2,}$")
DIRECTIVE = re.compile(r"^@(\w+)\s*:\s*(.+)$")
# A cue is a character name in capitals, optionally followed by a parenthetical. Any
# letter may start it, not only A to Z: `HÉLÈNE` is a name in capitals, and her lines used
# to be filed as prose. Whether the letters are capitals is `_looks_like_a_cue`'s test.
CUE = re.compile(r"^([^\W\d_][\w '.-]*?)\s*(?:\(([^)]*)\))?\s*:?\s*$")
# `CAPTION: Midnight. The docks.`, optionally `CAPTION (monologue): ...`. The text is
# on the same line, which is what distinguishes a caption from a character cue.
CAPTION_LINE = re.compile(r"^CAPTION\s*(?:\(([^)]*)\))?\s*:\s*(.+)$", re.IGNORECASE)
# A CAPTION line with nothing after the colon. It matches `CUE` perfectly, so without
# this it would be read as a character called CAPTION and quietly swallow the next
# line as their dialogue.
BARE_CAPTION = re.compile(r"^CAPTION\s*(?:\(([^)]*)\))?\s*:?\s*$", re.IGNORECASE)
# `SFX: BLAM`, optionally `SFX (BOB, large): BLAM` -- who it comes from, how loud. The
# sound on the same line.
SFX_LINE = re.compile(r"^SFX\s*(?:\(([^)]*)\))?\s*:\s*(.+)$", re.IGNORECASE)
# Dark Horse's form: `SFX:` as a cue, the sound on the next line. Without this it is a
# character called SFX, and the sound would be lettered in a balloon.
BARE_SFX = re.compile(r"^SFX\s*(?:\(([^)]*)\))?\s*:?\s*$", re.IGNORECASE)

# Parentheticals a letterer would act on. Anything else is a performance note for the
# artist and is not something the compiler can represent.
KIND_MODIFIERS = {
    "whisper": BalloonKind.WHISPER,
    "whispering": BalloonKind.WHISPER,
    "shout": BalloonKind.SHOUT,
    "shouting": BalloonKind.SHOUT,
    "yell": BalloonKind.SHOUT,
    "yelling": BalloonKind.SHOUT,
    "thought": BalloonKind.THOUGHT,
    "thinking": BalloonKind.THOUGHT,
}

# The parenthetical on a CAPTION line, which says what the box is doing. Spelled the
# same as the IR's own vocabulary, since a writer typing `(monologue)` means the thing
# the letterers call a monologue.
CAPTION_KINDS = {kind.value: kind for kind in CaptionKind}

# How loud an SFX is, as its parenthetical may say.
SFX_SIZES = {size.value: size for size in SfxSize}

# Directives that name a camera property rather than a top-level panel key.
CAMERA_DIRECTIVES = {"shot", "angle"}

# Page numbers as scripts spell them. Dark Horse's format writes `PAGE ONE`, and a page
# that repeats its panel numbers is named after the page, so `PAGE TWO` has to give the
# `2` a writer would say aloud. A closed table rather than a dependency: page counts are
# small, and the runtime is eight packages on purpose.
_UNIT_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TEN_WORDS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_UNITS = {word: value for value, word in enumerate(_UNIT_WORDS)}
_TENS = {word: 10 * value for value, word in enumerate(_TEN_WORDS, start=2)}


@dataclass
class _PanelDraft:
    """One panel being accumulated as the script is read.

    A typed accumulator rather than a bare dict: the script body contributes several
    kinds of thing -- dialogue, captions, directives, prose -- and keeping them apart
    until the end makes it obvious that prose never reaches the compiler.
    """

    #: The file line of the PANEL heading, which is where a fault found only once the
    #: whole panel is assembled -- a bad `@shot:` value, say -- gets reported.
    line: int
    #: What follows `PANEL`: `1` for `PANEL 1`.
    label: str
    #: The page it is on, as `_page_label` reads the PAGE heading above it, or `None`
    #: before the first one. Only used to tell apart panels whose labels repeat.
    page: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    camera: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    description: list[str] = field(default_factory=list)
    #: The file line each event was written on, in step with `events`: a cue's line for
    #: a speech, not the line of its text, since the cue is what names the speaker.
    event_lines: list[int] = field(default_factory=list)
    #: Where each directive was written, by the path in the panel it sets: `("camera",
    #: "shot")` for `@shot:`, `("setting",)` for `@setting:`.
    directive_lines: dict[tuple[str, ...], int] = field(default_factory=dict)

    def add(self, event: dict[str, Any], line: int) -> None:
        """Append an event, remembering the line it was written on."""
        self.events.append(event)
        self.event_lines.append(line)

    def line_of(self, loc: tuple[str | int, ...]) -> int:
        """The file line that holds whatever `loc`, a path within the panel, points at.

        An event is on its own line, and a value a directive set is on the directive's.
        Anything else -- the front matter's cast, say -- was not written in this panel,
        and is reported at its heading.

        Example:
            >>> draft = _PanelDraft(line=4, label="1")
            >>> draft.add({"say": {}}, 6)
            >>> draft.directive_lines[("camera", "shot")] = 5
            >>> [
            ...     draft.line_of(loc)
            ...     for loc in [("script", 0, "say", "by"), ("camera", "shot"), ("cast", "A", "at")]
            ... ]
            [6, 5, 4]
        """
        event = loc[1] if len(loc) > 1 and loc[0] == "script" else None
        if isinstance(event, int) and 0 <= event < len(self.event_lines):
            return self.event_lines[event]
        written = [key for key in self.directive_lines if loc[: len(key)] == key]
        if written:
            return self.directive_lines[max(written, key=len)]
        return self.line

    def as_document(self) -> dict[str, Any]:
        """The parts a panel can actually be compiled from.

        `description` is authorial prose the compiler cannot act on, so it is left out
        rather than being passed along and rejected as an unknown key.
        """
        document: dict[str, Any] = dict(self.settings)
        if self.camera:
            document["camera"] = {**document.get("camera", {}), **self.camera}
        document["script"] = self.events
        return document


def _looks_like_a_cue(line: str) -> bool:
    """Whether a line is a character cue rather than prose.

    Cues are conventionally set in capitals, which is the only signal available, so
    the line must also be short to avoid mistaking a shouted description for a cue.

    Only the *name* is tested for capitals. The parenthetical is a performance note
    and is conventionally lower case -- `BOB (whisper)` is a cue, and testing the
    whole line would silently drop every piece of modified dialogue in the script.
    """
    if not line or len(line) > 40:
        return False
    match = CUE.match(line)
    if not match:
        return False
    letters = [character for character in match.group(1) if character.isalpha()]
    return bool(letters) and all(character.isupper() for character in letters)


def _split_front_matter(text: str, source: Path | None) -> tuple[dict[str, Any], str, int]:
    """Peel off the YAML front-matter block, if there is one.

    Returns:
        The front matter, the body after it, and how many lines of the file the front
        matter occupied -- so a fault in the body can be reported against the line a
        person sees in their editor, not against the line within the body.
    """
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text, 0
    consumed = text.count("\n", 0, match.end())
    try:
        loaded = load(match.group(1))
    except DuplicateKeyError as exc:
        # The block's line, moved to the file's: the cast is what usually repeats.
        line = text.count("\n", 0, match.start(1)) + exc.line
        raise ScriptSyntaxError(
            f"line {line}: in the front matter, {exc.summary}",
            source=source,
            line=line,
            rule="duplicate-key",
        ) from exc
    except yaml.YAMLError as exc:
        raise ScriptSyntaxError(f"invalid front matter: {describe(exc)}", source=source) from exc
    if loaded is None:
        return {}, text[match.end() :], consumed
    if not isinstance(loaded, dict):
        raise ScriptSyntaxError("front matter must be a mapping", source=source)
    return loaded, text[match.end() :], consumed


def _number_value(token: str) -> int | None:
    """The number a page or panel label spells, if it spells one.

    Digits, or English number words up to ninety-nine, however they are joined: `TWO`,
    `twenty-one`, `TWENTY ONE`.

    Example:
        >>> [_number_value(token) for token in ("TWO", "twenty-one", "Twenty One", "07", "3A")]
        [2, 21, 21, 7, None]
    """
    if token.isascii() and token.isdigit():
        return int(token)
    words = token.lower().replace("-", " ").split()
    if len(words) == 1 and words[0] in _UNITS:
        return _UNITS[words[0]]
    if len(words) == 1:
        return _TENS.get(words[0])
    if len(words) == 2 and words[0] in _TENS and 1 <= _UNITS.get(words[1], 0) <= 9:
        return _TENS[words[0]] + _UNITS[words[1]]
    return None


def _number_label(token: str) -> str:
    """How a page or a panel is named.

    Digits are read as a number, so `07` and `7` are one page. English number words --
    `TWO`, `twenty-one` -- become the digits a writer would say aloud, so `Panel One` and
    `PANEL 1` are the same panel. Anything else, `3A` say, is kept exactly as written.

    Example:
        >>> [_number_label(token) for token in ("TWO", "twenty-one", "07", "3A")]
        ['2', '21', '7', '3A']
    """
    value = _number_value(token)
    return token if value is None else str(value)


#: The name the highlighting tests have always read page labels with.
_page_label = _number_label


def _recognisable(line: str) -> str:
    """A line with the Markdown a writer may have put around its label taken off.

    Writers keep scripts in Markdown, so `## PANEL 2` and `**PANEL 2**` are headings, and
    `**ALICE:**` a cue. The markers are stripped, then the convention is read; this is
    only what a line is recognised as, and the text itself is never rewritten.

    Example:
        >>> [_recognisable(line) for line in ("## PANEL 2", "**ALICE:** Hi.", "__PANEL 3__")]
        ['PANEL 2', 'ALICE: Hi.', 'PANEL 3']
    """
    line = MARKDOWN_HEADING.sub("", line, count=1)
    bold = BOLD_LABEL.match(line)
    if bold is not None:
        line = (bold.group(2) + bold.group(3)).strip()
    return line


@dataclass(frozen=True, slots=True)
class _PageHeading:
    """A PAGE heading: its name, as written and as read, and the count it promises."""

    label: str
    written: str
    count: int | None = None
    count_text: str = ""


def _read_page_heading(line: str) -> _PageHeading | None:
    """Read a PAGE heading, or return None if the line is not one.

    Dark Horse's `PAGE ONE (five panels)`: the parenthetical states how many panels the
    page has. Any other parenthetical -- `(splash)` -- is a note for the artist, and is
    not read as a count. A label of several words is a heading only when the words make a
    number, `PAGE TWENTY ONE`; `PAGE THREE IS WHERE IT BEGINS` is not one.
    """
    match = PAGE_HEADING.match(line)
    if match is None:
        return None
    written = match.group("label")
    if any(character.isspace() for character in written) and _number_value(written) is None:
        return None
    note = (match.group("note") or "").strip()
    stated = PANEL_COUNT.match(note)
    count = _number_value(stated.group("count")) if stated is not None else None
    return _PageHeading(
        label=_number_label(written),
        written=written,
        count=count,
        count_text=note if count is not None else "",
    )


def _read_panel_heading(line: str, number: int, page: str | None) -> _PanelDraft | None:
    """Read a PANEL heading, opening the panel it names, or return None if it is not one.

    Dark Horse writes the description on the heading's own line, `Panel 1. Alice and Bob
    on a corner.`. With a description after it, the label must look like a number --
    digits, digits and a letter, one letter, or a number in words -- so that `Panel
    shows Alice.` stays the sentence it is.
    """
    bare = PANEL_HEADING.match(line)
    if bare is not None:
        return _PanelDraft(line=number, label=_number_label(bare.group("label")), page=page)
    described = PANEL_WITH_DESCRIPTION.match(line)
    if described is None:
        return None
    label = described.group("label")
    if not NUMBER_LIKE.fullmatch(label) and _number_value(label) is None:
        return None
    draft = _PanelDraft(line=number, label=_number_label(label), page=page)
    draft.description.append(described.group("description").strip())
    return draft


@dataclass(frozen=True, slots=True)
class ScriptNote:
    """Something the script frontend noticed that is worth saying but is not a fault.

    Attributes:
        rule: Catalogue identifier, a rule whose level is `note`.
        message: What was noticed, phrased for whoever wrote the script.
        line: One-based line it is on.
        path: Where it is, structurally, so a finding's fingerprint survives an edit above
            it: the panel's name and what in it, or the page's.
    """

    rule: str
    message: str
    line: int
    path: tuple[str | int, ...] = ()


@dataclass
class _Note:
    """A note while the script is still being read, before its panels have their names."""

    rule: str
    message: str
    line: int
    draft: _PanelDraft | None = None
    tail: tuple[str | int, ...] = ()


@dataclass
class _Reading:
    """Everything reading a script body found."""

    drafts: dict[str, _PanelDraft]
    notes: list[ScriptNote]
    title_page: list[str]
    page_notes: dict[str, list[str]]


class _Reader:
    """The script body, read line by line into panel drafts.

    The order lines are tested in is the format, so it is spelled out here once:

    1. A blank line, or a Markdown horizontal rule, ends whatever was being written.
    2. A PAGE heading, then a PANEL heading -- after `#` markers and `**` are stripped.
    3. Outside any panel -- before the first heading, or between a PAGE heading and its
       first PANEL -- prose is the title page or a note on the page; anything that would
       belong to a panel is refused.
    4. Inside one: a directive, a caption, a sound effect, then the line a cue is waiting
       for, then a continuation of the speech, then a cue, then prose.
    """

    def __init__(self, source: Path | None, cast: frozenset[str]) -> None:
        self.source = source
        self.cast = cast
        self.drafts: list[_PanelDraft] = []
        self.current: _PanelDraft | None = None
        self.page: str | None = None
        self.notes: list[_Note] = []
        self.title_page: list[str] = []
        self.page_notes: dict[str, list[str]] = {}
        # A cue waiting for its first line of speech, and where it is.
        self.pending_cue: tuple[str, BalloonKind] | None = None
        self.cue_line = 0
        # The speech being written. Everything after a cue up to a blank line is one
        # balloon, so a line a writer wrapped by hand belongs to it.
        self.speech: dict[str, Any] | None = None
        # A bare `SFX:` cue, waiting for its sound on the next line: where it was, and
        # what its parenthetical said.
        self.sound: tuple[int, dict[str, Any]] | None = None
        # A name in capitals outside any panel, which is a cue if a line follows it.
        self.loose_cue: tuple[str, int] | None = None
        # The open PAGE heading, if it stated a count, and the panels under it so far.
        self.page_heading: tuple[int, _PageHeading] | None = None
        self.panels_on_page = 0

    def read(self, body: str, offset: int) -> None:
        """Read every line of the body, `offset` lines into the file."""
        # Split on line feeds alone: `splitlines` also breaks at a line or paragraph
        # separator, a form feed and more, which an editor shows inside one line, so
        # every line number after one was wrong.
        for number, raw in enumerate(body.split("\n"), start=offset + 1):
            self.line(raw.strip(), number)
        self.end_of_item()
        self.end_of_page()

    def line(self, written: str, number: int) -> None:
        """Read one line, stripped of surrounding whitespace."""
        if not written or HORIZONTAL_RULE.match(written):
            # A blank line ends a dialogue block, so a cue never reaches across one and
            # picks up the next panel's description as its speech. A Markdown rule is a
            # visible blank line.
            self.end_of_item()
            return
        line = _recognisable(written)
        if self.heading(line, number):
            return
        if self.current is None:
            self.outside(line, written, number)
        else:
            self.inside(line, written, number, self.current)

    def heading(self, line: str, number: int) -> bool:
        """Open a page or a panel, if the line is a heading."""
        page = _read_page_heading(line)
        if page is not None:
            self.end_of_item()
            self.end_of_page()
            self.page = page.label
            self.current = None
            self.page_heading = (number, page) if page.count is not None else None
            self.panels_on_page = 0
            return True
        draft = _read_panel_heading(line, number, self.page)
        if draft is None:
            return False
        self.end_of_item()
        self.current = draft
        self.drafts.append(draft)
        self.panels_on_page += 1
        return True

    def outside(self, line: str, written: str, number: int) -> None:
        """A line before the first heading, or between a PAGE heading and its first PANEL.

        Dark Horse's format opens with the writer's name and address, so prose here is
        kept as the title page, or as a note on the page. A name in capitals with a line
        under it looks like a cue, and is noted, since nothing there is spoken; one in the
        cast is a forgotten PANEL heading, and is refused, as is anything else a panel
        would hold.
        """
        where = (
            "before the first PANEL heading"
            if self.page is None and not self.drafts
            else f"between PAGE {self.page} and its first PANEL heading"
        )
        if self.loose_cue is not None:
            name, at = self.loose_cue
            self.loose_cue = None
            self.notes.append(
                _Note(
                    "looks-like-dialogue",
                    f"'{name}' is set as a speaker's cue, with a line under it, but {where} "
                    "nothing is spoken: it is read as prose. If it is a speaker, put it under "
                    "a PANEL heading",
                    at,
                    tail=("outside", name),
                )
            )
        if any(pattern.match(line) for pattern in _BELONGS_TO_A_PANEL):
            raise ScriptSyntaxError(
                f"line {number}: {written!r} is {where}, so it belongs to no panel",
                source=self.source,
                line=number,
            )
        if _looks_like_a_cue(line):
            name = _cue_name(line)
            if name in self.cast:
                raise ScriptSyntaxError(
                    f"line {number}: {name} speaks {where}, so the line belongs to no "
                    "panel. Is a PANEL heading missing above it?",
                    source=self.source,
                    line=number,
                )
            self.loose_cue = (name, number)
        if self.page is None:
            self.title_page.append(written)
        else:
            self.page_notes.setdefault(self.page, []).append(written)

    def inside(self, line: str, written: str, number: int, current: _PanelDraft) -> None:
        """A line in a panel."""
        if _apply_directive(line, current, number, self.source):
            self.speech = None
            return

        caption = _read_caption(line, number, self.source)
        if caption is not None:
            self.abandon_cue()
            current.add(caption, number)
            self.speech = None
            return

        # Checked before cues, as a caption is: `SFX` is a perfectly good character name
        # as far as the cue pattern is concerned.
        taken, self.sound = _take_sound(line, number, self.source, current, self.sound)
        if taken:
            self.abandon_cue()
            self.speech = None
            return

        if self.pending_cue is not None:
            speaker, kind = self.pending_cue
            self.speech = {"by": speaker, "text": written, "kind": kind.value}
            current.add({"say": self.speech}, self.cue_line)
            self.pending_cue = None
            return

        # A line that looks like a cue still starts a new speech, so two speeches with no
        # blank line between them stay two speeches, as they always have.
        if self.speech is not None and not _looks_like_a_cue(line):
            self.speech["text"] = f"{self.speech['text']} {written}"
            return

        self.speech = None
        cue = _read_cue(line)
        if cue is not None:
            self.pending_cue, self.cue_line = cue, number
            return
        # Prose. Kept for tooling and round-tripping, never interpreted.
        current.description.append(written)

    def abandon_cue(self) -> None:
        """A cue that nothing was said under: noted, since its line went somewhere else."""
        if self.pending_cue is None or self.current is None:
            return
        name = self.pending_cue[0]
        self.notes.append(
            _Note(
                "looks-like-dialogue",
                f"{name} is a cue with nothing said under it: the line after it is blank, "
                "or is not a line of dialogue. Write the line under the cue, or delete it",
                self.cue_line,
                draft=self.current,
                tail=("cue", self.cue_line - self.current.line),
            )
        )
        self.pending_cue = None

    def end_of_item(self) -> None:
        """A blank line, a heading or the end: whatever was being written is finished."""
        _no_sound(self.sound, self.source)
        self.abandon_cue()
        self.speech = self.sound = self.loose_cue = None

    def end_of_page(self) -> None:
        """Hold a page to the count its heading stated, now that its panels are known."""
        if self.page_heading is None:
            return
        line, page = self.page_heading
        self.page_heading = None
        found = self.panels_on_page
        if page.count == found:
            return
        follow = "panel follows" if found == 1 else "panels follow"
        self.notes.append(
            _Note(
                "panel-count",
                f"PAGE {page.written} says {page.count_text}, but {found} {follow} it. A "
                "panel heading may have been missed, or read as prose",
                line,
                tail=("page", page.label),
            )
        )

    def reading(self) -> _Reading:
        """What was read, with every panel named."""
        drafts = _name_panels(self.drafts, self.source)
        names = {id(draft): name for name, draft in drafts.items()}
        notes = [
            ScriptNote(
                rule=note.rule,
                message=f"line {note.line}: {note.message}",
                line=note.line,
                path=(names[id(note.draft)], *note.tail) if note.draft else note.tail,
            )
            for note in self.notes
        ]
        return _Reading(drafts, notes, self.title_page, self.page_notes)


#: Lines only a panel can hold, refused outside one: a directive, a caption, a sound.
_BELONGS_TO_A_PANEL = (DIRECTIVE, CAPTION_LINE, BARE_CAPTION, SFX_LINE, BARE_SFX)


def _cue_name(line: str) -> str:
    """The name a cue line gives, which `_looks_like_a_cue` has already accepted."""
    cue = CUE.match(line)
    return cue.group(1).strip() if cue is not None else line


def _read_script(
    body: str, source: Path | None, *, offset: int = 0, cast: frozenset[str] = frozenset()
) -> _Reading:
    """Read the script body into panel drafts, and what was noticed along the way.

    Args:
        body: The script after its front matter.
        source: The file, for error messages.
        offset: Lines of the file before the body, added to every reported line number.
        cast: The front matter's cast, which tells a forgotten PANEL heading from a title.
    """
    reader = _Reader(source, cast)
    reader.read(body, offset)
    return reader.reading()


def _name_panels(drafts: list[_PanelDraft], source: Path | None) -> dict[str, _PanelDraft]:
    """Name every panel, by its page as well as its number when the numbers repeat.

    Some writers number panels straight through a script; publishers' formats start again
    at `Panel 1` on every page. A script whose labels never repeat keeps them as names,
    exactly as before pages meant anything. Otherwise every panel is named
    `page-panel` -- `2-1` for PANEL 1 under PAGE TWO -- so the names stay uniform.

    A panel that still cannot be told apart is reported, never overwritten: that used to
    lose the earlier panel without a word.

    Raises:
        ScriptSyntaxError: Rule `duplicate-panel`, at the heading that repeats, or at a
            panel that has no page to be named by.
    """
    labels = [draft.label for draft in drafts]
    if len(set(labels)) == len(labels):
        return {draft.label: draft for draft in drafts}

    seen: dict[tuple[str | None, str], _PanelDraft] = {}
    for draft in drafts:
        first = seen.setdefault((draft.page, draft.label), draft)
        if first is not draft:
            where = f" on page {draft.page}" if draft.page is not None else ""
            raise ScriptSyntaxError(
                f"line {draft.line}: PANEL {draft.label} appears twice{where}; the first is "
                f"on line {first.line}. Number panels straight through, or start each page "
                "with a PAGE heading",
                source=source,
                line=draft.line,
                rule="duplicate-panel",
            )

    named: dict[str, _PanelDraft] = {}
    for draft in drafts:
        if draft.page is None:
            raise ScriptSyntaxError(
                f"line {draft.line}: panel numbers repeat, so each panel is named by its "
                f"page, and PANEL {draft.label} comes before any PAGE heading",
                source=source,
                line=draft.line,
                rule="duplicate-panel",
            )
        named[f"{draft.page}-{draft.label}"] = draft
    return named


def _apply_directive(line: str, draft: _PanelDraft, number: int, source: Path | None) -> bool:
    """Handle an `@key: value` line. Returns whether the line was one."""
    directive = DIRECTIVE.match(line)
    if not directive:
        return False
    key, value = directive.group(1), directive.group(2).strip()
    if key == "script":
        raise ScriptSyntaxError(
            f"line {number}: a panel's script is written by its cues, captions and sound "
            "effects; '@script:' would replace them. Write each line as a cue instead",
            source=source,
            line=number,
            rule="duplicate-key",
        )
    path = ("camera", key) if key in CAMERA_DIRECTIVES else (key,)
    first = draft.directive_lines.get(path)
    if first is not None:
        # The second used to replace the first without a word -- `@setting:` twice lost
        # the first one's weather -- which is the loss `duplicate-key` reports in YAML.
        raise ScriptSyntaxError(
            f"line {number}: '@{key}' is written twice in this panel; the first is on line "
            f"{first}. Write it once, with everything it sets",
            source=source,
            line=number,
            rule="duplicate-key",
        )
    draft.directive_lines[path] = number
    if key in CAMERA_DIRECTIVES:
        draft.camera[key] = value
        return True
    try:
        draft.settings[key] = load(value)
    except DuplicateKeyError as exc:
        raise ScriptSyntaxError(
            f"line {number}: in directive '@{key}', {exc.summary}",
            source=source,
            line=number,
            rule="duplicate-key",
        ) from exc
    except yaml.YAMLError as exc:
        raise ScriptSyntaxError(
            f"line {number}: cannot read directive '@{key}': {describe(exc)}",
            source=source,
            line=number,
        ) from exc
    return True


def _read_cue(line: str) -> tuple[str, BalloonKind] | None:
    """Parse a character cue, or return None if the line is not one."""
    if not _looks_like_a_cue(line):
        return None
    cue = CUE.match(line)
    if cue is None:  # pragma: no cover -- _looks_like_a_cue already matched
        return None
    modifier = (cue.group(2) or "").strip().lower()
    return cue.group(1).strip(), KIND_MODIFIERS.get(modifier, BalloonKind.SPEECH)


def _no_sound(waiting: tuple[int, dict[str, Any]] | None, source: Path | None) -> None:
    """Refuse an `SFX:` cue that nothing follows, rather than lose the sound it announced.

    Called wherever a waiting cue would be abandoned: a blank line, a heading, the end.
    """
    if waiting is None:
        return
    line = waiting[0]
    raise ScriptSyntaxError(
        f"line {line}: an SFX cue with no sound after it; write the sound on the next line, "
        "or after the colon, as 'SFX: BLAM'",
        source=source,
        line=line,
    )


def _take_sound(
    line: str,
    number: int,
    source: Path | None,
    draft: _PanelDraft,
    waiting: tuple[int, dict[str, Any]] | None,
) -> tuple[bool, tuple[int, dict[str, Any]] | None]:
    """Read a line as part of a sound effect, if it is one.

    A waiting `SFX:` cue takes the next line whatever it looks like -- `BLAM` is in
    capitals, and would otherwise be read as a character's cue.

    Returns:
        Whether the line was taken, and the cue still waiting for its sound, if any.
    """
    if waiting is not None:
        draft.add({"sfx": {**waiting[1], "text": line}}, waiting[0])
        return True, None
    effect = _read_sfx(line, number, source)
    if effect is None:
        return False, None
    payload, text = effect
    if text is None:
        return True, (number, payload)
    draft.add({"sfx": {**payload, "text": text}}, number)
    return True, None


def _read_sfx(
    line: str, number: int, source: Path | None
) -> tuple[dict[str, Any], str | None] | None:
    """Parse an `SFX` line, or return None if the line is not one.

    Returns:
        What the parenthetical said -- `from` and `size` -- and the sound, or `None` for
        the sound when it is on the next line, as Dark Horse's format writes it.

    Raises:
        ScriptSyntaxError: The parenthetical names two sources. A name that is not in the
            cast is reported by validation, as `unknown-actor`, like any other.
    """
    found = SFX_LINE.match(line) or BARE_SFX.match(line)
    if found is None:
        return None
    payload: dict[str, Any] = {}
    for item in (part.strip() for part in (found.group(1) or "").split(",")):
        if not item:
            continue
        if item.lower() in SFX_SIZES:
            payload["size"] = item.lower()
        elif "from" in payload:
            raise ScriptSyntaxError(
                f"line {number}: an SFX comes from one actor, not {payload['from']!r} and "
                f"{item!r}; the parenthetical takes a cast name and a size, as "
                "'SFX (BOB, large): BLAM'",
                source=source,
                line=number,
            )
        else:
            payload["from"] = item
    return payload, (found.group(2).strip() if found.re is SFX_LINE else None)


def _read_caption(line: str, number: int, source: Path | None) -> dict[str, Any] | None:
    """Parse a `CAPTION:` line, or return None if the line is not one.

    Tested before character cues, because `CAPTION` on its own is a perfectly good
    character name as far as the cue pattern is concerned.
    """
    match = CAPTION_LINE.match(line)
    if not match:
        if BARE_CAPTION.match(line):
            raise ScriptSyntaxError(
                f"line {number}: a CAPTION carries its text on the same line, as "
                f"'CAPTION: Midnight. The docks.'",
                source=source,
                line=number,
            )
        return None

    modifier = (match.group(1) or "").strip().lower()
    if modifier and modifier not in CAPTION_KINDS:
        known = ", ".join(sorted(CAPTION_KINDS))
        raise ScriptSyntaxError(
            f"line {number}: unknown caption kind '{modifier}'; known kinds are {known}",
            source=source,
            line=number,
        )
    kind = CAPTION_KINDS.get(modifier, CaptionKind.LOCALE)
    return {"caption": {"text": match.group(2).strip(), "kind": kind.value}}


def normalise_text(text: str) -> str:
    r"""A script as it is read, whatever the editor that saved it did.

    - **Line endings become line feeds.** Python's text mode does this silently when
      reading a file, which is why it took a browser to notice: the playground hands over
      the bytes it was given, and a script saved by a Windows editor -- or pasted from one
      -- arrives with CRLF. The front-matter pattern then does not match, the `---` fence
      is read as prose, and the whole document is rejected for having content before the
      first PANEL heading.
    - **A byte-order mark is dropped.** Some Windows editors still write one, and it hid
      the front matter in exactly the same way.
    - **Text is composed (NFC).** A macOS editor may store `É` as `E` and a combining
      accent, and a name typed that way in a cue is the same name the front matter
      composed; compared as stored, the cue named nobody.

    Example:
        >>> normalise_text("\ufeffZOE\u0308\r\n") == "ZO\u00cb\n"
        True
    """
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


@dataclass(frozen=True, slots=True)
class PanelLines:
    """Where a script panel was written, for a finding about it to point at.

    Attributes:
        heading: The line of its PANEL heading.
        events: The line each entry of its `script` was written on, in order: a speech's
            cue, a caption's or a sound effect's own line.
    """

    heading: int
    events: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ScriptDocument:
    """A comic script, read and validated, and where each of its panels was written.

    Attributes:
        panels: Panel name to scene graph, in the order the panels appear.
        lines: Panel name to the lines it was written on.
        notes: What reading it noticed that is worth saying but is not a fault -- a cue
            with nothing said under it, a page whose count its panels do not match.
        descriptions: Panel name to its prose, which is kept and never interpreted.
        title_page: The prose before the first heading: Dark Horse's format opens with the
            writer's name and address.
        page_notes: Page to the prose between its heading and its first panel.
    """

    panels: dict[str, PanelIR]
    lines: dict[str, PanelLines]
    notes: tuple[ScriptNote, ...] = ()
    descriptions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    title_page: tuple[str, ...] = ()
    page_notes: dict[str, tuple[str, ...]] = field(default_factory=dict)


def parse_script_document(text: str, *, source: Path | None = None) -> ScriptDocument:
    r"""Parse comic script, keeping the line each panel and each of its events is on.

    `parse_script` is this, less the lines. A checker reporting a fault in a panel that
    did validate -- a balloon over the word limit, say -- needs to know where it is.

    Example:
        >>> document = parse_script_document(
        ...     "---\ncast: {A: {reference: alice}}\n---\nPANEL 1\nA\nHi.\n"
        ... )
        >>> document.lines["1"]
        PanelLines(heading=4, events=(5,))
    """
    # Anything that reaches here as a string gets the treatment a file would have had,
    # and the same whatever editor saved it.
    text = normalise_text(text)
    front_matter, body, offset = _split_front_matter(text, source)
    cast = front_matter.get("cast")
    reading = _read_script(
        body, source, offset=offset, cast=frozenset(cast if isinstance(cast, dict) else ())
    )
    panels = reading.drafts

    if not panels:
        raise ScriptSyntaxError("no PANEL headings found", source=source)

    return ScriptDocument(
        panels=_validate(panels, front_matter, source),
        lines={
            name: PanelLines(heading=draft.line, events=tuple(draft.event_lines))
            for name, draft in panels.items()
        },
        notes=tuple(reading.notes),
        descriptions={name: tuple(draft.description) for name, draft in panels.items()},
        title_page=tuple(reading.title_page),
        page_notes={page: tuple(lines) for page, lines in reading.page_notes.items()},
    )


def parse_script(text: str, *, source: Path | None = None) -> dict[str, PanelIR]:
    """Parse comic script into one validated panel per PANEL heading."""
    return parse_script_document(text, source=source).panels


def _validate(
    panels: dict[str, _PanelDraft], front_matter: dict[str, Any], source: Path | None
) -> dict[str, PanelIR]:
    """Validate each drafted panel over the front matter, reporting the first fault."""
    result: dict[str, PanelIR] = {}
    for name, draft in panels.items():
        combined = merge(front_matter, draft.as_document())
        try:
            result[name] = PanelIR.model_validate(normalise(combined))
        except PanelSyntaxError as exc:
            line = draft.line_of(exc.loc)
            raise ScriptSyntaxError(
                f"line {line}: in PANEL {name}: {exc}", source=source, line=line, rule=exc.rule
            ) from exc
        except ValidationError as exc:
            raise _first_fault(exc, name, draft, source) from exc
    return result


def _first_fault(
    exc: ValidationError, name: str, draft: _PanelDraft, source: Path | None
) -> ScriptSyntaxError:
    """The fault validation found that comes first in the script, with its rule and line.

    A panel is validated once it is assembled, so pydantic sees the whole panel and knows
    nothing of lines. Every fault it found used to be reported together, as
    `invalid-field`, at the PANEL heading -- an unknown speaker and a bad `@shot:` alike,
    wherever they were written. The rule is known (the frontend reads it exactly as
    `scenet check` reads a YAML document's), and so is the line each event and directive
    is on. One finding, the first in reading order, as the script frontend always gives:
    fixing it shows the next.
    """
    faults: list[tuple[int, str, tuple[str | int, ...], str]] = []
    for error in errors_of(exc):
        rule, loc = rule_for_pydantic(error)
        message = str(error["msg"]).removeprefix("Value error, ")
        faults.append((draft.line_of(loc), rule, loc, message))
    if not faults:  # pragma: no cover -- pydantic raises with at least one error
        return ScriptSyntaxError(f"in PANEL {name}: {summarise(exc)}", source=source)
    line, rule, loc, message = min(faults, key=lambda fault: fault[0])
    where = ".".join(str(part) for part in loc) or "<root>"
    return ScriptSyntaxError(
        f"line {line}: in PANEL {name}, at {where}: {message}",
        source=source,
        line=line,
        rule=rule,
    )


def load_script(path: Path) -> dict[str, PanelIR]:
    """Read and validate a comic script from disk.

    Args:
        path: A `*.script` file in the comic-script format writers already use.

    Returns:
        Panel name to scene graph, in the order the panels appear.

    Raises:
        OSError: The file cannot be read.
        ScriptSyntaxError: The script cannot be parsed -- dialogue before the first
            `PANEL` heading, or no `PANEL` headings at all.
    """
    return parse_script(path.read_text(encoding="utf-8"), source=path)
