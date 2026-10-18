"""A frontend for comic script, the format writers already use.

Checked before building this: Fountain has no native panel, caption or SFX support,
and there is no standardised comic script format at all. But the informal industry
convention is stable across publishers -- `PANEL 1`, a prose description, a character
cue in capitals, the dialogue beneath it -- so that is what this parses. Dark Horse
publishes its own house format, and it is read as written: `PAGE ONE (five panels)`,
`Panel 1.` with its description, `CAP:` and `CAP/NAME`, numbered lettering, Markdown
around any of it. So is a French script: `PLANCHE 1`, `CASE 2`, `RÉCITATIF :`, the
*échelle des plans*. Each PAGE heading is a page.

**The honest limitation.** A prose description like "Alice and Bob face each other on
a rainy street corner" cannot be compiled. Turning that into staging needs natural
language understanding, and guessing would produce panels that are confidently wrong
-- far worse than refusing. So descriptions are preserved but not interpreted -- each one
is its panel's `description`, read out as written by accessible output -- and anything the
compiler must know is declared explicitly: cast and staging in a front-matter block,
per-panel settings as `@` directives.

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
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scenet.compose import (
    DESCRIPTION_KEY,
    NOT_A_DEFAULT,
    OVER_KEY,
    merge,
    names,
    relation_text,
    resolve_overrides,
    settle,
)
from scenet.errors import CompositionError, PanelSyntaxError, ScriptSyntaxError
from scenet.frontends.common import (
    errors_of,
    normalise,
    normalise_layout,
    rule_for_pydantic,
    summarise,
)
from scenet.ir import (
    BalloonKind,
    CameraAngle,
    CaptionKind,
    PageLayout,
    PanelIR,
    Predicate,
    SfxSize,
    ShotType,
    Side,
    unholdable,
)
from scenet.safe_yaml import DuplicateKeyError, describe, load

# Leading blank lines are tolerated. A script pasted out of an editor or produced by a
# templating step very often starts with one, and refusing it would be a baffling
# failure for a file that looks identical to a working one.
FRONT_MATTER = re.compile(r"^\s*---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)
# The label is everything up to an optional trailing colon or full stop -- `PANEL 1:` and
# Dark Horse's `Panel 1.` both name panel `1`. A greedy `\S+` used to take the colon, so
# the panel was called `1:` and `scenet build` wrote a file Windows cannot hold.
PANEL_HEADING = re.compile(
    r"^(?P<keyword>PANEL|CASE|VIGNETTE)\s+(?P<label>[^\s:]+?)\s*[.:]?\s*$", re.IGNORECASE
)
# Dark Horse's `Panel 1. Alice and Bob on a corner.`: the description on the heading's own
# line, after a full stop, a colon, a dash or a spaced hyphen.
PANEL_WITH_DESCRIPTION = re.compile(
    r"^(?P<keyword>PANEL|CASE|VIGNETTE)\s+(?P<label>[^\s.:\u2014\u2013-]+)\s*(?:[.:\u2014\u2013]|\s-)\s*(?P<description>\S.*)$",
    re.IGNORECASE,
)
# A label a panel with a description on its line may have: `1`, `4B`, `C`.
NUMBER_LIKE = re.compile(r"\d+[^\W\d_]?|[^\W\d_]")
# Dark Horse's `PAGE ONE (five panels)`. The label may be several words when they make a
# number, `PAGE TWENTY ONE`; the parenthetical may state the count, or be a note.
#
# Every part can match a given stretch in one way only, because a script is untrusted
# input and backtracking is not free. Words are split on whitespace alone: a word already
# takes a hyphen, so `TWENTY-ONE` is one word, and when a hyphen could also part two
# words, `PAGE !-!-!-…(` split in exponentially many ways before failing (CodeQL
# py/redos). The tail takes trailing space once, after whatever it follows, where three
# optional runs of it in a row made a long blank line cubic.
#
# Each word is as short as the line allows, as PANEL_HEADING's label is, so a closing full
# stop ends the heading rather than the label: `Page 4B.` is page `4B`, and
# `PAGE TWENTY ONE.` is twenty-one rather than a sentence. A full stop the line needs
# inside a word stays there, as in `PAGE 3.5`.
PAGE_HEADING = re.compile(
    r"^(?P<keyword>PAGE|PLANCHE)\s+(?P<label>[^\s:()]+?(?:\s+[^\s:()]+?)*?)\s*(?:\((?P<note>[^)]*)\)\s*)?(?:[.:]\s*)?$",
    re.IGNORECASE,
)
# The count in a PAGE heading's parenthetical: `five panels`, `1 panel`, `six cases`.
PANEL_COUNT = re.compile(
    r"^(?P<count>\w+(?:[\s-]\w+)*)\s+(?:panels?|cases?|vignettes?)$", re.IGNORECASE
)
# Markdown a writer may put around a label: `## PANEL 2`, `**PANEL 2**`, `**ALICE:**`.
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+")
BOLD_LABEL = re.compile(r"^(\*\*|__)(\S(?:.*?\S)?)\1(.*)$")
# A Markdown horizontal rule, `---` or `* * *`, which reads as the blank line it looks like.
# `--` is two hyphens, Dark Horse's carry-over mark, and is not one.
HORIZONTAL_RULE = re.compile(r"^([-*_])(?:[ \t]*\1){2,}$")
DIRECTIVE = re.compile(r"^@(\w+)\s*:\s*(.+)$")
# A cue is a character name in capitals, then any parentheticals -- `BOB (OP) (whisper)`, or
# one with commas, `BOB (OP, whisper)` -- and an optional colon. Any letter may start it,
# not only A to Z: `HÉLÈNE` is a name in capitals, and her lines used to be filed as prose.
# Whether the letters are capitals is `_looks_like_a_cue`'s test.
CUE = re.compile(r"^([^\W\d_][\w '.-]*?)\s*((?:\([^)]*\)\s*)*):?\s*$")
# A cue with its line after the colon: `ALICE: Hello.` Dialogue only when the name is in the
# panel's cast -- a writer's `NOTE: redraw this` is not -- or, in capitals, a note says why
# it was not.
#
# The name ends on something other than space, so the run after it is the `\s*`'s alone:
# when both could take it, a long gap was quadratic. A name never kept a trailing space
# anyway -- the shortest name was always preferred. CUE has the same shape, but only ever
# reads a line of forty characters or fewer.
INLINE_CUE = re.compile(
    r"^(?P<name>[^\W\d_](?:[\w '.-]*?[\w'.-])?)\s*(?P<mods>(?:\([^)]*\)\s*)*):\s*(?P<text>\S.*)$"
)
# `CAPTION: Midnight.`, `CAP (monologue):` with the text under it, and Dark Horse's
# `CAP/CHARACTER`, a caption carrying a character's speech. The text follows the colon, or
# runs on the lines under the label to a blank line. `CAPTAIN` is not `CAP`.
#
# No run of space here can be taken by two parts, for the reason PAGE_HEADING gives: the
# speaker and the text end on something other than space, and the space that ends the
# line is taken by whatever comes last rather than once more after it. A speaker of
# nothing but space, `CAP/ :`, is still one space, as it always was.
CAPTION_LABEL = re.compile(
    r"^(?:CAPTION|CAP|R[EÉ]CITATIF|NARRATIF|CARTOUCHE)(?!\w)\s*(?:/\s*(?P<speaker>[^():/]*?[^():/\s]|\s)\s*)?(?P<mods>(?:\([^)]*\)\s*)*)"
    r"(?:(?P<colon>:)\s*(?P<text>(?:.*\S)?)\s*)?$",
    re.IGNORECASE,
)
# `SFX: BLAM`, optionally `SFX (BOB, large): BLAM` -- who it comes from, how loud. The
# sound on the same line.
#
# Space is taken once after each part rather than before and after an optional one, for
# the reason PAGE_HEADING gives: two optional runs in a row made a long line quadratic
# here, and three made the bare form below cubic.
SFX_LINE = re.compile(r"^(?:SFX|ONOMATOP[EÉ]E)\s*(?:\(([^)]*)\)\s*)?:\s*(.+)$", re.IGNORECASE)
# Dark Horse's form: `SFX:` as a cue, the sound on the next line. Without this it is a
# character called SFX, and the sound would be lettered in a balloon.
BARE_SFX = re.compile(r"^(?:SFX|ONOMATOP[EÉ]E)\s*(?:\(([^)]*)\)\s*)?(?::\s*)?$", re.IGNORECASE)
# Blambot: "Each item in the lettering area should be numbered." `1. ALICE:`, `2) CAP:`.
BALLOON_NUMBER = re.compile(r"^\d+[.)]?\s+")

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
    # Dark Horse's `(burst)`; Blambot: "(BURST), meaning the dialogue is shouted and should
    # be in a burst balloon".
    "burst": BalloonKind.SHOUT,
    # French: a *bulle de pensée* is a thought balloon (Blankcomic's script example).
    "pensée": BalloonKind.THOUGHT,
    "pensee": BalloonKind.THOUGHT,
    # The BnF's *Les bulles de la BD*: a dotted outline when a character "murmure", and
    # *chuchoter* is to murmur (Larousse). A shout for one who "crie fort".
    "murmure": BalloonKind.WHISPER,
    "murmuré": BalloonKind.WHISPER,
    "chuchoté": BalloonKind.WHISPER,
    "chuchote": BalloonKind.WHISPER,
    "cri": BalloonKind.SHOUT,
    "crié": BalloonKind.SHOUT,
    "crie": BalloonKind.SHOUT,
}

# A voice over: Blambot's "CAPTION (VOICE OVER), meaning the character is speaking, but is
# not in the location shown in the current panel". On a cue, the line is a spoken caption by
# that character; on a caption, it is the spoken kind.
VOICE_OVER = {"v.o.", "vo", "voice over", "voice-over", "voiceover"}

# Off panel: Dark Horse's `(OP)`, Blambot's `(OFF)`, the screenplay's `(O.S.)` and its older
# spelling `(O.C.)`. The speaker is in the scene but not in the frame.
OFF_PANEL = {
    "op",
    "off",
    "o.s.",
    "os",
    "o.c.",
    "oc",
    "off-panel",
    "off panel",
    "offpanel",
    # French cinema's *hors-champ*, out of the frame.
    "hors champ",
    "hors-champ",
}

# Dark Horse's `(small)`, and `(weak)`, which Blambot reads as "dialogue should be
# diminished": smaller type. Comicraft's weak lettering is also erratic; that hand is
# not drawn.
SMALL_TYPE = {
    "small",
    "weak",
    # The BnF again: type smaller than the rest reads as a character who "parle bas".
    "à voix basse",
    "a voix basse",
    "voix basse",
}

# The side of the frame an off-panel speaker is on, when a cue names it: `(OP, left)`.
SIDES = {side.value: side for side in Side}

# Labels a line starts with that are never a speaker: a cast member called `CAP` would be
# read as a caption every time it spoke. Compared without regard to case.
RESERVED_NAMES = {
    "cap",
    "caption",
    "sfx",
    "récitatif",
    "recitatif",
    "narratif",
    "cartouche",
    "onomatopée",
    "onomatopee",
}

# Quotation marks a writer puts around speech, which the compiler adds itself where they
# belong. Spelled as code points, so no editor turns one into another.
_DOUBLE_QUOTE = '"'
_OPENING_QUOTES = (_DOUBLE_QUOTE, chr(0x201C), chr(0x00AB))
_CLOSING_QUOTES = (_DOUBLE_QUOTE, chr(0x201D), chr(0x00BB))
_QUOTE_PAIRS = tuple(zip(_OPENING_QUOTES, _CLOSING_QUOTES, strict=True))
# French typography spaces the inside of guillemets, often with a no-break space.
_QUOTE_SPACE = " " + chr(0x00A0) + chr(0x202F)

# The parenthetical on a CAPTION line, which says what the box is doing. Spelled the
# same as the IR's own vocabulary, since a writer typing `(monologue)` means the thing
# the letterers call a monologue.
CAPTION_KINDS = {kind.value: kind for kind in CaptionKind}

# How loud an SFX is, as its parenthetical may say.
SFX_SIZES = {size.value: size for size in SfxSize}

# The *échelle des plans*, rung for rung against `shot_types.md`, compared folded. *Gros
# plan* is cut above the shoulders, at the face (BnF, *Créer une BD*; Ac-Lyon; French
# Wikipedia's ladder puts *plan rapproché épaule* between it and *plan rapproché*), so it is
# `big_close_up`, and the shoulders' own rung is `close_up`. OQLF puts *gros plan* at the
# shoulders; that divergence is recorded in `write_a_comic_script.md`. *Plan général* and
# *plan italien* are left out rather than collapse two rungs into one.
FRENCH_SHOTS = {
    "plan d ensemble": "long_shot",
    "pe": "long_shot",
    "plan moyen": "full_shot",
    "pm": "full_shot",
    "plan americain": "cowboy",
    "pa": "cowboy",
    "plan rapproche taille": "medium_shot",
    "plan mi moyen": "medium_shot",
    "prt": "medium_shot",
    "pmm": "medium_shot",
    "plan rapproche poitrine": "medium_close_up",
    "plan rapproche": "medium_close_up",
    "prp": "medium_close_up",
    "pr": "medium_close_up",
    "plan rapproche epaule": "close_up",
    "plan epaule": "close_up",
    "gros plan": "big_close_up",
    "gp": "big_close_up",
    "tres gros plan": "extreme_close_up",
    "tgp": "extreme_close_up",
}

# *Plongée* looks down on the subject, *contre-plongée* up at it.
FRENCH_ANGLES = {
    "plongee": "high",
    "contre plongee": "low",
    "angle normal": "eye_level",
}

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


# French numbers to twenty, for `PLANCHE UNE` and `(six cases)`: a page holds no more.
_FRENCH_NUMBERS = {
    word: value
    for value, word in enumerate(
        (
            "zero",
            "un",
            "deux",
            "trois",
            "quatre",
            "cinq",
            "six",
            "sept",
            "huit",
            "neuf",
            "dix",
            "onze",
            "douze",
            "treize",
            "quatorze",
            "quinze",
            "seize",
            "dix sept",
            "dix huit",
            "dix neuf",
            "vingt",
        )
    )
} | {"une": 1}


def _folded(text: str) -> str:
    """Text as French names are compared, so a writer's spelling need not be exact.

    Lower case, no accents, no apostrophes, hyphens or full stops, single spaces.

    Example:
        >>> _folded("Plan d'Ensemble"), _folded("contre-plongée"), _folded("P.A.")
        ('plan d ensemble', 'contre plongee', 'pa')
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    for mark in ("'", chr(0x2019), "-"):
        plain = plain.replace(mark, " ")
    return " ".join(plain.replace(".", "").split())


@dataclass
class _PanelDraft:
    """One panel being accumulated as the script is read.

    A typed accumulator rather than a bare dict: the script body contributes several
    kinds of thing -- dialogue, captions, directives, prose -- and keeping them apart
    until the end makes it obvious that prose is never interpreted: it reaches the
    compiler only as the panel's `description`, which nothing is drawn from.
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
        """The panel as a document, its prose as its `description`.

        The prose is never interpreted -- nothing is drawn from it -- but it is already a
        text rendering of the panel, which is what a reader who cannot see it needs. Its
        lines are one paragraph, with the Markdown markers a writer may have put round a
        word taken off. A `@description:` directive says something else, and wins.
        """
        document: dict[str, Any] = dict(self.settings)
        if self.camera:
            document["camera"] = {**document.get("camera", {}), **self.camera}
        document["script"] = self.events
        if self.description and DESCRIPTION_KEY not in document:
            document[DESCRIPTION_KEY] = _without_markdown(" ".join(self.description))
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
    french = _FRENCH_NUMBERS.get(" ".join(_folded(token).split()))
    if french is not None:
        return french
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


#: Markdown's markers round a word: `**bold**` and `__bold__`, then `*italic*` and
#: `_italic_`. Only round a word, so `snake_case` and `2*3*4` keep theirs.
_MARKDOWN_EMPHASIS = (
    re.compile(r"(?<![\w*])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![\w*])"),
    re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)"),
    re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])"),
    re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)"),
)


def _without_markdown(prose: str) -> str:
    """Prose with the emphasis markers taken off, which a screen reader would read out.

    Example:
        >>> _without_markdown("**Alice** looks _up_ at *Bob*, past snake_case and 2*3*4.")
        'Alice looks up at Bob, past snake_case and 2*3*4.'
    """
    for pattern in _MARKDOWN_EMPHASIS:
        prose = pattern.sub(r"\1", prose)
    return prose


def _check_prose(prose: str, number: int, source: Path | None) -> str:
    """A line of prose, refused at its own line if an SVG cannot hold it.

    Prose was never written anywhere, so a stray control character in it was harmless. It
    is the panel's description now, which goes into the SVG; reported here, the finding
    names the line it is on rather than the panel's heading.
    """
    # Whitespace first, as the description itself is read: Word's U+000B is a space.
    problem = unholdable(" ".join(prose.split()))
    if problem is not None:
        raise ScriptSyntaxError(
            f"line {number}: this panel's description {problem}",
            source=source,
            line=number,
            rule="invalid-field",
        )
    return prose


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
    several = any(character.isspace() for character in written)
    french = match.group("keyword").upper() != "PAGE"
    if (
        (several or french)
        and _number_value(written) is None
        and not NUMBER_LIKE.fullmatch(written)
    ):
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
    # `CASE` and `VIGNETTE` are words too: `CASE CLOSED` is a cue, not a panel.
    if bare is not None and _is_a_panel_label(bare.group("keyword"), bare.group("label")):
        return _PanelDraft(line=number, label=_number_label(bare.group("label")), page=page)
    described = PANEL_WITH_DESCRIPTION.match(line)
    if described is None:
        return None
    label = described.group("label")
    if not _is_a_panel_label("CASE", label):
        return None
    draft = _PanelDraft(line=number, label=_number_label(label), page=page)
    draft.description.append(described.group("description").strip())
    return draft


def _is_a_panel_label(keyword: str, label: str) -> bool:
    """Whether a heading's label names a panel.

    Anything after `PANEL` alone on its line; only a number after `CASE` or `VIGNETTE`, or
    before a description, since those are words too.
    """
    if keyword.upper() == "PANEL":
        return True
    return NUMBER_LIKE.fullmatch(label) is not None or _number_value(label) is not None


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
    pages: list["_PageDraft"]


@dataclass
class _PageDraft:
    """One page being accumulated: its panels, and the tiers `@tiers:` gave them, if any."""

    label: str
    line: int
    drafts: list[_PanelDraft] = field(default_factory=list)
    tiers: list[int] | None = None
    tiers_line: int = 0


@dataclass
class _Pending:
    """A label waiting for its text on the next line: a cue, a caption or a sound effect.

    Attributes:
        verb: The event it will be: `say`, `caption` or `sfx`.
        payload: Its fields so far, everything but the text.
        line: Where the label is, which is where the event is reported from.
        name: A cue's speaker, to say who had nothing to say.
    """

    verb: str
    payload: dict[str, Any]
    line: int
    name: str = ""


class _Reader:
    """The script body, read line by line into panel drafts.

    The order lines are tested in is the format, so it is spelled out here once:

    1. A blank line, or a Markdown horizontal rule, ends whatever was being written.
    2. A PAGE heading, then a PANEL heading -- after `#` markers and `**` are stripped.
    3. Outside any panel -- before the first heading, or between a PAGE heading and its
       first PANEL -- prose is the title page or a note on the page; anything that would
       belong to a panel is refused.
    4. Inside one, a directive; then a label with its text on the line (a caption, a sound
       effect, with its text on the line or under it, or a cue whose name is in the
       panel's cast with its line after it), which wins even over a label waiting for its
       text; then the line a label is waiting for, whatever it looks like; then a
       continuation of the speech or caption being written; then a cue alone on its line;
       then prose. A balloon number before a label is set aside first.
    """

    def __init__(
        self, source: Path | None, cast: frozenset[str], panel_casts: list[frozenset[str]]
    ) -> None:
        self.source = source
        self.cast = cast
        # Each panel's own cast, from its `@cast:` directives, in heading order: a line's
        # speaker may be cast further down the panel.
        self.panel_casts = panel_casts
        self.drafts: list[_PanelDraft] = []
        self.current: _PanelDraft | None = None
        self.page: str | None = None
        self.notes: list[_Note] = []
        self.title_page: list[str] = []
        self.page_notes: dict[str, list[str]] = {}
        # A label waiting for its text on the next line.
        self.pending: _Pending | None = None
        # The speech or caption being written. Everything up to a blank line is one
        # balloon or box, so a line a writer wrapped by hand belongs to it.
        self.writing: dict[str, Any] | None = None
        # A name in capitals outside any panel, which is a cue if a line follows it.
        self.loose_cue: tuple[str, int] | None = None
        # The open PAGE heading, if it stated a count, and the panels under it so far.
        self.page_heading: tuple[int, _PageHeading] | None = None
        # Every page, in order, with the panels under its heading.
        self.pages: list[_PageDraft] = []
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
            self.pages.append(_PageDraft(label=page.label, line=number))
            self.current = None
            self.page_heading = (number, page) if page.count is not None else None
            self.panels_on_page = 0
            return True
        draft = _read_panel_heading(line, number, self.page)
        if draft is None:
            return False
        for prose in draft.description:
            _check_prose(prose, number, self.source)
        self.end_of_item()
        self.current = draft
        self.drafts.append(draft)
        if self.pages:
            self.pages[-1].drafts.append(draft)
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
        if self.tiers(line, number):
            return
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
        _no_tiers_here(line, number, self.source)
        if _apply_directive(line, current, number, self.source):
            # A directive leaves a waiting label waiting, but ends a speech.
            self.writing = None
            return
        labelled = self.unnumbered(line)
        if self.inline_label(labelled, number, current):
            return
        if self.pending is not None:
            self.fulfil(written, current)
            return
        # A line that looks like a cue still starts a new speech, so two speeches with no
        # blank line between them stay two speeches, as they always have.
        if self.writing is not None and not _looks_like_a_cue(labelled):
            self.writing["text"] = f"{self.writing['text']} {written}"
            return
        self.writing = None
        if self.cue_alone(labelled, number):
            return
        # Prose. Never interpreted: it is the panel's description, read out as it is.
        current.description.append(_check_prose(written, number, self.source))

    def tiers(self, line: str, number: int) -> bool:
        """`@tiers: 2 1 2` between a PAGE heading and its first panel: that page's tiers."""
        directive = DIRECTIVE.match(line)
        if directive is None or directive.group(1) != "tiers":
            return False
        page = self.pages[-1] if self.pages else None
        if page is None:
            _no_tiers_here(line, number, self.source)
            return False
        if page.tiers is not None:
            raise ScriptSyntaxError(
                f"line {number}: '@tiers' is written twice for PAGE {page.label}; the first is on "
                f"line {page.tiers_line}",
                source=self.source,
                line=number,
                rule="duplicate-key",
            )
        counts = [int(count) for count in re.findall(r"\d+", directive.group(2))]
        if not counts or 0 in counts:
            raise ScriptSyntaxError(
                f"line {number}: '@tiers' is how many panels each tier holds, from the top, as "
                "'@tiers: 2 1 2'",
                source=self.source,
                line=number,
                rule="page-layout",
            )
        page.tiers, page.tiers_line = counts, number
        return True

    def cast_here(self) -> frozenset[str]:
        """The open panel's cast: the front matter's, and what its own `@cast:` adds."""
        return self.cast | self.panel_casts[len(self.drafts) - 1]

    def unnumbered(self, line: str) -> str:
        """A line with a balloon number taken off, when what follows it is a label.

        Otherwise the line stands as written: `1 MORE TIME`, wrapped onto a line of its
        own, is the end of a speech, not a numbered cue for a character called MORE TIME.
        """
        number = BALLOON_NUMBER.match(line)
        if number is None:
            return line
        rest = line[number.end() :]
        inline = INLINE_CUE.match(rest)
        if (
            CAPTION_LABEL.match(rest)
            or SFX_LINE.match(rest)
            or BARE_SFX.match(rest)
            or (inline is not None and inline.group("name").strip() in self.cast_here())
            or (
                _looks_like_a_cue(rest)
                and (rest.endswith(":") or _cue_name(rest) in self.cast_here())
            )
        ):
            return rest
        return line

    def inline_label(self, line: str, number: int, current: _PanelDraft) -> bool:
        """A caption or a sound effect, or a cast member's cue with its line after it.

        These win even over a label waiting for its text: `BOB (whisper)` and then
        `CAPTION: Later.` is a caption, and Bob has nothing to say. `CAPTION` and `SFX`
        are never a speaker, so a caption or a sound effect with its text to follow wins
        too. A cue alone does not: the line under a cue is its line, whatever it looks
        like -- `OK.` is spoken.
        """
        caption = CAPTION_LABEL.match(line)
        if caption is not None:
            self.abandon()
            self.writing = None
            fields = self.caption(caption, number)
            if not caption.group("text"):
                self.pending = _Pending("caption", fields, number)
                return True
            # A caption on its line is complete: the line under it is not more of it.
            current.add({"caption": {**fields, "text": caption.group("text")}}, number)
            return True
        effect = _read_sfx(line, number, self.source)
        if effect is not None:
            self.abandon()
            self.writing = None
            payload, text = effect
            if text is None:
                self.pending = _Pending("sfx", payload, number)
            else:
                current.add({"sfx": {**payload, "text": text}}, number)
            return True
        cue = INLINE_CUE.match(line)
        if cue is None:
            return False
        name = cue.group("name").strip()
        modifiers = _modifiers(cue.group("mods"))
        # Somebody who speaks from off panel, or in voice over, is not drawn, so need not
        # be in the cast: `PHONE (OP): Ring.` is a line, as `PHONE (OP)` above it would be.
        unseen = any(word in OFF_PANEL or word in VOICE_OVER for word in modifiers)
        if name not in self.cast_here() and not unseen:
            self.not_a_speaker(name, number, current)
            return False
        self.abandon()
        verb, payload = _line_for(name, _modifiers(cue.group("mods")), number, self.source)
        payload["text"] = cue.group("text")
        current.add({verb: payload}, number)
        self.writing = payload
        return True

    def not_a_speaker(self, name: str, number: int, current: _PanelDraft) -> None:
        """`NAME: text` in capitals with NAME not in the cast: read as it would otherwise be.

        A writer's `NOTE: redraw this` is not dialogue, and becomes prose. But it looks
        like dialogue, and a misspelled speaker looks exactly the same, so it is noted.
        A name in lower case -- `Later: they meet` -- is ordinary prose, and is not.
        """
        letters = [character for character in name if character.isalpha()]
        if self.pending is not None or not letters or not all(c.isupper() for c in letters):
            return
        read_as = "part of the speech above" if self.writing is not None else "prose"
        self.notes.append(
            _Note(
                "looks-like-dialogue",
                f"'{name}:' is set like a line of dialogue, but {name} is not in this panel's "
                f"cast, so the line is read as {read_as}. If {name} speaks, add them to the cast",
                number,
                draft=current,
                tail=("line", number - current.line),
            )
        )

    def fulfil(self, written: str, current: _PanelDraft) -> None:
        """The line a label was waiting for: its text, whatever it looks like."""
        pending = self.pending
        if pending is None:  # pragma: no cover -- only called with one waiting
            return
        self.pending = None
        payload = {**pending.payload, "text": written}
        current.add({pending.verb: payload}, pending.line)
        # A speech or a caption runs on to a blank line; a sound effect is one line.
        self.writing = payload if pending.verb != "sfx" else None

    def cue_alone(self, line: str, number: int) -> bool:
        """A cue on a line of its own, its line to follow."""
        cue = _read_cue(line)
        if cue is None:
            return False
        name, modifiers = cue
        verb, payload = _line_for(name, modifiers, number, self.source)
        self.pending = _Pending(verb, payload, number, name=name)
        return True

    def caption(self, label: re.Match[str], number: int) -> dict[str, Any]:
        """A caption's fields from its label: the kind, and who speaks it, if anyone."""
        speaker = (label.group("speaker") or "").strip() or None
        kind = _caption_kind(speaker, _modifiers(label.group("mods")), number, self.source)
        return {"kind": kind.value, **({"by": speaker} if speaker else {})}

    def abandon(self) -> None:
        """A label with nothing under it: its next line was blank, a heading or a label."""
        pending = self.pending
        self.pending = None
        if pending is None or self.current is None:
            return
        if pending.verb == "sfx":
            raise ScriptSyntaxError(
                f"line {pending.line}: an SFX cue with no sound after it; write the sound on "
                "the next line, or after the colon, as 'SFX: BLAM'",
                source=self.source,
                line=pending.line,
            )
        if pending.verb == "caption" and not pending.name:
            raise ScriptSyntaxError(
                f"line {pending.line}: a caption with no text; write it after the colon, as "
                "'CAPTION: Midnight.', or on the line under the label",
                source=self.source,
                line=pending.line,
            )
        self.notes.append(
            _Note(
                "looks-like-dialogue",
                f"{pending.name} is a cue with nothing said under it: the line after it is "
                "blank, or is not a line of dialogue. Write the line under the cue, or delete it",
                pending.line,
                draft=self.current,
                tail=("cue", pending.line - self.current.line),
            )
        )

    def end_of_item(self) -> None:
        """A blank line, a heading or the end: whatever was being written is finished."""
        self.abandon()
        self.writing = self.loose_cue = None

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
        """What was read, with every panel named and its speech as it will be lettered."""
        for draft in self.drafts:
            for event in draft.events:
                _take_off_quotes(event)
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
        return _Reading(drafts, notes, self.title_page, self.page_notes, self.pages)


def _no_tiers_here(line: str, number: int, source: Path | None) -> None:
    """Refuse `@tiers:` anywhere but right after a PAGE heading, before its first panel."""
    directive = DIRECTIVE.match(line)
    if directive is not None and directive.group(1) == "tiers":
        raise ScriptSyntaxError(
            f"line {number}: '@tiers' lays out a page's panels, so it belongs right after a "
            "PAGE heading, before its first panel",
            source=source,
            line=number,
            rule="page-layout",
        )


def default_tiers(count: int) -> list[int]:
    """How many panels each tier of a page holds, when the script does not say.

    Dark Horse leaves "exact panel layout" to the artist, and the compiler is the artist,
    so it follows a fixed rule: three tiers at most up to nine panels -- the lettering
    height of a page assumes three -- with an odd panel in a tier of its own in the middle,
    and beyond nine, rows of three with the extras in the earlier tiers.

    Example:
        >>> [default_tiers(count) for count in (1, 4, 5, 7, 10)]
        [[1], [2, 2], [2, 1, 2], [2, 3, 2], [3, 3, 2, 2]]
    """
    fixed = {
        1: [1],
        2: [1, 1],
        3: [1, 1, 1],
        4: [2, 2],
        5: [2, 1, 2],
        6: [2, 2, 2],
        7: [2, 3, 2],
        8: [3, 2, 3],
        9: [3, 3, 3],
    }
    if count in fixed:
        return fixed[count]
    rows = -(-count // 3)
    base, extra = divmod(count, rows)
    return [base + 1 if row < extra else base for row in range(rows)]


def _layout(reading: _Reading, page_format: object, source: Path | None) -> PageLayout:
    """The pages a script's PAGE headings lay its panels out on.

    Raises:
        ScriptSyntaxError: Rule `page-layout`, for `@tiers:` that do not add up to the
            page's panels, or a page format that does not validate.
    """
    names = {id(draft): name for name, draft in reading.drafts.items()}
    pages = []
    for page in reading.pages:
        if not page.drafts:
            continue
        panels = [names[id(draft)] for draft in page.drafts]
        counts = page.tiers or default_tiers(len(panels))
        if sum(counts) != len(panels):
            raise ScriptSyntaxError(
                f"line {page.tiers_line}: '@tiers' places {sum(counts)} panels, but PAGE "
                f"{page.label} has {len(panels)}",
                source=source,
                line=page.tiers_line,
                rule="page-layout",
            )
        tiers, start = [], 0
        for count in counts:
            tiers.append({"panels": panels[start : start + count]})
            start += count
        pages.append({"tiers": tiers})
    data: dict[str, Any] = {"pages": pages}
    if page_format is not None:
        data["page"] = page_format
    try:
        return PageLayout.model_validate(normalise_layout(data))
    except ValidationError as exc:
        raise ScriptSyntaxError(
            f"invalid page format: {summarise(exc)}", source=source, rule="page-layout"
        ) from exc


#: Lines only a panel can hold, refused outside one: a directive, a caption, a sound.
_BELONGS_TO_A_PANEL = (DIRECTIVE, CAPTION_LABEL, SFX_LINE, BARE_SFX)


def _cue_name(line: str) -> str:
    """The name a cue line gives, which `_looks_like_a_cue` has already accepted."""
    cue = CUE.match(line)
    return cue.group(1).strip() if cue is not None else line


def _modifiers(parentheticals: str | None) -> list[str]:
    """Every word in a label's parentheticals, in the order written, lower case.

    `(OP) (whisper)` and `(OP, whisper)` say the same. Collected into a list, never a set,
    so what is reported about them does not depend on how a set iterates.

    Example:
        >>> _modifiers("(OP) (Whisper, burst)")
        ['op', 'whisper', 'burst']
    """
    return [
        part.strip().lower()
        for group in re.findall(r"\(([^)]*)\)", parentheticals or "")
        for part in group.split(",")
        if part.strip()
    ]


def _line_for(
    name: str, modifiers: list[str], number: int, source: Path | None
) -> tuple[str, dict[str, Any]]:
    """What a cue's line is: a balloon of some kind, or a voice over's spoken caption.

    Raises:
        ScriptSyntaxError: Rule `invalid-field`, for two kinds of balloon at once, or a
            voice over with a kind of balloon it does not have.
    """
    kinds = list(
        dict.fromkeys(KIND_MODIFIERS[word] for word in modifiers if word in KIND_MODIFIERS)
    )
    off_panel = any(word in OFF_PANEL for word in modifiers)
    if any(word in VOICE_OVER for word in modifiers):
        if off_panel:
            raise ScriptSyntaxError(
                f"line {number}: {name} speaks in voice over, as a caption, and from off "
                "panel, as a balloon; a line is one or the other",
                source=source,
                line=number,
                rule="invalid-field",
            )
        small = [word for word in modifiers if word in SMALL_TYPE]
        if kinds or small:
            what = kinds[0].value if kinds else small[0]
            raise ScriptSyntaxError(
                f"line {number}: {name} speaks in voice over, which is lettered as a caption "
                f"and has no balloon to be {what} in",
                source=source,
                line=number,
                rule="invalid-field",
            )
        return "caption", {"by": name, "kind": CaptionKind.SPOKEN.value}
    if len(kinds) > 1:
        raise ScriptSyntaxError(
            f"line {number}: {name}'s line cannot be both {kinds[0].value} and "
            f"{kinds[1].value}; a balloon has one kind",
            source=source,
            line=number,
            rule="invalid-field",
        )
    kind = kinds[0] if kinds else BalloonKind.SPEECH
    payload: dict[str, Any] = {"by": name, "kind": kind.value}
    if any(word in SMALL_TYPE for word in modifiers):
        payload["size"] = "small"
    if off_panel:
        # A side is only a side beside a marker: `(left)` alone is a note for the artist.
        side = next((SIDES[word] for word in modifiers if word in SIDES), None)
        payload["off_panel"] = side.value if side is not None else True
    return "say", payload


def _caption_kind(
    speaker: str | None, modifiers: list[str], number: int, source: Path | None
) -> CaptionKind:
    """A caption's kind from its parentheticals: spoken, if it names a speaker and no kind.

    Raises:
        ScriptSyntaxError: An unknown kind, or two.
    """
    kinds: list[CaptionKind] = []
    for word in modifiers:
        if word in VOICE_OVER:
            kinds.append(CaptionKind.SPOKEN)
        elif word in CAPTION_KINDS:
            kinds.append(CAPTION_KINDS[word])
        else:
            known = ", ".join([*sorted(CAPTION_KINDS), "voice over"])
            raise ScriptSyntaxError(
                f"line {number}: unknown caption kind '{word}'; known kinds are {known}",
                source=source,
                line=number,
            )
    distinct = list(dict.fromkeys(kinds))
    if len(distinct) > 1:
        raise ScriptSyntaxError(
            f"line {number}: a caption cannot be both {distinct[0].value} and {distinct[1].value}",
            source=source,
            line=number,
            rule="invalid-field",
        )
    if distinct:
        return distinct[0]
    return CaptionKind.SPOKEN if speaker else CaptionKind.LOCALE


def _take_off_quotes(event: dict[str, Any]) -> None:
    """The quotation marks a writer put around speech, which the lettering adds itself.

    A balloon takes no quotation marks, so one enclosing pair is taken off, when nothing
    inside is quoted. A spoken caption's are the compiler's to add -- one opening each box,
    one closing the speaker's last -- so the writer's opening mark is taken off, and its
    closing one with it. French typography's spaces inside guillemets go too.
    """
    if "say" in event:
        event["say"]["text"] = _unquoted(event["say"]["text"])
    elif "caption" in event and event["caption"].get("kind") == CaptionKind.SPOKEN.value:
        event["caption"]["text"] = _unquoted_spoken(event["caption"]["text"])


def _unquoted(text: str) -> str:
    """Speech without one enclosing pair of quotation marks, if nothing inside is quoted."""
    for opening, closing in _QUOTE_PAIRS:
        if len(text) > 1 and text.startswith(opening) and text.endswith(closing):
            inner = text[1:-1].strip(_QUOTE_SPACE)
            if inner and not any(mark in inner for mark in (*_OPENING_QUOTES, *_CLOSING_QUOTES)):
                return inner
    return text


def _unquoted_spoken(text: str) -> str:
    """A spoken caption without the writer's opening mark, nor its closing one if it has one.

    Blambot's run opens every box with a quote and closes only the last, so a box may well
    open and not close.
    """
    if not text.startswith(_OPENING_QUOTES):
        return text
    inner = text[1:].lstrip(_QUOTE_SPACE)
    if inner.endswith(_CLOSING_QUOTES):
        closed = inner[:-1].rstrip(_QUOTE_SPACE)
        if not any(mark in closed for mark in (*_OPENING_QUOTES, *_CLOSING_QUOTES)):
            inner = closed
    return inner or text


@dataclass
class _ScannedPanel:
    """What the cast pre-pass needs of a panel: where it is, whom it casts, what it is over."""

    page: str | None
    label: str
    cast: set[str] = field(default_factory=set)
    over: str | None = None


def _panel_casts(body: str) -> list[frozenset[str]]:
    """Each panel's cast from its `@cast:` directives, and what it inherits by `@over:`.

    In the order of the headings. Read before the panels are, because a cue on one line may
    name a cast member a directive further down the same panel adds, or the panel it is over.
    """
    scanned: list[_ScannedPanel] = []
    page: str | None = None
    for raw in body.split("\n"):
        line = _recognisable(raw.strip())
        heading = _read_page_heading(line)
        if heading is not None:
            page = heading.label
            continue
        draft = _read_panel_heading(line, 0, page)
        if draft is not None:
            scanned.append(_ScannedPanel(page=page, label=draft.label))
            continue
        directive = DIRECTIVE.match(line)
        if directive is None or not scanned:
            continue
        if directive.group(1) == OVER_KEY:
            scanned[-1].over = directive.group(2).strip()
        elif directive.group(1) == "cast":
            try:
                members = load(directive.group(2).strip())
            except yaml.YAMLError:
                continue  # reported, at its line, when the panel itself is read
            if isinstance(members, dict):
                scanned[-1].cast.update(str(name) for name in members)
    return _inherited_casts(scanned)


def _inherited_casts(scanned: list[_ScannedPanel]) -> list[frozenset[str]]:
    """Each scanned panel's cast, with that of every panel up its `@over:` chain."""
    labels = [panel.label for panel in scanned]
    paged = len(set(labels)) != len(labels)
    names = [f"{panel.page}-{panel.label}" if paged else panel.label for panel in scanned]
    by_name = dict(zip(names, scanned, strict=True))

    def cast_of(panel: _ScannedPanel, seen: frozenset[str]) -> frozenset[str]:
        if panel.over is None:
            return frozenset(panel.cast)
        label = _number_label(panel.over)
        here = f"{panel.page}-{label}" if panel.page is not None else None
        parent = by_name.get(here or "") or by_name.get(label)
        if parent is None or parent.label in seen:
            # A missing parent or a cycle is reported when the panels are composed.
            return frozenset(panel.cast)
        return frozenset(panel.cast) | cast_of(parent, seen | {panel.label})

    return [cast_of(panel, frozenset()) for panel in scanned]


def _reserved_name(cast: object) -> str | None:
    """A cast member whose id is a label, `CAP` say, which could never speak."""
    if not isinstance(cast, dict):
        return None
    return next((str(name) for name in cast if str(name).lower() in RESERVED_NAMES), None)


def _reserved_message(name: str) -> str:
    """Why a cast member cannot be called `name`."""
    return (
        f"'{name}' is reserved: a line that starts with it is a caption or a sound effect, "
        "never a speaker's cue. Give the cast member another id"
    )


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
    reader = _Reader(source, cast, _panel_casts(body))
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
        draft.camera[key] = _camera_word(key, value, number, source, draft.label)
        return True
    if key in (OVER_KEY, DESCRIPTION_KEY):
        # Kept as written. YAML would read the panel name `07` as the number 7, and a
        # description `9:14, and Alice waves` as a mapping -- or `9:14` as 554.
        draft.settings[key] = value
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
    reserved = _reserved_name(draft.settings[key]) if key == "cast" else None
    if reserved is not None:
        raise ScriptSyntaxError(
            f"line {number}: {_reserved_message(reserved)}",
            source=source,
            line=number,
            rule="invalid-field",
        )
    return True


def _camera_word(key: str, value: str, number: int, source: Path | None, panel: str) -> str:
    """A shot or an angle as the language spells it, from English or from French.

    Raises:
        ScriptSyntaxError: Rule `invalid-field`, for a word that is neither, naming both
            the English and the French ones.
    """
    english = [item.value for item in (ShotType if key == "shot" else CameraAngle)]
    french = FRENCH_SHOTS if key == "shot" else FRENCH_ANGLES
    if value in english:
        return value
    translated = french.get(_folded(value))
    if translated is not None:
        return translated
    named = sorted({_FRENCH_SPELLINGS.get(word, word) for word in french if len(word) > 3})
    raise ScriptSyntaxError(
        f"line {number}: in PANEL {panel}, unknown {key} '{value}'; known are "
        f"{', '.join(english)}, or in French {', '.join(named)}",
        source=source,
        line=number,
        rule="invalid-field",
    )


# The French names as written, for a message: the table compares them folded.
_FRENCH_SPELLINGS = {
    "plan d ensemble": "plan d'ensemble",
    "plan americain": "plan américain",
    "plan rapproche taille": "plan rapproché taille",
    "plan mi moyen": "plan mi-moyen",
    "plan rapproche poitrine": "plan rapproché poitrine",
    "plan rapproche": "plan rapproché",
    "plan rapproche epaule": "plan rapproché épaule",
    "plan epaule": "plan épaule",
    "tres gros plan": "très gros plan",
    "plongee": "plongée",
    "contre plongee": "contre-plongée",
}


def _read_cue(line: str) -> tuple[str, list[str]] | None:
    """Parse a character cue -- its name and its modifiers -- or return None if not one."""
    if not _looks_like_a_cue(line):
        return None
    cue = CUE.match(line)
    if cue is None:  # pragma: no cover -- _looks_like_a_cue already matched
        return None
    return cue.group(1).strip(), _modifiers(cue.group(2))


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
        directives: The line each of its directives was written on, by the path in the
            panel it sets: `("setting",)` for `@setting:`.
    """

    heading: int
    events: tuple[int, ...]
    directives: Mapping[tuple[str, ...], int] = field(default_factory=dict[tuple[str, ...], int])


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
        layout: The pages its PAGE headings lay its panels out on; none without them.
    """

    panels: dict[str, PanelIR]
    lines: dict[str, PanelLines]
    notes: tuple[ScriptNote, ...] = ()
    descriptions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    title_page: tuple[str, ...] = ()
    page_notes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    layout: PageLayout = field(default_factory=PageLayout)


def parse_script_document(text: str, *, source: Path | None = None) -> ScriptDocument:
    r"""Parse comic script, keeping the line each panel and each of its events is on.

    `parse_script` is this, less the lines. A checker reporting a fault in a panel that
    did validate -- a balloon over the word limit, say -- needs to know where it is.

    Example:
        >>> document = parse_script_document(
        ...     "---\ncast: {A: {reference: alice}}\n---\nPANEL 1\nA\nHi.\n"
        ... )
        >>> document.lines["1"]
        PanelLines(heading=4, events=(5,), directives={})
    """
    # Anything that reaches here as a string gets the treatment a file would have had,
    # and the same whatever editor saved it.
    text = normalise_text(text)
    front_matter, body, offset = _split_front_matter(text, source)
    if "pages" in front_matter:
        raise ScriptSyntaxError(
            "a comic script's pages come from its PAGE headings, so its front matter has no "
            "`pages:`; `page:` sets their format",
            source=source,
            rule="page-layout",
        )
    if DESCRIPTION_KEY in front_matter:
        # The front matter is merged under every panel, and a description says what one
        # picture shows. It is a top-level key, so it starts a line of the front matter.
        line = next(
            (
                number
                for number, written in enumerate(text.split("\n")[:offset], start=1)
                if re.match(rf"{DESCRIPTION_KEY}\s*:", written)
            ),
            None,
        )
        raise ScriptSyntaxError(
            f"{f'line {line}: ' if line else ''}{NOT_A_DEFAULT}",
            source=source,
            line=line,
            rule="unknown-key",
        )
    page_format = front_matter.pop("page", None)
    cast = front_matter.get("cast")
    reserved = _reserved_name(cast)
    if reserved is not None:
        line = next(
            (
                number
                for number, written in enumerate(text.split("\n"), start=1)
                if re.search(rf"(?<![\w-]){re.escape(reserved)}\s*:", written)
            ),
            None,
        )
        raise ScriptSyntaxError(
            f"{f'line {line}: ' if line else ''}{_reserved_message(reserved)}",
            source=source,
            line=line,
            rule="invalid-field",
        )
    reading = _read_script(
        body, source, offset=offset, cast=frozenset(cast if isinstance(cast, dict) else ())
    )
    panels = reading.drafts

    if not panels:
        raise ScriptSyntaxError("no PANEL headings found", source=source)

    notes = list(reading.notes)
    layout = _layout(reading, page_format, source)
    return ScriptDocument(
        panels=_validate(panels, front_matter, source, notes),
        lines={
            name: PanelLines(
                heading=draft.line,
                events=tuple(draft.event_lines),
                directives=dict(draft.directive_lines),
            )
            for name, draft in panels.items()
        },
        notes=tuple(notes),
        descriptions={name: tuple(draft.description) for name, draft in panels.items()},
        title_page=tuple(reading.title_page),
        page_notes={page: tuple(lines) for page, lines in reading.page_notes.items()},
        layout=layout,
    )


def parse_script(text: str, *, source: Path | None = None) -> dict[str, PanelIR]:
    """Parse comic script into one validated panel per PANEL heading."""
    return parse_script_document(text, source=source).panels


def _off_panel(
    document: dict[str, Any],
    name: str,
    draft: _PanelDraft,
    notes: list[ScriptNote],
    source: Path | None,
) -> dict[str, Any]:
    """A panel with everybody who speaks from off panel in it left out of it.

    Off panel means in the scene but not in the frame. The front matter is the scene's
    cast, so `ALICE (OP)` leaves Alice out of this panel -- and out of every staging
    relation that names her, each with a note, since that changes what the panel stages.
    All but one kind: `BOB looking_at ALICE` still holds, since Bob may look toward the
    side of the frame she is heard from.
    It is worked out from the panel's own lines, after its `@over:` chain and the front
    matter are merged, so a panel over this one does not inherit her absence. Where she
    was written to stand, `at: left_third` say, is the side her tail ends on, unless the
    cue named one.

    Raises:
        ScriptSyntaxError: Rule `off-panel-speaker`, for a speaker the panel's own
            `@cast:` draws, or one who speaks both on and off panel in it.
    """
    speakers: dict[str, int] = {}
    drawn: dict[str, int] = {}
    for index, event in enumerate(draft.events):
        say = event.get("say")
        if say is None:
            continue
        side = speakers if say.get("off_panel", False) is not False else drawn
        side.setdefault(say["by"], index)
    own_cast = draft.settings.get("cast")
    for speaker, index in speakers.items():
        line = draft.event_lines[index]
        if speaker in drawn:
            later = draft.event_lines[max(index, drawn[speaker])]
            raise ScriptSyntaxError(
                f"line {later}: {speaker} speaks both on and off panel in PANEL {name}; a "
                "speaker is drawn in a panel, or speaks from outside it",
                source=source,
                line=later,
                rule="off-panel-speaker",
            )
        if isinstance(own_cast, dict) and speaker in own_cast:
            raise ScriptSyntaxError(
                f"line {line}: {speaker} speaks from off panel, but this panel's own @cast: "
                "draws them; leave them out of it",
                source=source,
                line=line,
                rule="off-panel-speaker",
            )
    cast = document.get("cast")
    leaving = [speaker for speaker in speakers if isinstance(cast, dict) and speaker in cast]
    if not leaving or not isinstance(cast, dict):
        return document
    document = {
        **document,
        "cast": {key: value for key, value in cast.items() if key not in leaving},
    }
    document["script"] = [_on_their_side(event, cast) for event in document.get("script", [])]
    staging = document.get("staging")
    if isinstance(staging, list):
        kept = []
        for index, relation in enumerate(staging):
            named = next((speaker for speaker in leaving if names(relation, speaker)), None)
            if named is None or _looks_toward(relation, named, leaving):
                kept.append(relation)
                continue
            line = draft.event_lines[speakers[named]]
            notes.append(
                ScriptNote(
                    rule="dropped-relation",
                    message=(
                        f"line {line}: '{relation_text(relation)}' does not apply in PANEL "
                        f"{name}, where {named} speaks from off panel and is not drawn"
                    ),
                    line=line,
                    path=(name, "staging", index),
                )
            )
        document["staging"] = kept
    return document


def _looks_toward(relation: object, speaker: str, leaving: Collection[str]) -> bool:
    """Whether a relation is somebody still drawn looking at a speaker who is not."""
    if isinstance(relation, str):
        words = relation.split()
        if len(words) != 3:
            return False
        subject, predicate, target = words
    elif isinstance(relation, dict):
        subject, predicate, target = (
            relation.get(key) for key in ("subject", "predicate", "object")
        )
    else:
        return False
    return predicate == Predicate.LOOKING_AT.value and target == speaker and subject not in leaving


def _on_their_side(event: dict[str, Any], cast: dict[str, Any]) -> dict[str, Any]:
    """An off-panel line with no side named, given the side its speaker was written at."""
    say = event.get("say")
    if say is None or say.get("off_panel") is not True:
        return event
    member = cast.get(say["by"])
    at = str(member.get("at", "")) if isinstance(member, dict) else ""
    side = next((value for value in ("left", "right") if at.startswith(value)), None)
    return event if side is None else {"say": {**say, "off_panel": side}}


def _over_target(target: str, name: str, draft: _PanelDraft, names: Collection[str]) -> str:
    """The panel an `@over:` names, by the name the script gave it.

    A label is looked up on the same page first -- `@over: 1` on page two is panel `2-1`
    -- so it does not change meaning when another page's numbers start again; then as a
    whole name, `1-1`. A label is read as a heading's is, so `@over: 07` is panel `7`.
    """
    label = _number_label(target.strip())
    on_this_page = f"{draft.page}-{label}"
    found = on_this_page if draft.page is not None and on_this_page in names else label
    if found == name:
        raise CompositionError(
            f"panel '{name}' is over '{target}', which names its own panel; name the panel "
            "it changes",
            loc=("panels", name, OVER_KEY),
        )
    return found


def _composed(panels: dict[str, _PanelDraft], source: Path | None) -> dict[str, dict[str, Any]]:
    """Every panel as a whole document, its `@over:` chain resolved.

    The same merge YAML's `over:` gets (`compose.resolve_overrides`): a panel's own
    directives win, and lists are replaced, never joined. A script panel always has its
    own `script`, possibly empty, so dialogue is never inherited -- only what the panel
    over it set up.

    Raises:
        ScriptSyntaxError: Rule `composition`, at the `@over:` line, for a panel that does
            not exist, a cycle, or a panel over itself.
    """
    documents = {name: draft.as_document() for name, draft in panels.items()}
    try:
        for name, draft in panels.items():
            target = documents[name].get(OVER_KEY)
            if isinstance(target, str):
                documents[name][OVER_KEY] = _over_target(target, name, draft, documents)
        return resolve_overrides(documents)
    except CompositionError as exc:
        name = str(exc.loc[1]) if len(exc.loc) > 1 else ""
        line = panels[name].directive_lines.get((OVER_KEY,)) if name in panels else None
        raise ScriptSyntaxError(
            f"line {line}: {exc}" if line else str(exc),
            source=source,
            line=line,
            rule="composition",
        ) from exc


def _validate(
    panels: dict[str, _PanelDraft],
    front_matter: dict[str, Any],
    source: Path | None,
    notes: list[ScriptNote],
) -> dict[str, PanelIR]:
    """Validate each drafted panel over the front matter, reporting the first fault.

    `@over:` is resolved first, then the front matter merged under each panel, as a YAML
    scene's defaults are merged under each of its panels.
    """
    composed = _composed(panels, source)
    result: dict[str, PanelIR] = {}
    for name, draft in panels.items():
        settled, dropped = settle(merge(front_matter, composed[name]))
        line = draft.directive_lines.get(("cast",)) or draft.directive_lines.get((OVER_KEY,))
        line = line or draft.line
        notes.extend(
            ScriptNote(
                rule="dropped-relation",
                message=(
                    f"line {line}: '{relation_text(item.relation)}' does not apply in PANEL "
                    f"{name}, which leaves {item.actor} out of it"
                ),
                line=line,
                path=(name, "staging", item.index),
            )
            for item in dropped
        )
        combined = _off_panel(settled, name, draft, notes, source)
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
