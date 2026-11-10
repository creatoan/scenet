r"""What a comic script writes, read as the script frontend reads it (#241).

`tests/written.py` reads a script's front matter and its `@` directives against the published
schemas, which say what those keys mean. The rest of what a script writes -- its headings, its
cues and what their parentheses say, its captions and sounds, its French -- is the script
frontend's own, and no schema describes it. So the forms a script can take are read from the
frontend itself, as it is:

- **its tables**: every word a cue, a caption or a sound may carry in parentheses, every side
  an off-panel speaker is heard from, every French shot and angle;
- **its patterns**: the keywords a heading or a label opens with, read from each pattern's own
  source -- `PANEL|CASE|VIGNETTE` -- so a keyword added to a pattern is a form at once;
- **the panel's keys**, each a directive, as the frontend makes every key a panel takes one,
  less those it refuses;
- **the forms no table holds**, `LINE_FORMS`: a title page, a heading in Markdown, a sound on
  the line under `SFX:`.

Two entries of a table that differ only in case, accents, dots, hyphens or spaces are one form,
written either way: `(O.S.)` and `(os)`, `(pensée)` and `(pensee)`.

A script is measured as the frontend reads it, never as text: a line counts only as what the
frontend made of it -- a heading, an event or a directive, found by the line
`parse_script_document` says each was written on -- and a word only when the frontend looked it
up and found it. A parenthesis in prose, or a word in a comment of the front matter, is no form.
"""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal, get_args

from scenet import emphasis
from scenet.frontends.script_front import (
    _FRENCH_SPELLINGS,
    BALLOON_NUMBER,
    BARE_SFX,
    BOLD_LABEL,
    CAMERA_DIRECTIVES,
    CAPTION_KINDS,
    CAPTION_LABEL,
    CUE,
    DIRECTIVE,
    FRENCH_ANGLES,
    FRENCH_SHOTS,
    HORIZONTAL_RULE,
    INLINE_CUE,
    KIND_MODIFIERS,
    MARKDOWN_HEADING,
    OFF_PANEL,
    PAGE_HEADING,
    PANEL_COUNT,
    PANEL_HEADING,
    PANEL_WITH_DESCRIPTION,
    SFX_LINE,
    SFX_SIZES,
    SIDES,
    SMALL_TYPE,
    VOICE_OVER,
    _folded,
    _modifiers,
    _read_page_heading,
    _read_panel_heading,
    _recognisable,
    _split_front_matter,
    normalise_text,
    parse_script_document,
)
from scenet.ir import (
    CameraAngle,
    CaptionEvent,
    Direction,
    PanelIR,
    ScriptEvent,
    SfxEvent,
    ShotType,
)
from scenet.safe_yaml import load
from scenet.schema import scene_schema

__all__ = [
    "LINE_FORMS",
    "NOT_READ",
    "READ",
    "REFUSED",
    "LineForm",
    "fold",
    "keywords",
    "offered",
    "read",
    "read_file",
]

#: The forms no table holds, each a reading the frontend makes of a line or of a whole script,
#: named as `docs/howto/write_a_comic_script.md` describes it.
LineForm = Literal[
    "a title page",
    "prose between a PAGE heading and its first panel",
    "a PAGE heading with a count",
    "a PAGE heading with a note that is not a count",
    "a panel heading alone",
    "a panel heading with its description",
    "a heading in Markdown, after #",
    "a label in bold",
    "a horizontal rule",
    "a numbered lettering item",
    "a cue alone on its line",
    "a cue with its line after a colon",
    "a cue in lower case, a cast id",
    "a caption with its text after the colon",
    "a caption with its text under the label",
    "a caption by a speaker, CAP/NAME",
    "a sound with its text after the colon",
    "a sound on the line under SFX",
    "a sound from somebody",
    "a sound with no parenthetical",
    "a stressed word",
    "a panel before the first PAGE heading",
    "more than one page",
    "page: in the front matter",
    "direction: rtl in the front matter",
    "@cast leaving somebody out with null",
]

LINE_FORMS: frozenset[str] = frozenset(get_args(LineForm))

#: Directives the frontend refuses though a panel takes the key, by why, which a test holds
#: it to.
REFUSED = {"script": "a panel's script is written by its cues, captions and sound effects"}

#: Every public table and pattern of the script frontend this module reads, by what it reads
#: from it. A test holds the frontend to this list and `NOT_READ`, so a table or a pattern it
#: gains is read here, or excused, before it can go unexemplified.
READ = {
    "KIND_MODIFIERS": "its words, on a cue",
    "VOICE_OVER": "its words, on a cue and on a caption",
    "OFF_PANEL": "its words, on a cue",
    "SMALL_TYPE": "its words, on a cue",
    "SIDES": "its words, beside an off-panel mark",
    "CAPTION_KINDS": "its words, on a caption",
    "SFX_SIZES": "its words, on a sound",
    "FRENCH_SHOTS": "its words, after @shot:",
    "FRENCH_ANGLES": "its words, after @angle:",
    "CAMERA_DIRECTIVES": "its directives, each in English and in French",
    "PANEL_HEADING": "its keywords, and a panel heading alone",
    "PANEL_WITH_DESCRIPTION": "a panel heading with its description",
    "PAGE_HEADING": "its keywords, and a count or a note",
    "PANEL_COUNT": "its nouns",
    "CAPTION_LABEL": "its keywords, a speaker, its words and where its text is",
    "SFX_LINE": "its keywords, a sound's source and size, and its text after the colon",
    "BARE_SFX": "a sound on the line under SFX",
    "MARKDOWN_HEADING": "a heading in Markdown",
    "BOLD_LABEL": "a label in bold",
    "HORIZONTAL_RULE": "a horizontal rule",
    "DIRECTIVE": "every directive, and what it sets",
    "CUE": "a cue alone on its line",
    "INLINE_CUE": "a cue with its line, and one in lower case",
    "BALLOON_NUMBER": "a numbered lettering item",
}

#: The public tables and patterns of the script frontend this module does not read, by why.
NOT_READ = {
    "FRONT_MATTER": "the front matter is YAML, read against the schemas by tests/written.py",
    "NUMBER_LIKE": "it tells a heading's label from a word, and is no form of its own",
    "RESERVED_NAMES": "the ids no cast member may take: writing one is an error",
}


def fold(word: str) -> str:
    """A word as two spellings of it are one form: folded as the frontend folds French, and
    without its spaces.

    Example:
        >>> from tests.script_forms import fold
        >>> [fold(word) for word in ("O.S.", "os", "Voice-Over", "voiceover", "pensée")]
        ['os', 'os', 'voiceover', 'voiceover', 'pensee']
    """
    return "".join(_folded(word).split())


#: A word in a pattern's source: letters, a class of letters, a letter made optional.
_WORD = r"(?:[^\W\d_]|\[[^\W\d_]+\]|\?)+"
#: A group of a pattern's source whose alternatives are all words: `(?P<keyword>PAGE|PLANCHE)`.
_ALTERNATIVES = re.compile(rf"\((?:\?P<\w+>|\?:)({_WORD}(?:\|{_WORD})+)\)")


def keywords(pattern: re.Pattern[str]) -> tuple[str, ...]:
    r"""The words a pattern opens a heading or a label with, read from its own source.

    They are the one group of the pattern whose alternatives are all words. A class of
    letters stands for its last, the accented one -- `R[EÉ]CITATIF` is `RÉCITATIF` -- and a
    letter made optional is kept: `panels?` is `panels`.

    Example:
        >>> import re
        >>> from tests.script_forms import keywords
        >>> keywords(re.compile(r"^(?:SFX|ONOMATOP[EÉ]E)\s*:"))
        ('SFX', 'ONOMATOPÉE')
    """
    found = _ALTERNATIVES.findall(pattern.pattern)
    assert len(found) == 1, f"{pattern.pattern!r} has {len(found)} groups of keywords, not one"
    return tuple(
        re.sub(r"\[([^\]]+)\]", lambda letters: letters.group(1)[-1], word).replace("?", "")
        for word in found[0].split("|")
    )


def _spelled(entries: Iterable[str], where: str) -> dict[str, str]:
    """A table's entries by their fold, each as the form it is: its spellings, and where.

    Example:
        >>> from tests.script_forms import _spelled
        >>> _spelled(["o.s.", "os", "op"], "on a cue")["os"]
        '(o.s.) or (os) on a cue'
    """
    spellings: dict[str, set[str]] = {}
    for entry in entries:
        spellings.setdefault(fold(entry), set()).add(entry)
    return {
        key: f"{' or '.join(f'({word})' for word in sorted(words))} {where}"
        for key, words in spellings.items()
    }


def _named(words: Iterable[str], form: str) -> dict[str, str]:
    """Keywords by their fold, each as the form it is."""
    return {fold(word): form.format(word) for word in words}


#: What a cue's parentheses may say, as `_line_for` looks it up: exactly, in lower case.
_ON_A_CUE = frozenset({*KIND_MODIFIERS, *VOICE_OVER, *OFF_PANEL, *SMALL_TYPE})
#: What a caption's parentheses may say, as `_caption_kind` looks it up.
_ON_A_CAPTION = frozenset({*CAPTION_KINDS, *VOICE_OVER})

CUE_WORDS = _spelled(_ON_A_CUE, "on a cue")
SIDE_WORDS = _spelled(SIDES, "beside an off-panel mark")
CAPTION_WORDS = _spelled(_ON_A_CAPTION, "on a caption")
SOUND_WORDS = _spelled(SFX_SIZES, "on a sound")

#: A camera directive's words in English, as `_camera_word` takes them: as the language
#: spells them.
_ENGLISH = {
    key: frozenset(item.value for item in (ShotType if key == "shot" else CameraAngle))
    for key in CAMERA_DIRECTIVES
}
#: A camera directive's words in French, by their fold, each as the directive that writes it.
IN_FRENCH = {
    key: {
        fold(word): f"@{key}: {_FRENCH_SPELLINGS.get(word, word)}"
        for word in (FRENCH_SHOTS if key == "shot" else FRENCH_ANGLES)
    }
    for key in CAMERA_DIRECTIVES
}

PANEL_KEYWORDS = _named(keywords(PANEL_HEADING), "{} as a panel heading")
PAGE_KEYWORDS = _named(keywords(PAGE_HEADING), "{} as a page heading")
CAPTION_KEYWORDS = _named(keywords(CAPTION_LABEL), "{} as a caption")
SOUND_KEYWORDS = _named(keywords(SFX_LINE), "{} as a sound")
#: A count's nouns, singular or plural alike: `one panel`, `two panels`.
COUNT_NOUNS = {
    fold(word).removesuffix("s"): f"{word} counted on a page heading"
    for word in keywords(PANEL_COUNT)
}


def _directives() -> frozenset[str]:
    """Every directive: each key a panel takes, but those refused, and the frontend's own."""
    panel = scene_schema()["properties"]["panels"]["additionalProperties"]["properties"]
    return frozenset(set(panel) - set(REFUSED)) | CAMERA_DIRECTIVES | {"tiers"}


def offered() -> frozenset[str]:
    """Every form a comic script can take, by the name `read` gives it."""
    tables: list[Mapping[str, str]] = [
        CUE_WORDS,
        SIDE_WORDS,
        CAPTION_WORDS,
        SOUND_WORDS,
        *IN_FRENCH.values(),
        PANEL_KEYWORDS,
        PAGE_KEYWORDS,
        CAPTION_KEYWORDS,
        SOUND_KEYWORDS,
        COUNT_NOUNS,
    ]
    return frozenset(
        LINE_FORMS
        | {form for table in tables for form in table.values()}
        | {f"@{key}" for key in _directives()}
        | {f"@{key} in English" for key in CAMERA_DIRECTIVES}
    )


def _opening(line: str) -> str:
    """The word a label opens with: `CAP` in `CAP/MAYA`, `SFX` in `SFX (large): BOOM`."""
    word = re.match(r"[^\W\d_]+", line)
    assert word is not None, line
    return word.group()


class _Reading:
    """The forms of one script, as its lines are read."""

    def __init__(self) -> None:
        self.lines: set[LineForm] = set()
        self.words: set[str] = set()

    def markup(self, written: str, *, heading: bool) -> None:
        """Markdown round a heading or a label: `#` before a heading, `**` round either."""
        if heading and MARKDOWN_HEADING.match(written):
            self.lines.add("a heading in Markdown, after #")
        if BOLD_LABEL.match(MARKDOWN_HEADING.sub("", written, count=1)):
            self.lines.add("a label in bold")

    def body(self, written: str) -> None:
        """A line of the body that is read the same wherever it is: a rule, a PAGE heading,
        a page's `@tiers:`."""
        if HORIZONTAL_RULE.match(written):
            self.lines.add("a horizontal rule")
            return
        line = _recognisable(written)
        heading = PAGE_HEADING.match(line)
        page = _read_page_heading(line)
        if heading is None or page is None:
            directive = DIRECTIVE.match(line)
            if directive is not None and directive.group(1) == "tiers":
                self.words.add("@tiers")
            return
        self.markup(written, heading=True)
        self.words.add(PAGE_KEYWORDS[fold(heading.group("keyword"))])
        note = (heading.group("note") or "").strip()
        if page.count is not None:
            self.lines.add("a PAGE heading with a count")
            self.words.add(COUNT_NOUNS[fold(note.split()[-1]).removesuffix("s")])
        elif note:
            self.lines.add("a PAGE heading with a note that is not a count")

    def panel_heading(self, written: str) -> None:
        """The heading a panel opens with."""
        self.markup(written, heading=True)
        line = _recognisable(written)
        draft = _read_panel_heading(line, 0, None)
        assert draft is not None, written
        described = bool(draft.description)
        heading = (PANEL_WITH_DESCRIPTION if described else PANEL_HEADING).match(line)
        assert heading is not None, written
        self.words.add(PANEL_KEYWORDS[fold(heading.group("keyword"))])
        self.lines.add(
            "a panel heading with its description" if described else "a panel heading alone"
        )

    def directive(self, path: tuple[str, ...], written: str) -> None:
        """A directive, by the path in the panel it sets, and what it sets it to."""
        # `@shot:` sets `("camera", "shot")`, and `@camera:` the camera, `("camera",)`.
        key = path[-1] if path[0] == "camera" else path[0]
        self.words.add(f"@{key}")
        directive = DIRECTIVE.match(_recognisable(written))
        assert directive is not None, written
        value = directive.group(2).strip()
        if key in CAMERA_DIRECTIVES:
            english = value in _ENGLISH[key]
            self.words.add(f"@{key} in English" if english else IN_FRENCH[key][fold(value)])
        elif key == "cast":
            cast = load(value)
            if isinstance(cast, dict) and None in cast.values():
                self.lines.add("@cast leaving somebody out with null")

    def event(self, event: ScriptEvent, written: str, panel: PanelIR) -> None:
        """A line of the panel's script: a speech, a caption or a sound, from its label."""
        self.markup(written, heading=False)
        line = _recognisable(written)
        number = BALLOON_NUMBER.match(line)
        if number is not None:
            # A label opens with a letter, so a number before it is a lettering item's.
            self.lines.add("a numbered lettering item")
            line = line[number.end() :]
        label = CAPTION_LABEL.match(line)
        if isinstance(event, SfxEvent):
            self.sound(line)
            return
        if isinstance(event, CaptionEvent) and label is not None:
            self.caption(label, line)
        else:
            # A speech, or a voice over's caption, which is written as a cue.
            self.cue(line, panel)
        if any(span.emphasised for span in emphasis.parse(event.text)):
            self.lines.add("a stressed word")

    def cue(self, line: str, panel: PanelIR) -> None:
        """A cue: its name, where its line is, and the words in its parentheses."""
        inline = INLINE_CUE.match(line)
        if inline is not None:
            name, parentheticals = inline.group("name").strip(), inline.group("mods")
            self.lines.add("a cue with its line after a colon")
        else:
            alone = CUE.match(line)
            assert alone is not None, line
            name, parentheticals = alone.group(1).strip(), alone.group(2)
            self.lines.add("a cue alone on its line")
        letters = [character for character in name if character.isalpha()]
        if name in panel.cast and not all(character.isupper() for character in letters):
            self.lines.add("a cue in lower case, a cast id")
        words = _modifiers(parentheticals)
        self.words.update(CUE_WORDS[fold(word)] for word in words if word in _ON_A_CUE)
        if any(word in OFF_PANEL for word in words):
            self.words.update(SIDE_WORDS[fold(word)] for word in words if word in SIDES)

    def caption(self, label: re.Match[str], line: str) -> None:
        """A caption: its keyword, who speaks it, its words, and where its text is."""
        self.words.add(CAPTION_KEYWORDS[fold(_opening(line))])
        if (label.group("speaker") or "").strip():
            self.lines.add("a caption by a speaker, CAP/NAME")
        words = _modifiers(label.group("mods"))
        self.words.update(CAPTION_WORDS[fold(word)] for word in words if word in _ON_A_CAPTION)
        self.lines.add(
            "a caption with its text after the colon"
            if label.group("text")
            else "a caption with its text under the label"
        )

    def sound(self, line: str) -> None:
        """A sound effect: its keyword, its parenthetical, and where the sound is."""
        found = SFX_LINE.match(line) or BARE_SFX.match(line)
        assert found is not None, line
        self.words.add(SOUND_KEYWORDS[fold(_opening(line))])
        self.lines.add(
            "a sound with its text after the colon"
            if found.re is SFX_LINE
            else "a sound on the line under SFX"
        )
        items = [item.strip() for item in (found.group(1) or "").split(",") if item.strip()]
        if not items:
            self.lines.add("a sound with no parenthetical")
        for item in items:
            if item.lower() in SFX_SIZES:
                self.words.add(SOUND_WORDS[fold(item)])
            else:
                self.lines.add("a sound from somebody")


def read(text: str) -> frozenset[str]:
    """Every form a comic script takes, as the frontend reads it.

    Raises:
        ScriptSyntaxError: The script does not compile: an example of nothing.
    """
    text = normalise_text(text)
    document = parse_script_document(text)
    lines = text.split("\n")
    front_matter, _, offset = _split_front_matter(text, None)
    reading = _Reading()
    if "page" in front_matter:
        reading.lines.add("page: in the front matter")
    if document.direction is Direction.RTL:
        reading.lines.add("direction: rtl in the front matter")
    if document.title_page:
        reading.lines.add("a title page")
    if document.page_notes:
        reading.lines.add("prose between a PAGE heading and its first panel")
    pages = document.layout.pages
    if len(pages) > 1:
        reading.lines.add("more than one page")
    placed = {name for page in pages for tier in page.tiers for name, _ in tier.placed}
    if placed and set(document.panels) - placed:
        reading.lines.add("a panel before the first PAGE heading")
    for written in lines[offset:]:
        reading.body(written.strip())
    for name, panel in document.panels.items():
        where = document.lines[name]
        reading.panel_heading(lines[where.heading - 1].strip())
        for path, number in where.directives.items():
            reading.directive(path, lines[number - 1].strip())
        for event, number in zip(panel.script, where.events, strict=True):
            reading.event(event, lines[number - 1].strip(), panel)
    return frozenset({*reading.lines, *reading.words})


def read_file(path: Path) -> frozenset[str]:
    """Every form a comic script in a file takes."""
    return read(path.read_text(encoding="utf-8"))
