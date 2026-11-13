"""The intermediate representation: a validated semantic scene graph.

This is the language's real definition. The YAML surface syntax is one way to
produce it; a comic-script frontend will be another. Nothing here carries a
coordinate -- computing those is the solver's job.

Validation is strict on purpose. Panel sources are untrusted input, and a typo in a
predicate or an actor id should be a clear error at parse time rather than a silently
wrong picture.
"""

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    ModelWrapValidatorHandler,
    Tag,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import InitErrorDetails

from scenet.emphasis import EmphasisError, parse
from scenet.errors import RuleViolationError

__all__ = [
    "AnchorX",
    "BalloonKind",
    "CameraAngle",
    "CameraSpec",
    "CaptionEvent",
    "CaptionKind",
    "CaptionTone",
    "CastMember",
    "Column",
    "Corner",
    "Direction",
    "Face",
    "Facing",
    "Fit",
    "FontSpec",
    "Horizon",
    "Inset",
    "InsetOrder",
    "LetteringSpec",
    "Mark",
    "Mass",
    "MassKind",
    "PageFormat",
    "PageLayout",
    "PageSpec",
    "Palette",
    "PanelIR",
    "PanelPlacement",
    "PanelSpec",
    "PlacementZone",
    "Plane",
    "Predicate",
    "Relation",
    "SayEvent",
    "SettingSpec",
    "SfxEvent",
    "SfxSize",
    "ShotType",
    "Side",
    "Spans",
    "StackedPanel",
    "Strict",
    "Tier",
    "TimeOfDay",
    "TypeSize",
    "Weather",
    "check_placements",
]

# Depth-first search marks, used by the ordering cycle check.
_UNVISITED, _ON_STACK, _DONE = 0, 1, 2


class Strict(BaseModel):
    """Reject unknown keys everywhere.

    A misspelled key that is silently ignored produces a panel that is subtly wrong
    with no indication of why, which is the worst possible failure for a language
    meant to be precise.

    Non-finite numbers are refused for the same reason. `.inf` and `.nan` are valid
    YAML floats, but every number in a document is a length, a weight or a fraction,
    and an infinite one reached the solver -- where kiwisolver ended the interpreter
    without an exception to report.
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, use_attribute_docstrings=True
    )


#: Characters XML 1.0 cannot hold at all, escaped or not: the C0 controls other than tab,
#: line feed and carriage return, lone surrogates, and the two noncharacters U+FFFE and
#: U+FFFF. A string reaching the SVG with one in it makes a document no parser accepts.
_NOT_IN_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _holdable(value: str) -> str:
    """Refuse a string an SVG cannot hold, naming the character so it can be found."""
    found = _NOT_IN_XML.search(value)
    if found is not None:
        raise ValueError(
            f"contains U+{ord(found.group()):04X}, a control character an SVG cannot "
            "hold; delete it"
        )
    return value


#: A string that is written into the SVG -- dialogue, a caption, an actor id. Refused at
#: parse time rather than escaped at emission, because there is no escaping it: XML 1.0
#: has no way to write these characters, not even as a character reference.
SvgText = Annotated[str, AfterValidator(_holdable)]


def _balanced(value: str) -> str:
    """Refuse lettering whose emphasis is opened and never closed, saying where it opened."""
    try:
        parse(value)
    except EmphasisError as exc:
        raise RuleViolationError(str(exc), rule="unbalanced-emphasis") from exc
    return value


#: A line that is lettered -- dialogue or a caption -- and so may stress a word by writing
#: it between underscores: `I _told_ you`. See :mod:`scenet.emphasis`.
LetteredText = Annotated[SvgText, AfterValidator(_balanced)]


def unholdable(value: str) -> str | None:
    r"""Why an SVG cannot hold a string, or None when it can.

    For a frontend that checks text before it reaches a model, and wants the finding at
    the line it was written on rather than wherever validation would put it.

    Example:
        >>> from scenet.ir import unholdable
        >>> unholdable("Alice waits.") is None
        True
        >>> unholdable("Alice \x07 waits.")
        'contains U+0007, a control character an SVG cannot hold; delete it'
    """
    try:
        _holdable(value)
    except ValueError as exc:
        return str(exc)
    return None


def as_one_line(value: object) -> object:
    """Prose as it is read: every run of whitespace one space, and none at either end.

    Line breaks in a description are how it was typed, not part of what it says. Python's
    idea of whitespace includes U+000B and U+000C, which is how Word writes a manual line
    break and a page break, so text pasted from it reads as it looks. Anything else passes
    unchanged, for validation to refuse.
    """
    return " ".join(value.split()) if isinstance(value, str) else value


def _said(value: str) -> str:
    """Refuse a description with nothing in it, which would name the panel with nothing."""
    if not value:
        raise RuleViolationError(
            "a description says what the panel shows; leave it out to have one generated",
            rule="invalid-field",
        )
    return value


#: What a panel shows, in words, for a reader who cannot see it -- one line of prose,
#: carried and never interpreted.
Description = Annotated[SvgText, BeforeValidator(as_one_line), AfterValidator(_said)]


class ShotType(StrEnum):
    """How tightly the camera frames the cast.

    Ordered from widest to tightest, and the order is enforced by a test: reading down
    the ladder, the figure never gets smaller.

    A shot type is defined by two things in two different units. The **crop landmark**
    is anatomical -- the waist, the chest, the shoulders -- which is what stops a shot
    type baking in one body and one pose; naming a fraction of panel height instead
    would do exactly that. The **headroom** is a plain fraction of panel height, because
    it is about composition within the frame rather than anatomy.
    `docs/reference/shot_types.md` is normative.

    The requested shot is an *upper bound on tightness*, not a promise. If the cast
    cannot fit across the panel at that framing the camera retreats, and says so in
    :attr:`CompileResult.notes <scenet.pipeline.CompileResult.notes>`.

    Example:
        >>> from scenet import ShotType
        >>> ShotType("close_up")
        <ShotType.CLOSE_UP: 'close_up'>

    See Also:
        :class:`CameraSpec <scenet.ir.CameraSpec>`, whose `shot` takes one.
        :class:`Landmark <scenet.assets.contract.Landmark>`, the crop lines a shot names.
    """

    LONG_SHOT = "long_shot"
    WIDE = "wide"
    FULL_SHOT = "full_shot"
    MEDIUM_FULL = "medium_full"
    COWBOY = "cowboy"
    MEDIUM_SHOT = "medium_shot"
    MEDIUM_CLOSE_UP = "medium_close_up"
    CLOSE_UP = "close_up"
    BIG_CLOSE_UP = "big_close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"


class CameraAngle(StrEnum):
    r"""The camera's height relative to the subject.

    Affects headroom rather than perspective: this is a flat, orthographic compiler, so
    a tilted camera does not foreshorten anything. What it changes is how much air sits
    above the head -- which is the compositional cue readers actually take from an
    angle, and one that survives being drawn flat.

    A **low** camera looks up and the subject looms, so the head rides high in the frame
    with little space above it. A **high** camera looks down, so the head sits lower and
    more space opens up above. See
    :func:`headroom_for <scenet.solve.camera.headroom_for>` for the exact factors.

    Example:
        >>> from scenet import CameraAngle, compile_source
        >>> core = compile_source("camera: {angle: low}\ncast: {a: {reference: alice}}").core
        >>> core.camera.angle is CameraAngle.LOW
        True

    See Also:
        :class:`CameraSpec <scenet.ir.CameraSpec>`, whose `angle` takes one.
        :class:`ShotType <scenet.ir.ShotType>`, the other half of the camera.
    """

    LOW = "low"
    EYE_LEVEL = "eye_level"
    HIGH = "high"


class AnchorX(StrEnum):
    """Where along the panel width an actor would like to stand.

    Horizontal only. Actors stand on a ground line, so their vertical position is
    derived from the camera rather than requested -- which is why this has no vertical
    counterpart and :class:`PlacementZone <scenet.ir.PlacementZone>`, used for balloons, does.

    These are *weak* preferences. Non-overlap and declared left-to-right ordering are
    required constraints and will override an anchor without complaint; two actors both
    asking for `center` will simply be pushed apart around it.

    Example:
        >>> from scenet import AnchorX, compile_source
        >>> core = compile_source("cast: {a: {reference: alice, at: left_third}}").core
        >>> AnchorX("left_third") is AnchorX.LEFT_THIRD
        True
        >>> core.actors[0].bounds.centre.x < core.width / 2
        True

    See Also:
        :class:`CastMember <scenet.ir.CastMember>`, whose `at` takes one.
        :class:`Predicate <scenet.ir.Predicate>`, to stage two actors against each other instead.
    """

    LEFT_EDGE = "left_edge"
    LEFT_THIRD = "left_third"
    CENTRE = "center"
    RIGHT_THIRD = "right_third"
    RIGHT_EDGE = "right_edge"


class TypeSize(StrEnum):
    r"""How large a line of dialogue is lettered, against the panel's dialogue size.

    Dark Horse lists "(small), (burst), and (weak)" among the common indications for
    modified lettering. Blambot, *Small Dialogue / Big Balloon*: "A reduced font size is
    used when a character mutters something, says something to him/herself, or speaks
    sheepishly" -- smaller type, in the room the balloon would have had.

    Example:
        >>> from scenet import TypeSize, compile_source
        >>> def size(text):
        ...     source = "cast: {a: {reference: alice}}\nscript: [{say: " + text + "}]"
        ...     return compile_source(source).core.balloons[0].font_size
        >>> size("{by: a, text: mm., size: small}") < size("{by: a, text: mm.}")
        True
        >>> TypeSize("small") is TypeSize.SMALL
        True

    See Also:
        :class:`SayEvent <scenet.ir.SayEvent>`, whose `size` takes one.
        :class:`LetteringSpec <scenet.ir.LetteringSpec>`, the panel's own dialogue size.
    """

    NORMAL = "normal"
    SMALL = "small"


class Side(StrEnum):
    r"""A side of the panel's frame: where an off-panel speaker is, or where it bleeds.

    An off-panel balloon's tail ends on the frame on this side -- Blambot, *Off-Panel
    Dialogue*: "the tail of the balloon generally butts against the panel border". A panel
    on a page bleeds past the trim on the sides its placement lists.

    Example:
        >>> from scenet import Side, compile_source
        >>> core = compile_source(
        ...     "cast: {a: {reference: alice}}\n"
        ...     "script: [{say: {by: z, text: Over here!, off_panel: right}}]"
        ... ).core
        >>> core.balloons[0].off_panel is Side.RIGHT
        True

    See Also:
        :class:`SayEvent <scenet.ir.SayEvent>`, whose `off_panel` takes one.
        :class:`PanelPlacement <scenet.ir.PanelPlacement>`, whose `bleed` lists them.
    """

    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class PlacementZone(StrEnum):
    r"""Where in the panel a balloon would prefer to sit.

    Two-dimensional, unlike `AnchorX`: an actor is placed along the ground line and
    so only needs a horizontal anchor, whereas a balloon floats and needs both axes.
    These are hints of the weakest priority -- occlusion and reading order override
    them freely.

    Example:
        >>> from scenet import PlacementZone, compile_source
        >>> core = compile_source(
        ...     "cast: {a: {reference: alice}}\n"
        ...     "script: [{say: {by: a, text: Up here., prefer: top_right}}]"
        ... ).core
        >>> PlacementZone("top_right").value
        'top_right'
        >>> core.balloons[0].box.x > core.width / 2
        True

    See Also:
        :class:`SayEvent <scenet.ir.SayEvent>`, whose `prefer` takes one: a preference, which a
        hard rule such as reading order may overrule.
    """

    TOP_LEFT = "top_left"
    TOP_CENTRE = "top_center"
    TOP_RIGHT = "top_right"
    MIDDLE_LEFT = "middle_left"
    MIDDLE_CENTRE = "middle_center"
    MIDDLE_RIGHT = "middle_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTRE = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"

    @property
    def fractions(self) -> tuple[float, float]:
        """The zone's centre as a fraction of panel width and height."""
        vertical, horizontal = self.value.split("_")
        across = {"left": 0.25, "center": 0.5, "right": 0.75}[horizontal]
        down = {"top": 0.2, "middle": 0.5, "bottom": 0.8}[vertical]
        return across, down


class Direction(StrEnum):
    r"""Which way a comic is read: its progression, not the direction of its text.

    `ltr` reads from the top left, as Western comics do; `rtl` from the top right, as manga
    do -- the panels on a page and in a strip, the pages side by side, and the balloons and
    captions in a panel. The words in a balloon are not touched: a manga translated into
    English still reads right to left while each line reads left to right.

    It is the whole document's, written once, as EPUB's `page-progression-direction` is per
    book, whose words these are. Only what reading decides follows it. The scene is never
    mirrored: figures, gaze, staging, tails and sound effects stay as staged, and every
    word that names a place on the panel -- `at:`, `left_of`, `facing:`, `prefer:`, a side
    for `off_panel`, an inset's corner -- means the same place either way.

    Example:
        >>> from scenet import Direction, compile_source
        >>> core = compile_source("direction: rtl\ncast: {a: {reference: alice}}").core
        >>> core.direction is Direction.RTL
        True

    See Also:
        :func:`render_strip <scenet.emit.strip.render_strip>` and
        :func:`render_pages <scenet.emit.page.render_pages>`, which lay panels out in it.
    """

    LTR = "ltr"
    RTL = "rtl"


class Palette(StrEnum):
    r"""What a panel is drawn in: the value ladder in grey, or its twin in colour.

    +----------+----------------------------------------------------------------------------+
    | Palette  | What it draws                                                              |
    +==========+============================================================================+
    | `mono`   | Every value as the grey it is -- **the default**, and what every panel was |
    +----------+----------------------------------------------------------------------------+
    | `tinted` | Every value on the ladder in its twin colour: same rung, same hour         |
    +----------+----------------------------------------------------------------------------+

    **Colour is a twin of value, never a replacement.** A tinted colour has the OKLab
    lightness of the grey it stands for, so in monochrome a tinted panel is the mono one,
    and every decision the compiler makes from a value -- which rung a mass takes, whether
    rain is inked or papered, how a caption is lettered -- is made on the grey. Panel Core
    keeps the grey where it always did and adds the colour beside it.

    Only the ladder is tinted: the masses of a setting, the veil and the falling rain.
    Snow, the paper, the figures and all lettering stay as they are in every palette.

    A closed set of names, not a colour field, for the reason `CaptionTone` is one: an
    open colour would be the language's one open vocabulary, and would let a value break
    the ladder. See :func:`colour_for <scenet.solve.backdrop.colour_for>`.

    Example:
        >>> from scenet import Palette, compile_source
        >>> core = compile_source("palette: tinted\ncast: {a: {reference: alice}}").core
        >>> core.palette is Palette.TINTED, core.as_mono().palette is Palette.MONO
        (True, True)

    See Also:
        :meth:`PanelCore.as_mono <scenet.core.PanelCore.as_mono>`, the same panel in greys.
        :class:`CaptionTone <scenet.ir.CaptionTone>`, whose `warm` a palette colours.
    """

    MONO = "mono"
    TINTED = "tinted"


class Facing(StrEnum):
    """Which way an actor is turned.

    Mirroring the whole puppet, gaze vector included. Defaults to `right`, so a cast
    written left to right ends up looking into the panel rather than out of it.

    Example:
        >>> from scenet import Facing, compile_source
        >>> core = compile_source("cast: {a: {reference: alice, facing: left}}").core
        >>> Facing("left") is Facing.LEFT, core.actors[0].transform.mirrored
        (True, True)

    See Also:
        :class:`CastMember <scenet.ir.CastMember>`, whose `facing` takes one.
    """

    LEFT = "left"
    RIGHT = "right"


class Mark(StrEnum):
    """Something drawn around a character, rather than on them, to say how they are.

    The vocabulary is Mort Walker's, from *The Lexicon of Comicana* (1980), which grew
    out of his 1964 National Cartoonists Society piece "Let's Get Down to Grawlixes".
    The book is tongue-in-cheek, but the terms entered real use, and they are comics'
    own names for comics' own conventions. So the set is closed and citable, and nothing
    in it is invented here.

    +-------------+---------------------------------------------+--------------------------------+
    | Mark        | What it is                                  | What it says                   |
    +=============+=============================================+================================+
    | `plewds`    | Droplets flying off the head                | sweating: effort, heat, nerves |
    +-------------+---------------------------------------------+--------------------------------+
    | `squeans`   | Little starbursts and circles over the head | dizzy, drunk, or sick          |
    +-------------+---------------------------------------------+--------------------------------+
    | `grawlixes` | Symbols over the head standing in for words | swearing                       |
    +-------------+---------------------------------------------+--------------------------------+
    | `briffits`  | A dust cloud left at the feet               | gone, fast                     |
    +-------------+---------------------------------------------+--------------------------------+

    "Emanata" is Walker's general term for these, which is why it names the module that
    draws them and the Core field that holds them.

    A mark is not an expression. A character can be angry *and* sweating, so marks are
    a list that composes with `expression:` rather than a second one. Grawlixes are
    drawn as symbols -- a jarn (spiral), a nittle (bursting star), a bolt and a hash --
    rather than typed: an oath written as `@#$%!` already works, as dialogue.

    All four are drawn **outside** the head circle, in the space balloons are placed
    in. They never move a character. A balloon prefers not to cover them, and covers
    them anyway rather than fail when a panel is too crowded to oblige.

    Example:
        >>> from scenet import Mark, compile_source
        >>> core = compile_source("cast: {a: {reference: alice, marks: [plewds]}}").core
        >>> core.actors[0].marks == (Mark.PLEWDS,)
        True

    See Also:
        :class:`CastMember <scenet.ir.CastMember>`, whose `marks` lists them.
    """

    PLEWDS = "plewds"
    SQUEANS = "squeans"
    GRAWLIXES = "grawlixes"
    BRIFFITS = "briffits"


class Predicate(StrEnum):
    r"""How one actor stands in relation to another.

    Drawn from the spatial subset of the Visual Genome vocabulary rather than invented,
    so a scene stays convertible to and from the scene-graph representations used
    elsewhere in computer vision.

    `left_of` and `right_of` are the load-bearing ones: they are resolved at parse time
    into a linear ordering, because Cassowary cannot express the disjunction "A left of
    B *or* B left of A".

    Example:
        >>> from scenet import Predicate, compile_source
        >>> core = compile_source(
        ...     "cast: {a: {reference: alice}, b: {reference: bob}}\nstaging: [b left_of a]"
        ... ).core
        >>> Predicate("left_of") is Predicate.LEFT_OF
        True
        >>> core.actor("b").bounds.centre.x < core.actor("a").bounds.centre.x
        True

    See Also:
        :class:`Relation <scenet.ir.Relation>`, one predicate between two actors.
    """

    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    IN_FRONT_OF = "in_front_of"
    BEHIND = "behind"
    LOOKING_AT = "looking_at"
    GROUND_SHARED_WITH = "ground_shared_with"


class BalloonKind(StrEnum):
    r"""What kind of balloon carries a line, which is how it gets drawn.

    The kind changes the outline and the tail, never the placement: a whisper is
    subject to exactly the same face-avoidance and reading-order rules as a shout.

    +-----------+--------------------------+------------------+
    | Kind      | Outline                  | Tail             |
    +===========+==========================+==================+
    | `speech`  | rounded rectangle        | tapered pointer  |
    +-----------+--------------------------+------------------+
    | `thought` | ellipse                  | trail of bubbles |
    +-----------+--------------------------+------------------+
    | `whisper` | dashed rounded rectangle | tapered pointer  |
    +-----------+--------------------------+------------------+
    | `shout`   | jagged burst             | tapered pointer  |
    +-----------+--------------------------+------------------+

    Example:
        >>> from scenet import BalloonKind, compile_source
        >>> core = compile_source(
        ...     "cast: {a: {reference: alice}}\n"
        ...     "script: [{say: {by: a, text: Psst., kind: whisper}}]"
        ... ).core
        >>> core.balloons[0].kind is BalloonKind.WHISPER
        True

    See Also:
        :class:`SayEvent <scenet.ir.SayEvent>`, whose `kind` takes one.
    """

    SPEECH = "speech"
    THOUGHT = "thought"
    WHISPER = "whisper"
    SHOUT = "shout"


class CaptionKind(StrEnum):
    """What a caption box is doing, which is how it gets set.

    These four are the letterers' own vocabulary, taken from Blambot's *Comic Book
    Grammar & Tradition* rather than invented -- for the same reason the predicates
    were taken from Visual Genome. Note that "narration", the obvious guess, is not
    among them.

    +-------------+---------------------------------------------+---------------------------+
    | Kind        | What it is                                  | How it is set             |
    +=============+=============================================+===========================+
    | `locale`    | Location and time -- "Midnight. The docks." | Italic                    |
    +-------------+---------------------------------------------+---------------------------+
    | `monologue` | A character's inner voice                   | Italic                    |
    +-------------+---------------------------------------------+---------------------------+
    | `spoken`    | Off-panel dialogue                          | Roman, in quotation marks |
    +-------------+---------------------------------------------+---------------------------+
    | `editorial` | The voice of the writer or editor           | Italic                    |
    +-------------+---------------------------------------------+---------------------------+

    `monologue` has largely replaced the thought balloon in modern comics, so a panel
    has two ways to render an inner voice: this and
    :attr:`BalloonKind.THOUGHT <scenet.ir.BalloonKind>`. Both are correct. They are
    different eras of the same convention, not a duplication.

    Example:
        >>> from scenet import CaptionKind
        >>> CaptionKind.LOCALE.is_italic, CaptionKind.SPOKEN.is_italic
        (True, False)

    See Also:
        :class:`CaptionEvent <scenet.ir.CaptionEvent>`, whose `kind` takes one.
        :class:`CaptionTone <scenet.ir.CaptionTone>`, the box a caption is lettered on.
    """

    LOCALE = "locale"
    MONOLOGUE = "monologue"
    SPOKEN = "spoken"
    EDITORIAL = "editorial"

    @property
    def is_italic(self) -> bool:
        """Whether this kind is set in italic. Everything except `spoken`."""
        return self is not CaptionKind.SPOKEN

    @property
    def is_quoted(self) -> bool:
        """Whether this kind takes quotation marks.

        `spoken` only, because it is the one kind where somebody is talking.
        """
        return self is CaptionKind.SPOKEN


class Face(StrEnum):
    """Which face of the lettering family a run of text is set in.

    Not something an author writes: a caption's kind decides between roman and italic,
    and a word written between underscores is set in bold italic. It is recorded in
    Panel Core, run by run, so the emitter draws each run in the face it was measured in.

    +---------------+-----------------------------------------------------------+
    | Face          | Used for                                                  |
    +===============+===========================================================+
    | `regular`     | Dialogue, and `spoken` captions                           |
    +---------------+-----------------------------------------------------------+
    | `italic`      | Every other caption kind                                  |
    +---------------+-----------------------------------------------------------+
    | `bold_italic` | Emphasis, in either -- Blambot's rule for a stressed word |
    +---------------+-----------------------------------------------------------+
    | `display`     | Sound effects: letters that are part of the picture       |
    +---------------+-----------------------------------------------------------+

    Each is a real font file of the same family. A synthetic slant or a stroked-out bold
    would measure as the roman face and draw as neither, which is the disagreement between
    measurement and rendering that lettering as outlines exists to prevent.
    """

    REGULAR = "regular"
    ITALIC = "italic"
    BOLD_ITALIC = "bold_italic"
    DISPLAY = "display"


class CaptionTone(StrEnum):
    """The value a caption box is filled with.

    A caption box is opaque, so its lettering is never at risk: the text sits on the
    fill whatever is behind it. What a tone changes is whether the *box* reads. On a
    clear day the atmosphere is `#eeeeee` and a white box on it is 1.16:1 -- legible,
    and invisible. The failing case is the pale end, not the dark one.

    +---------+-----------+-----------------------------------------------+-------------+
    | Tone    | Fill      | Where it comes from                           | Lettered in |
    +=========+===========+===============================================+=============+
    | `paper` | `#ffffff` | the paper the panel is printed on             | ink         |
    +---------+-----------+-----------------------------------------------+-------------+
    | `pale`  | `#adadad` | the `day` row of the value ladder, far plane  | ink         |
    +---------+-----------+-----------------------------------------------+-------------+
    | `ink`   | `#090909` | the `day` row of the value ladder, foreground | paper       |
    +---------+-----------+-----------------------------------------------+-------------+
    | `warm`  | `#eeeeee` | the `day` row of the value ladder, atmosphere | ink         |
    +---------+-----------+-----------------------------------------------+-------------+

    **Drawn from the ladder in `solve/backdrop.py`, not from a second palette.** Three of
    the four are rungs of it, taken by index rather than restated, which is what keeps
    lettering and backdrop from drifting apart as either is tuned. The `day` row is the
    ladder at its widest, so tones taken from it span the most ground.

    **A tone is fixed, not a function of the panel's hour.** A caption's value is a
    property of the caption; letting it drift with `time` would make the contrast table
    a function of the panel and the legibility floor unenforceable.

    `ink` produces what letterers call reversed type: the lettering inverts to paper,
    because black type on a near-black box is not lettering, it is a filled rectangle.
    Which mark reads is resolved by the solver -- see
    :attr:`CoreCaption.ink <scenet.core.CoreCaption>` -- exactly as falling rain's is.

    `warm` is the classic yellow `locale` caption, under the colour policy: its
    value is the grey above, and in a palette with colour it is drawn in that grey's twin,
    a pale yellow of the same lightness. In `mono` it is the grey, which is what a
    black-and-white reprint does to a yellow caption. The other three are neutral in every
    palette.

    There is no free-form colour here. A `fill:` taking any string would be the language's
    one open vocabulary, and would let an author produce an unreadable box.

    Example:
        >>> from scenet import CaptionEvent, CaptionTone
        >>> CaptionEvent(text="Later.", tone="ink").tone is CaptionTone.INK
        True

    See Also:
        :class:`CaptionEvent <scenet.ir.CaptionEvent>`, whose `tone` takes one.
        :class:`Palette <scenet.ir.Palette>`, which decides what `warm` is printed in.
    """

    PAPER = "paper"
    PALE = "pale"
    INK = "ink"
    WARM = "warm"


class MassKind(StrEnum):
    """What a tonal mass in the backdrop is made of.

    Subsetted from the **supercategories** of
    `COCO-Stuff <https://arxiv.org/pdf/1612.03716>`__, the canonical taxonomy of *stuff* --
    "amorphous background regions" as opposed to *things* with a well-defined shape.
    Its own argument is that stuff classes explain scene type and the geometric
    properties of a scene, which is exactly the job here. Taken from an existing
    vocabulary for the same reason the predicates were taken from Visual Genome.

    **Deliberately not the leaf names.** COCO-Stuff's actual classes are
    `building-other`, `sky-other`, `wall-brick`, `water-other` and so on, where the
    `-other` suffix marks the catch-all inside a supercategory. `building-other` is not
    a word anyone should have to type.

    Seven are outdoor -- `building`, `ground`, `plant`, `sky`, `solid`, `structural`,
    `water` -- and five indoor: `ceiling`, `floor`, `furniture`, `wall`, `window`.
    COCO-Stuff's own indoor/outdoor split is where that distinction comes from, so it
    did not have to be invented either. Its `textile`, `food` and `rawmaterial`
    supercategories are left out: drapery and objects, not scene-defining masses.

    A kind decides the **shape** a mass takes, never its value. Value comes from the
    plane, which is what keeps the notan reading honest -- see
    :class:`Plane <scenet.ir.Plane>`.

    Example:
        >>> from scenet import Mass, MassKind
        >>> Mass(kind="wall").kind is MassKind.WALL
        True

    See Also:
        :class:`Mass <scenet.ir.Mass>`, whose `kind` takes one.
    """

    BUILDING = "building"
    CEILING = "ceiling"
    FLOOR = "floor"
    FURNITURE = "furniture"
    GROUND = "ground"
    PLANT = "plant"
    SKY = "sky"
    SOLID = "solid"
    STRUCTURAL = "structural"
    WALL = "wall"
    WATER = "water"
    WINDOW = "window"


class Plane(StrEnum):
    """How far back a mass sits, which decides both its draw order and its value.

    Four planes, ordered from the back of the panel forward. They map onto the existing
    integer :attr:`CoreActor.depth <scenet.core.CoreActor.depth>` painter's order rather
    than introducing a second ordering mechanism: the three backdrop planes take
    negative depths, and `foreground` takes one above the frontmost actor, so a
    foreground mass draws over the cast the way a silhouetted doorway does.

    Value follows from the plane and from nothing else, which is what makes the
    `aerial perspective <https://en.wikipedia.org/wiki/Aerial_perspective>`__ rule
    parametric: with distance, contrast drops toward the atmosphere. Reading front to
    back, a mass never gets darker. See
    :func:`tone_for <scenet.solve.backdrop.tone_for>`.

    Example:
        >>> from scenet import Mass, Plane
        >>> Mass(kind="building", plane="far").plane is Plane.FAR
        True

    See Also:
        :class:`Mass <scenet.ir.Mass>`, whose `plane` takes one.
    """

    FOREGROUND = "foreground"
    NEAR = "near"
    MID = "mid"
    FAR = "far"


class Spans(StrEnum):
    """How much of the panel's width a mass covers.

    Resolved to an extent in the frontend, and that is **not cosmetic**. Any construct that
    would reintroduce a left/right disjunction has to resolve it before the solver, because
    Cassowary cannot express "A left of B *or* B left of A".
    A span is an absolute extent rather than a relation, which is what stops masses
    becoming an unordered `beside`.

    Example:
        >>> from scenet import Mass, Spans
        >>> Mass(kind="building", spans="left").spans is Spans.LEFT
        True

    See Also:
        :class:`Mass <scenet.ir.Mass>`, whose `spans` takes one.
    """

    FULL = "full"
    LEFT = "left"
    CENTRE = "center"
    RIGHT = "right"

    @property
    def fractions(self) -> tuple[float, float]:
        """The extent as `(start, end)` fractions of panel width.

        `left` and `right` overlap slightly in the middle. Butting them exactly would
        leave a seam down the centre of the panel wherever both are used at the same
        plane, which reads as a mistake rather than as two masses.

        Example:
            >>> from scenet import Spans
            >>> Spans.FULL.fractions
            (0.0, 1.0)
        """
        return {
            Spans.FULL: (0.0, 1.0),
            Spans.LEFT: (0.0, 0.56),
            Spans.CENTRE: (0.26, 0.74),
            Spans.RIGHT: (0.44, 1.0),
        }[self]


class Horizon(StrEnum):
    """Where the ground meets whatever is behind it.

    One line for the whole panel, which every mass is composed against: masses of the
    ground sort start at it and run down, masses that stand in the world rise from it.
    Named rather than given as a number for the same reason `at:` is -- the author is
    saying how the panel is composed, not typing a coordinate.

    Example:
        >>> from scenet import Horizon, SettingSpec
        >>> SettingSpec(horizon="low").horizon is Horizon.LOW
        True

    See Also:
        :class:`SettingSpec <scenet.ir.SettingSpec>`, whose `horizon` takes one.
        :class:`Mass <scenet.ir.Mass>`, which is composed against it.
    """

    HIGH = "high"
    MID = "mid"
    LOW = "low"

    @property
    def fraction(self) -> float:
        """Where the line sits, as a fraction of panel height.

        A **high** horizon sits nearer the top of the frame, so more ground is in view
        and the camera reads as looking down over it.

        Example:
            >>> from scenet import Horizon
            >>> Horizon.HIGH.fraction < Horizon.LOW.fraction
            True
        """
        return {Horizon.HIGH: 0.38, Horizon.MID: 0.55, Horizon.LOW: 0.72}[self]


class TimeOfDay(StrEnum):
    """When the panel happens, which shifts the whole value ladder.

    Each time supplies two numbers -- the value of the foreground and the value of the
    atmosphere -- and the planes are spaced evenly between them. So `night` is not a
    blue filter over a daytime panel: it is a darker, more compressed ladder, which is
    what night actually does to a drawn scene. The ladder stays monotonic in depth at
    every time of day, by construction rather than by tuning.

    Example:
        >>> from scenet import SettingSpec, TimeOfDay
        >>> SettingSpec(time="night").time is TimeOfDay.NIGHT
        True

    See Also:
        :class:`SettingSpec <scenet.ir.SettingSpec>`, whose `time` takes one.
    """

    DAWN = "dawn"
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"


class Weather(StrEnum):
    """What the air is doing between the reader and the panel.

    `clouds` and `fog` are first-class *stuff* in COCO-Stuff, so this vocabulary did not
    have to be invented either. `fog` renders as a turbulence veil over the backdrop;
    `rain` and `snow` add that veil as cloud and put falling marks over everything,
    because weather is between the reader and the figures rather than behind them.

    Example:
        >>> from scenet import SettingSpec, Weather
        >>> SettingSpec(weather="rain").weather is Weather.RAIN
        True

    See Also:
        :class:`SettingSpec <scenet.ir.SettingSpec>`, whose `weather` takes one.
    """

    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    SNOW = "snow"


class Fit(StrEnum):
    """How a supplied picture fills the panel, keeping its own proportions.

    +-----------+--------------------------------------------------------------------+------------+
    | Fit       | The picture                                                        | SVG's word |
    +===========+====================================================================+============+
    | `cover`   | Fills the panel; what overhangs it is cropped, equally on both     | `slice`    |
    |           | sides                                                              |            |
    +-----------+--------------------------------------------------------------------+------------+
    | `contain` | Is shown whole; the panel shows round it where their shapes differ | `meet`     |
    +-----------+--------------------------------------------------------------------+------------+

    Centred either way. A picture is never stretched: its shape is a fact about it, and
    a figure drawn into it would be stretched with it.

    Example:
        >>> from scenet import Fit, SettingSpec
        >>> SettingSpec(image="art/street.png", fit="contain").fit is Fit.CONTAIN
        True

    See Also:
        :class:`SettingSpec <scenet.ir.SettingSpec>`, whose `fit` takes one.
    """

    COVER = "cover"
    CONTAIN = "contain"


class PanelSpec(Strict):
    """The panel's own dimensions.

    Example:
        >>> from scenet import PanelSpec
        >>> PanelSpec(size=(1200.0, 600.0)).width
        1200.0

    See Also:
        :class:`PanelIR <scenet.ir.PanelIR>`, whose `panel` it is.
    """

    size: tuple[float, float] = (1000.0, 1000.0)
    """The panel's width and height, `[width, height]`, in panel units: everything else is
    measured against them. Printed, a unit is a tenth of a millimetre.
    """
    margin: float = Field(default=0.0, ge=0.0)
    """An inset on all four sides, in panel units. Balloons, captions and sound effects keep
    inside it; figures may run past it, as comics let them.
    """

    @property
    def width(self) -> float:
        """Panel width in panel units."""
        return self.size[0]

    @property
    def height(self) -> float:
        """Panel height in panel units."""
        return self.size[1]

    @model_validator(mode="after")
    def check_positive(self) -> Self:
        """Reject a panel with no usable area.

        Returns:
            The validated spec.

        Raises:
            ValueError: A dimension is zero or negative, or the margins meet in the
                middle leaving nothing to compose in.
        """
        _check_positive_panel_spec(self)
        return self


def _check_positive_panel_spec(spec: PanelSpec) -> None:
    """`PanelSpec.check_positive`, outside the class so that mutmut mutates it."""
    if spec.width <= 0 or spec.height <= 0:
        raise RuleViolationError("panel size must be positive", rule="panel-geometry")
    if spec.margin * 2 >= min(spec.width, spec.height):
        raise RuleViolationError("margin leaves no usable panel area", rule="panel-geometry")


class CameraSpec(Strict):
    """How the panel is framed.

    There is exactly **one camera per panel**, and every actor is drawn at the scale it
    implies. Scaling each actor to its own crop landmark instead would make everybody
    the same apparent height and erase the body differences a comic uses to tell
    characters apart.

    Example:
        >>> from scenet import CameraSpec, ShotType
        >>> CameraSpec(shot="close_up").shot is ShotType.CLOSE_UP
        True

    See Also:
        :class:`ShotType <scenet.ir.ShotType>` and :class:`CameraAngle <scenet.ir.CameraAngle>`,
        what it takes.
    """

    shot: ShotType = ShotType.MEDIUM_SHOT
    """How tightly the camera frames the cast, named by where the frame cuts the body, from
    `long_shot` to `extreme_close_up`. The tightest it may go: the camera steps back when the
    cast does not fit.
    """
    angle: CameraAngle = CameraAngle.EYE_LEVEL
    """The camera's height: `low` looks up, leaving little air above the head; `high` looks
    down, leaving more.
    """


class Mass(Strict):
    """One tonal mass in the backdrop: what it is, how far back, how wide.

    **Backdrops are never author-drawn**, and there are two reasons. The structural one:
    crisp architecture needs a vanishing point, and this is deliberately a flat,
    orthographic compiler, so drawn buildings would fight the compiler's own model.
    Soft tonal masses have no perspective to get wrong.

    The second is that this is how comics actually establish place. Notan -- the
    Japanese light/dark mass principle, which reached Western art teaching through
    Arthur Wesley Dow's *Composition* (1899) -- says place is read from the arrangement
    of masses rather than from rendered detail.

    Example:
        >>> from scenet import Mass, MassKind
        >>> Mass(kind=MassKind.SKY).plane.value
        'mid'

    See Also:
        :class:`SettingSpec <scenet.ir.SettingSpec>`, whose `masses` holds them.
        :class:`MassKind <scenet.ir.MassKind>`, every kind there is.
    """

    kind: MassKind
    """What the mass is made of, which decides its silhouette: seven outdoor kinds of stuff and
    five indoor.
    """
    plane: Plane = Plane.MID
    """How far back the mass sits, which decides its value and its draw order. A `foreground`
    mass is drawn over the cast.
    """
    spans: Spans = Spans.FULL
    """How much of the panel's width the mass covers: all of it, or its `left`, `center` or
    `right` part.
    """


class FontSpec(Strict):
    """The font files a panel is lettered in, each a path relative to the document.

    Paths, never names: a font is a declared file and never a system lookup, so a
    document letters the same on every machine. They are read relative to the folder the
    document is in, and an absolute one is refused; see :mod:`scenet.paths`.

    Example:
        >>> from scenet import FontSpec, parse_panel
        >>> font = parse_panel("lettering: {font: fonts/Comic.ttf}").lettering.font
        >>> isinstance(font, FontSpec), font.regular
        (True, 'fonts/Comic.ttf')

    See Also:
        :class:`LetteringSpec <scenet.ir.LetteringSpec>`, whose `font` takes one.
        :class:`FontMetrics <scenet.solve.text.FontMetrics>`, a font read for measuring.
    """

    regular: str
    """The font file dialogue and `spoken` captions are lettered in, relative to the document.
    Written alone, as `font: fonts/Comic.ttf`, it letters every face.
    """
    italic: str | None = None
    """The font file every caption but a `spoken` one is lettered in. Left out, they are set in
    `regular`.
    """
    bold_italic: str | None = None
    """The font file a stressed word, `_word_`, is lettered in. Left out, it is `italic`, or
    `regular` when there is no italic, and a note says so.
    """
    display: str | None = None
    """The font file sound effects are lettered in. Left out, the shipped display face, Bangers,
    whatever the other faces are.
    """


class LetteringSpec(Strict):
    """How a panel is lettered.

    A size or a font set beside `panels:` is a default every panel inherits, which is how a page
    letters at one size of the author's choosing. Set on one panel, it letters that panel
    alone -- the author's call to make, and not one the compiler second-guesses.

    The type is measured at exactly this size, so it decides how big every balloon is. A
    size too large for the panel leaves a balloon nowhere to go, which `scenet check
    --deep` reports as `balloon-placement`.

    Example:
        >>> from scenet import LetteringSpec, parse_panel
        >>> lettering = parse_panel("lettering: {size: 30}").lettering
        >>> isinstance(lettering, LetteringSpec), lettering.size
        (True, 30.0)

    See Also:
        :class:`FontSpec <scenet.ir.FontSpec>`, the files it letters in.
    """

    size: float | None = Field(default=None, gt=0.0)
    """The dialogue type size, in panel units; captions keep 30 parts in 35 of it. Left out,
    3.5% of the height the panel letters against: its own, or one tier of a three-tier page.
    """
    font: FontSpec | None = None
    """The font files to letter in, relative to the document: one file for every face, or one
    for each. Left out, Source Sans Pro.
    """


class SettingSpec(Strict):
    """Where and when the panel happens: tonal masses, or a picture drawn elsewhere.

    **There is no `place` field here, deliberately.** `place: docks` is surface syntax
    that the frontend expands into exactly the mass list an author could have written
    themselves -- the same treatment `alice left_of bob` gets, which reaches the IR as a
    :class:`Relation <scenet.ir.Relation>` and never as text. That is what keeps a
    preset a library for convenience rather than a second, opaque format: by the time
    anything downstream sees a backdrop, there is one representation of it.

    A panel with no masses and clear weather has no backdrop at all, which is what every
    panel written before this block existed still gets.

    Example:
        >>> from scenet import SettingSpec, parse_panel
        >>> panel = parse_panel("setting: {place: docks, time: night}")
        >>> isinstance(panel.setting, SettingSpec)
        True
        >>> panel.setting.time.value, len(panel.setting.masses) > 0
        ('night', True)

    See Also:
        :class:`Mass <scenet.ir.Mass>`, one shape in it.
        :class:`Place <scenet.places.Place>`, a setting by name.
    """

    horizon: Horizon = Horizon.MID
    """Where the ground meets what is behind it, which every mass is composed against: `high`
    shows more ground, `low` less.
    """
    masses: tuple[Mass, ...] = ()
    """The backdrop as tonal masses, back to front: what a `place` expands into, written out.
    Write this, `place` or `image`, never two of them.
    """
    time: TimeOfDay = TimeOfDay.DAY
    """When the panel happens, which sets the two ends of the value ladder: the foreground's
    value and the atmosphere's.
    """
    weather: Weather = Weather.CLEAR
    """What the air is doing: `fog` veils the backdrop; `rain` and `snow` veil it as cloud, and
    fall over everything, the cast included.
    """
    image: SvgText | None = None
    """A picture drawn elsewhere, behind the cast: a PNG or JPEG file, relative to the document.
    Only its size is read. Written instead of `place` and `masses`.
    """
    fit: Fit | None = None
    """How the picture fills the panel: `cover` fills it and crops what overhangs, equally on
    both sides; `contain` shows the whole picture. Left out, `cover`.
    """

    @model_validator(mode="after")
    def check_backdrop(self) -> Self:
        """Refuse a picture beside masses, and a fit with no picture to fit.

        The frontend says so first, at the line that was written; this holds the same
        rule for a setting built in Python. A horizon beside a picture is the frontend's
        alone to refuse: here its default and a written one look the same.

        Returns:
            The validated setting.

        Raises:
            RuleViolationError: `conflicting-setting` for masses and a picture, and
                `invalid-field` for a fit with nothing to fit.
        """
        _check_backdrop(self)
        return self

    @property
    def is_bare(self) -> bool:
        """Whether there is nothing to draw: no masses, no picture, nothing in the air."""
        return not self.masses and self.image is None and self.weather is Weather.CLEAR


def _check_backdrop(setting: SettingSpec) -> None:
    """`SettingSpec.check_backdrop`, outside the class so that mutmut mutates it."""
    if setting.image is not None and setting.masses:
        raise RuleViolationError(
            "'setting' lists masses and names an image; the picture is the whole "
            "backdrop, so write one or the other",
            rule="conflicting-setting",
            loc=("setting", "masses"),
        )
    if setting.fit is not None and setting.image is None:
        raise RuleViolationError(
            "'setting' has a fit and no image; `fit` says how a picture fills the "
            "panel, so it goes beside `image`",
            rule="invalid-field",
            loc=("setting", "fit"),
        )


class CastMember(Strict):
    """One character present in the panel: a puppet Scenet poses, or a figure a picture draws.

    The split between actor id and `reference` is what lets one puppet appear twice in
    a panel as two different people:

    .. code-block:: yaml

        cast:
          guard_left:  {reference: bob, pose: arms_crossed}
          guard_right: {reference: bob, pose: standing_neutral, facing: left}

    Example:
        >>> from scenet import CastMember, Facing
        >>> member = CastMember(reference="alice", at="left_third", facing="left")
        >>> member.facing is Facing.LEFT
        True

    See Also:
        :class:`PanelIR <scenet.ir.PanelIR>`, whose `cast` holds them.
        :class:`AnchorX <scenet.ir.AnchorX>` and :class:`Facing <scenet.ir.Facing>`, what it takes.
    """

    reference: str | None = None
    """The puppet to draw: a shipped puppet's name, or the path of a `.puppet.yaml` file,
    relative to the document. Written instead of `figure`.
    """
    pose: str = "standing_neutral"
    """A pose the puppet declares, by name."""
    expression: str = "neutral"
    """An expression the puppet declares, by name."""
    marks: tuple[Mark, ...] = ()
    """Emanata drawn around the character -- `plewds`, `squeans`, `grawlixes`, `briffits` -- in
    any order, each once. They compose with the expression.
    """
    at: AnchorX = AnchorX.CENTRE
    """Where along the panel's width the figure would like to stand. A preference: non-overlap
    and `left_of` override it.
    """
    facing: Facing = Facing.RIGHT
    """Which way the figure is turned, `left` or `right`, gaze and all."""
    figure: SvgText | None = None
    """A figure the panel's picture draws, by the name its artwork contract gives it. Written
    instead of `reference`, and with none of the keys that pose or place a puppet.
    """

    @model_validator(mode="wrap")
    @classmethod
    def names_a_puppet_or_a_figure(
        cls, data: object, handler: ModelWrapValidatorHandler["CastMember"]
    ) -> "CastMember":
        """Require one of `reference` and `figure`, reported as `reference` missing.

        Both are optional to the model, so pydantic alone would accept a member that
        names neither. Saying so as `reference` being missing -- pydantic's own error, at
        the place it always was -- keeps every finding a puppet's member gave before
        figures existed exactly as it was, and lets a misspelt `referecne` still be
        folded into "did you mean 'reference'?".
        """
        return _names_a_puppet_or_a_figure(cls.__name__, data, handler)

    @property
    def is_figure(self) -> bool:
        """Whether this member is a figure a picture draws, rather than a puppet."""
        return self.figure is not None

    @field_validator("marks")
    @classmethod
    def check_marks(cls, marks: tuple[Mark, ...]) -> tuple[Mark, ...]:
        """Reject a mark listed twice, and put the rest in a fixed order.

        Returns:
            The marks, sorted.

        Raises:
            ValueError: A mark appears more than once. Harmless to draw, but almost
                certainly a slip, and this language reports slips.
        """
        return _check_marks(marks)


def _names_a_puppet_or_a_figure(
    title: str, data: object, handler: ModelWrapValidatorHandler["CastMember"]
) -> "CastMember":
    """`CastMember.names_a_puppet_or_a_figure`, outside the class so that mutmut mutates it."""
    if not isinstance(data, dict) or any(
        data.get(key) is not None for key in ("reference", "figure")
    ):
        return handler(data)
    missing: InitErrorDetails = {"type": "missing", "loc": ("reference",), "input": data}
    try:
        handler(data)
    except ValidationError as exc:
        raise ValidationError.from_exception_data(title, [missing, *_init_details(exc)]) from None
    raise ValidationError.from_exception_data(title, [missing])


def _check_marks(marks: tuple[Mark, ...]) -> tuple[Mark, ...]:
    """`CastMember.check_marks`, outside the class so that mutmut mutates it."""
    repeated = sorted({mark.value for mark in marks if marks.count(mark) > 1})
    if repeated:
        raise ValueError(f"mark listed more than once: {', '.join(repeated)}")
    return tuple(sorted(marks))


def _init_details(error: ValidationError) -> list[InitErrorDetails]:
    """A validation error's details, in the form a new one is built from."""
    details: list[InitErrorDetails] = []
    for item in error.errors():
        detail: InitErrorDetails = {
            "type": item["type"],
            "loc": item["loc"],
            "input": item["input"],
        }
        if "ctx" in item:
            detail["ctx"] = item["ctx"]
        details.append(detail)
    return details


#: What a puppet's member may say that a figure's may not: posing and placing it.
PUPPET_KEYS: tuple[str, ...] = ("pose", "expression", "marks", "at", "facing")


class Relation(Strict):
    """One staging fact, written as a sentence.

    Authored as `alice left_of bob` rather than a three-key mapping because staging is
    read far more often than it is written, and a sentence is legible at a glance.

    Raises:
        ~pydantic_core.ValidationError: The subject and object are the same actor. No
            predicate here is meaningful reflexively.

    Example:
        >>> from scenet import Predicate, Relation
        >>> relation = Relation(subject="a", predicate="left_of", object="b")
        >>> relation.predicate is Predicate.LEFT_OF
        True

    See Also:
        :class:`Predicate <scenet.ir.Predicate>`, every relation there is.
    """

    subject: str
    """The actor id the relation is about."""
    predicate: Predicate
    """How the subject stands to the object: `left_of`, `right_of`, `in_front_of`, `behind`,
    `looking_at` or `ground_shared_with`.
    """
    object: str
    """The other actor id. For `looking_at`, it may be somebody heard from off panel."""

    @model_validator(mode="after")
    def check_not_reflexive(self) -> Self:
        """Reject a relation between an actor and itself.

        Returns:
            The validated relation.

        Raises:
            ValueError: Subject and object are the same actor id. No predicate in the
                language means anything reflexively, so this is always a typo.
        """
        _check_not_reflexive(self)
        return self


def _check_not_reflexive(relation: Relation) -> None:
    """`Relation.check_not_reflexive`, outside the class so that mutmut mutates it."""
    if relation.subject == relation.object:
        raise RuleViolationError(
            f"relation '{relation.predicate}' cannot relate '{relation.subject}' to itself",
            rule="reflexive-relation",
        )


class SayEvent(Strict):
    """One line of dialogue.

    Script order **is** reading order, and reading order is a hard constraint. Reorder
    these and you reorder the panel.

    Example:
        >>> from scenet import BalloonKind, SayEvent
        >>> line = SayEvent(by="alice", text="Psst.", kind="whisper")
        >>> line.kind is BalloonKind.WHISPER
        True

    See Also:
        :class:`CaptionEvent <scenet.ir.CaptionEvent>`, words no character says.
        :class:`SfxEvent <scenet.ir.SfxEvent>`, a sound.
    """

    verb: Literal["say"] = "say"
    """Always `say`: the key the entry is written under in a script."""
    by: SvgText
    """Who speaks: an actor id in the cast, whose mouth the tail points at. With `off_panel`,
    the name of somebody nobody draws.
    """
    text: LetteredText = Field(min_length=1)
    """The line, as one string; the compiler breaks it into lines. A word between underscores,
    `_word_`, is stressed, and lettered in bold italic.
    """
    prefer: PlacementZone | None = None
    """Where the balloon would like to sit, one of nine zones of the panel. The weakest
    placement term: face avoidance and reading order override it.
    """
    kind: BalloonKind = BalloonKind.SPEECH
    """The balloon the line is carried in: `speech`, `thought`, `whisper` or `shout`."""
    off_panel: bool | Side = False
    """The speaker is outside the panel: `true`, or the side of the frame they are on. The tail
    ends on the frame there.
    """
    size: TypeSize = TypeSize.NORMAL
    """`small` for a line muttered, said under the breath or weakly: smaller type, in a balloon
    that keeps its room.
    """

    @field_validator("off_panel", mode="before")
    @classmethod
    def check_off_panel(cls, value: object) -> object:
        """`true`, `false` or a side, and one finding for anything else.

        Validated as a plain union, a wrong value failed both members and was reported
        twice, once as not a boolean and once as not a side, when it is one mistake.
        """
        return _check_off_panel(value)


def _check_off_panel(value: object) -> object:
    """`SayEvent.check_off_panel`, outside the class so that mutmut mutates it."""
    if isinstance(value, bool) or value in {side.value for side in Side}:
        return value
    sides = ", ".join(f"'{side.value}'" for side in Side)
    raise ValueError(
        f"off_panel is true, false, or the side of the frame the speaker is on: {sides}; "
        f"not {value!r}"
    )


class CaptionEvent(Strict):
    """One caption box: the panel speaking in its own voice.

    A caption is what lets a panel say where and when it happens without a character
    having to explain it out loud. `MIDNIGHT. THE DOCKS.` in the corner does the work
    of an establishing shot with no artwork at all, which is how comics established
    place long before they had reliable backgrounds.

    **A caption is not a fifth balloon kind.** It has no speaker to point at and no
    tail, and :attr:`CoreBalloon.tail <scenet.core.CoreBalloon.tail>` is required -- a
    fifth kind would mean inventing a speaker and leaving a field dead.

    `by` is the one place where the rule that every actor id resolves does not hold,
    and deliberately: an off-panel speaker is not in the panel, so requiring them to be
    in the cast would defeat the point of saying they are off panel.

    Example:
        >>> from scenet import CaptionEvent
        >>> CaptionEvent(text="Midnight. The docks.").kind.value
        'locale'

    See Also:
        :class:`SayEvent <scenet.ir.SayEvent>`, words a character says.
        :class:`CaptionKind <scenet.ir.CaptionKind>` and :class:`CaptionTone
        <scenet.ir.CaptionTone>`, what it takes.
    """

    verb: Literal["caption"] = "caption"
    """Always `caption`: the key the entry is written under in a script."""
    text: LetteredText = Field(min_length=1)
    """What the box says, as one string; line breaks are computed. A word between underscores,
    `_word_`, is stressed.
    """
    kind: CaptionKind = CaptionKind.LOCALE
    """What the box is doing: `locale` for a place and time, `monologue` for an inner voice,
    `spoken` for speech from off panel, `editorial` for the writer's voice.
    """
    tone: CaptionTone = CaptionTone.PAPER
    """What the box is filled with: `paper`, `pale`, `ink`, which is lettered in paper, or
    `warm`, yellow under `palette: tinted`.
    """
    prefer: PlacementZone | None = None
    """Where the box would like to sit, one of nine zones of the panel. Left out, where reading
    starts: `top_left`, or `top_right` read right to left.
    """
    by: SvgText | None = None
    """Who is speaking, for a `spoken` caption only: any name, in the cast or not."""

    @field_validator("by")
    @classmethod
    def check_speaker_is_meaningful(cls, by: str | None, info: ValidationInfo) -> str | None:
        """Only an off-panel line has a speaker to name.

        A check on `by` rather than on the whole caption, so the finding points at the
        `by:` to delete. Fields are validated in the order they are declared, so `kind`
        has been by now; if it failed, there is no kind to hold `by` to, and the finding
        about `kind` is the one to report.

        Returns:
            The speaker, unchanged.

        Raises:
            ValueError: `by` was given for a kind that has no speaker. A locale box
                states a place; nobody says it, so naming who did is a mistake worth
                reporting rather than a field to ignore.
        """
        return _check_speaker_is_meaningful(by, info)


def _check_speaker_is_meaningful(by: str | None, info: ValidationInfo) -> str | None:
    """`CaptionEvent.check_speaker_is_meaningful`, outside the class so that mutmut mutates it."""
    kind = info.data.get("kind")
    if by is not None and isinstance(kind, CaptionKind) and not kind.is_quoted:
        raise RuleViolationError(
            f"only a 'spoken' caption may name a speaker, but this one is '{kind.value}'",
            rule="caption-speaker",
        )
    return by


class SfxSize(StrEnum):
    """How big a sound effect is lettered, as a multiple of the dialogue type size.

    +----------+-------------------------+
    | Size     | Times the dialogue size |
    +==========+=========================+
    | `small`  | 1.6                     |
    +----------+-------------------------+
    | `medium` | 2.6                     |
    +----------+-------------------------+
    | `large`  | 4                       |
    +----------+-------------------------+

    A multiple of the type size rather than of the figure, so an effect reads at
    `long_shot` as well as at `close_up`: a sound does not get quieter because the
    camera stepped back. Three steps, not a number, for the reason every other size in
    the language is named -- the author says how loud, the compiler says how big.

    Example:
        >>> from scenet import SfxEvent, SfxSize
        >>> SfxEvent(text="BAM", size="large").size is SfxSize.LARGE
        True

    See Also:
        :class:`SfxEvent <scenet.ir.SfxEvent>`, whose `size` takes one.
    """

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class SfxEvent(Strict):
    """A sound effect: letters that are part of the picture.

    `BLAM` is not dialogue. Comics letter sound as art -- big, angled, outlined, near
    where the sound is -- in a display face, not in the balloon face, and with no balloon.

    **Placed by candidates and cost, never at a coordinate.** It never covers a face,
    and balloons pay to cover it, as they pay to cover emanata. It takes its number in
    the script's one reading order, which is what a reader of the text follows, but it
    is exempt from the geometric reading-order rule: a sound sits where the sound is.

    Example:
        >>> from scenet import SfxEvent
        >>> SfxEvent.model_validate({"text": "BLAM", "from": "bob"}).source
        'bob'

    See Also:
        :class:`SfxSize <scenet.ir.SfxSize>`, how large it is.
    """

    model_config = ConfigDict(populate_by_name=True)

    verb: Literal["sfx"] = "sfx"
    """Always `sfx`: the key the entry is written under in a script."""
    text: SvgText = Field(min_length=1)
    """The sound, lettered exactly as written, in the display face."""
    source: str | None = Field(default=None, alias="from")
    """Written `from`: the actor id the sound comes from, which it is placed near."""
    prefer: PlacementZone | None = None
    """Where the effect would like to sit, one of nine zones of the panel: on its own, or as a
    pull on an effect that has a `from`.
    """
    size: SfxSize = SfxSize.MEDIUM
    """How loud: `small`, `medium` or `large`, lettered at 1.6, 2.6 or 4 times the dialogue type
    size.
    """
    rotate: float = Field(default=0.0, ge=-45.0, le=45.0)
    """How far the effect is turned clockwise, in degrees, from -45 to 45."""
    arc: float = Field(default=0.0, ge=-120.0, le=120.0)
    """How far the line of letters bends, in degrees, from -120 to 120: positive bows its middle
    up, negative down.
    """
    hollow: bool = False
    """`true` letters the effect as an outline with no fill, so the art shows through: an open
    effect.
    """


#: The tag a union member is chosen by when its input carries none.
UNTAGGED = "untagged"


def tag_by(field: str) -> Discriminator:
    """Choose a union member by the tag in `field`, as the members' literals spell it.

    A plain union is validated against every member in turn, and when all of them fail
    pydantic reports why each one did: one bad caption `kind` became four findings, three
    of them about a `say` entry nobody wrote. The tag already says which member is meant,
    so only that member's errors are reported, at a path that names it.

    The tag is a defaulted literal rather than a required one, so input without it is
    still accepted: it is sent to :data:`UNTAGGED`, which each union using this maps to
    the plain union it replaced. The frontends always write the tag, so only a caller
    building the IR by hand ever takes that route.

    Args:
        field: The literal field that names the member -- `verb`, say.

    Returns:
        A discriminator to annotate the union with.
    """

    def tag_of(value: object) -> str:
        tag = value.get(field) if isinstance(value, dict) else getattr(value, field, None)
        return UNTAGGED if tag is None else str(tag)

    return Discriminator(tag_of)


#: One entry in a panel's script, chosen by its `verb`.
ScriptEvent = Annotated[
    Annotated[SayEvent, Tag("say")]
    | Annotated[CaptionEvent, Tag("caption")]
    | Annotated[SfxEvent, Tag("sfx")]
    | Annotated[SkipJsonSchema[SayEvent | CaptionEvent | SfxEvent], Tag(UNTAGGED)],
    tag_by("verb"),
]


class PanelIR(Strict):
    """A complete, validated panel: the language's real definition.

    Every frontend produces one of these and nothing else, which is what lets the YAML
    syntax and the comic-script syntax coexist without the solver knowing either exists.
    **Nothing here carries a coordinate** -- computing those is the solver's job, and
    keeping them out is what makes a panel reusable at any size.

    Validation is strict and total: unknown keys are rejected, every actor id mentioned
    in `staging` or `script` must exist in `cast`, and the ordering relations must not
    contain a cycle. A misspelled key that was silently ignored would produce a panel
    that is subtly wrong with no indication of why, which for a language meant to be
    precise is the worst possible failure.

    Example:
        >>> from scenet import PanelIR, parse_panel
        >>> panel = parse_panel("panel: {size: [800.0, 600.0]}")
        >>> isinstance(panel, PanelIR)
        True
        >>> panel.panel.width, panel.camera.shot.value
        (800.0, 'medium_shot')

    See Also:
        :func:`compile_ir <scenet.pipeline.compile_ir>`, to turn one of these into geometry.
    """

    panel: PanelSpec = PanelSpec()
    """The panel's frame: its size and margin, in panel units."""
    camera: CameraSpec = CameraSpec()
    """How the cast is framed: the shot, and the camera's height."""
    setting: SettingSpec = SettingSpec()
    """Where and when the panel happens: a named place, tonal masses or a picture behind the
    cast, with the time of day and the weather.
    """
    lettering: LetteringSpec = LetteringSpec()
    """How the lettering is set: the dialogue type size, and the font files."""
    cast: dict[SvgText, CastMember] = Field(default_factory=dict)
    """Who is in the panel: each actor id, chosen by the author, and the puppet that plays them
    or the figure a picture draws. Their order means nothing.
    """
    staging: tuple[Relation, ...] = ()
    """How the cast stand to each other, as sentences: `alice left_of bob`. One relation each."""
    script: tuple[ScriptEvent, ...] = ()
    """What is said and heard, in the order it is read: `say` for a balloon, `caption` for a
    box, `sfx` for a sound effect.
    """
    description: Description | None = Field(
        default=None,
        description=(
            "What the panel shows, in words, for a reader who cannot see it. Carried into "
            "the SVG as its accessible name and never interpreted. Not inherited: a panel "
            "drawn `over:` another is a different picture. Left out, one is generated from "
            "the shot, the setting and the cast."
        ),
    )
    direction: Direction = Field(
        default=Direction.LTR,
        description=(
            "Which way the comic is read: `ltr` from the top left, `rtl` from the top right, "
            "as manga are -- panels, pages and the balloons in a panel. Its progression, not "
            "its text: the words in a balloon still read left to right. Written once for the "
            "whole document; the scene is never mirrored."
        ),
    )
    palette: Palette = Field(
        default=Palette.MONO,
        description=(
            "What the panel is drawn in: `mono`, the value ladder in grey, or `tinted`, each "
            "value in a colour with the same lightness. Colour never changes a value, so a "
            "tinted panel is, in monochrome, the mono one. Inherited like any default; a "
            "panel may have its own."
        ),
    )

    @model_validator(mode="after")
    def check_references_resolve(self) -> Self:
        """Every actor id mentioned anywhere must exist in the cast.

        Caught here rather than in the solver so the error names the offending
        identifier while the source is still in view.
        """
        _check_references_resolve(self)
        return self

    @model_validator(mode="after")
    def check_ordering_is_consistent(self) -> Self:
        """Horizontal ordering must not contain a cycle.

        The layout engine is a *linear* constraint solver, so ordering has to be
        decided before it runs -- see docs/reference/language/staging.md. A cycle such as
        'a left_of b, b left_of a' has no solution, and detecting it here produces a
        comprehensible message instead of an opaque solver failure.
        """
        _check_ordering_is_consistent(self)
        return self

    @model_validator(mode="after")
    def check_figures(self) -> Self:
        """A figure a picture draws is not posed, placed or staged, and plays one part.

        The frontend refuses a puppet's key written beside `figure`, since a written
        default and an absent key look the same here; this is the backstop for an IR
        built in Python, and the place the rest is decided:

        - a cast is all puppets or all figures (`conflicting-cast`): staging and the
          camera place puppets, and would place them over painted faces they cannot see;
        - one figure plays one part (`conflicting-cast`);
        - no staging relation names a figure (`figure-staging`): the artist staged them.
        """
        _check_figures(self)
        return self

    def figures(self) -> dict[str, str]:
        """The cast members a supplied picture draws, and the figure each plays.

        Example:
            >>> from scenet import parse_panel
            >>> parse_panel("cast: {ana: {figure: ana_in_red}}").figures()
            {'ana': 'ana_in_red'}
        """
        return {
            actor: member.figure for actor, member in self.cast.items() if member.figure is not None
        }

    def puppets(self) -> dict[str, str]:
        """The cast members Scenet poses, and the puppet each is drawn by."""
        return {
            actor: member.reference
            for actor, member in self.cast.items()
            if member.reference is not None
        }

    @property
    def drawn_by_its_picture(self) -> bool:
        """Whether everybody in the cast is a figure the panel's picture draws.

        Then nothing is staged, the camera does not run, and the shot is whatever the
        artist drew.
        """
        return bool(self.cast) and all(member.is_figure for member in self.cast.values())

    def ordering_constraints(self) -> tuple[tuple[str, str], ...]:
        """Normalised (left, right) pairs from both left_of and right_of relations."""
        pairs: list[tuple[str, str]] = []
        for relation in self.staging:
            if relation.predicate is Predicate.LEFT_OF:
                pairs.append((relation.subject, relation.object))
            elif relation.predicate is Predicate.RIGHT_OF:
                pairs.append((relation.object, relation.subject))
        return tuple(pairs)

    def gaze_targets(self) -> dict[str, str]:
        """Who is looking at whom.

        Returns:
            A mapping from each looking actor to the actor they are looking at. An
            actor may look at only one target, so a later `looking_at` relation for the
            same subject replaces an earlier one.

        Example:
            >>> from scenet import parse_panel
            >>> panel = parse_panel(
            ...     "{cast: {a: {reference: alice}, b: {reference: bob}},"
            ...     " staging: [a looking_at b]}"
            ... )
            >>> panel.gaze_targets()
            {'a': 'b'}
        """
        return {
            relation.subject: relation.object
            for relation in self.staging
            if relation.predicate is Predicate.LOOKING_AT
        }

    def off_panel_speakers(self) -> dict[str, Side | None]:
        """Who is heard from off panel, and the side each is heard from, if any line names one.

        Returns:
            Speaker to the first side a line of theirs names, or None when every line of
            theirs says only `off_panel: true`, in the order they first speak.

        Example:
            >>> from scenet import parse_panel
            >>> panel = parse_panel(
            ...     "{script: [{say: {by: carol, text: Hi, off_panel: true}},"
            ...     " {say: {by: carol, text: Here, off_panel: left}}]}"
            ... )
            >>> panel.off_panel_speakers()
            {'carol': <Side.LEFT: 'left'>}
        """
        heard: dict[str, Side | None] = {}
        for event in self.script:
            if isinstance(event, SayEvent) and event.off_panel is not False:
                named = event.off_panel if isinstance(event.off_panel, Side) else None
                if heard.get(event.by) is None:
                    heard[event.by] = named
        return heard

    def ground_groups(self) -> tuple[frozenset[str], ...]:
        """Actors joined by ground_shared_with, as connected components.

        Union-find rather than pairwise handling, so that 'a with b' plus 'b with c'
        puts all three on one ground line without the author saying 'a with c'.
        """
        parent = {actor: actor for actor in self.cast}

        def find(actor: str) -> str:
            while parent[actor] != actor:
                parent[actor] = parent[parent[actor]]
                actor = parent[actor]
            return actor

        for relation in self.staging:
            if relation.predicate is Predicate.GROUND_SHARED_WITH:
                root_a, root_b = find(relation.subject), find(relation.object)
                if root_a != root_b:
                    parent[root_b] = root_a

        groups: dict[str, set[str]] = {}
        for actor in self.cast:
            groups.setdefault(find(actor), set()).add(actor)
        return tuple(frozenset(members) for members in groups.values() if len(members) > 1)


def _check_references_resolve(panel: PanelIR) -> None:
    """`PanelIR.check_references_resolve`, outside the class so that mutmut mutates it."""
    known = set(panel.cast)
    heard = panel.off_panel_speakers()
    for index, relation in enumerate(panel.staging):
        for role, actor in (("subject", relation.subject), ("object", relation.object)):
            if actor in known:
                continue
            # Somebody heard from off panel is not drawn, but may be looked at: the
            # figure turns toward the side of the frame the voice comes from.
            looked_at = role == "object" and relation.predicate is Predicate.LOOKING_AT
            if looked_at and actor in heard:
                continue
            message = (
                f"staging relation '{relation.predicate}' names unknown actor "
                f"'{actor}' as {role}; cast is {sorted(known)}"
            )
            if actor in heard:
                message += (
                    f". '{actor}' speaks from off panel, and only looking_at may name "
                    "somebody who is not drawn"
                )
            raise RuleViolationError(
                message,
                rule="unknown-actor",
                loc=("staging", index),
            )
    # Captions are skipped rather than exempted by accident. A `spoken` caption's
    # `by` names somebody *off panel*, so it is not in the cast by definition and
    # checking it here would make the field impossible to use for what it is for.
    for index, event in enumerate(panel.script):
        if isinstance(event, SfxEvent):
            if event.source is not None and event.source not in known:
                raise RuleViolationError(
                    f"sound effect {index} comes from unknown actor '{event.source}'; "
                    f"cast is {sorted(known)}",
                    rule="unknown-actor",
                    loc=("script", index, event.verb, "from"),
                )
            continue
        if not isinstance(event, SayEvent):
            continue
        # An off-panel speaker is somebody nobody draws, so not in the cast -- and one
        # who is drawn in this panel cannot also be speaking from outside it.
        if event.off_panel is not False:
            if event.by in known:
                raise RuleViolationError(
                    f"script entry {index} is spoken from off panel by '{event.by}', "
                    "who is drawn in this panel; leave them out of the cast, or drop "
                    "off_panel",
                    rule="off-panel-speaker",
                    loc=("script", index, event.verb, "by"),
                )
            continue
        if event.by not in known:
            raise RuleViolationError(
                f"script entry {index} is spoken by unknown actor '{event.by}'; "
                f"cast is {sorted(known)}. If they speak from outside the panel, "
                "say so with off_panel",
                rule="unknown-actor",
                loc=("script", index, event.verb, "by"),
            )


def _check_ordering_is_consistent(panel: PanelIR) -> None:
    """`PanelIR.check_ordering_is_consistent`, outside the class so that mutmut mutates it."""
    edges: dict[str, set[str]] = {actor: set() for actor in panel.cast}
    # Which staging entry introduced each edge, so a cycle can be reported against a
    # line the author actually wrote rather than against the document as a whole.
    # First writer wins: if two entries state the same ordering, the earlier one is
    # the one to point at.
    wrote: dict[tuple[str, str], int] = {}
    for index, relation in enumerate(panel.staging):
        if relation.predicate is Predicate.LEFT_OF:
            edge = (relation.subject, relation.object)
        elif relation.predicate is Predicate.RIGHT_OF:
            edge = (relation.object, relation.subject)
        else:
            continue
        edges[edge[0]].add(edge[1])
        wrote.setdefault(edge, index)

    # Iterative depth-first search, so a deep cast cannot blow the Python stack.
    colour = dict.fromkeys(edges, _UNVISITED)
    for start in sorted(edges):
        if colour[start] != _UNVISITED:
            continue
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                colour[node] = _DONE
                continue
            colour[node] = _ON_STACK
            stack.append((node, True))
            for neighbour in sorted(edges[node]):
                if colour[neighbour] == _ON_STACK:
                    culprit = wrote.get((node, neighbour))
                    raise RuleViolationError(
                        f"horizontal ordering is cyclic around '{neighbour}'; "
                        "left_of/right_of relations must form a consistent order",
                        rule="ordering-cycle",
                        loc=("staging",) if culprit is None else ("staging", culprit),
                    )
                if colour[neighbour] == _UNVISITED:
                    stack.append((neighbour, False))


def _check_figures(panel: PanelIR) -> None:
    """`PanelIR.check_figures`, outside the class so that mutmut mutates it."""
    figures = panel.figures()
    if not figures:
        return
    for actor, member in panel.cast.items():
        if not member.is_figure:
            continue
        if member.reference is not None:
            raise RuleViolationError(
                f"cast member {actor!r} names a puppet and a figure the picture draws; it "
                "is one or the other. Over an inherited member, write `reference: null`",
                rule="conflicting-cast",
                loc=("cast", actor, "reference"),
            )
        for key in PUPPET_KEYS:
            if getattr(member, key) != CastMember.model_fields[key].default:
                raise RuleViolationError(
                    f"cast member {actor!r} is a figure the picture draws, which nobody "
                    f"poses or places, so {key!r} does not apply to it",
                    rule="conflicting-cast",
                    loc=("cast", actor, key),
                )
    puppets = [actor for actor, member in panel.cast.items() if not member.is_figure]
    if puppets:
        raise RuleViolationError(
            f"the cast mixes puppets ({', '.join(puppets)}) with figures the picture draws "
            f"({', '.join(figures)}); a panel's cast is all one or all the other, since "
            "staging would place a puppet over a painted face it cannot see",
            rule="conflicting-cast",
            loc=("cast", puppets[0], "reference"),
        )
    played: dict[str, str] = {}
    for actor, figure in figures.items():
        if figure in played:
            raise RuleViolationError(
                f"figure {figure!r} is played by {played[figure]!r} already; one figure "
                "the picture draws is one person",
                rule="conflicting-cast",
                loc=("cast", actor, "figure"),
            )
        played[figure] = actor
    for index, relation in enumerate(panel.staging):
        named = next(
            (actor for actor in (relation.subject, relation.object) if actor in figures),
            None,
        )
        if named is not None:
            raise RuleViolationError(
                f"staging relation '{relation.predicate}' names {named!r}, a figure the "
                "picture draws: the artist already placed and staged everyone in it",
                rule="figure-staging",
                loc=("staging", index),
            )


class PageFormat(Strict):
    """The page every panel on it is laid out on.

    In the same units a panel uses, and a unit prints as a tenth of a millimetre:
    the default page prints at 200 x 300 mm, and a US comic's 6.625 x 10.25 inches is
    `size: [1682.75, 2603.5]`.

    Example:
        >>> from scenet import PageFormat
        >>> PageFormat().size
        (2000.0, 3000.0)

    See Also:
        :class:`PageLayout <scenet.ir.PageLayout>`, which holds it.
    """

    size: tuple[float, float] = (2000.0, 3000.0)
    """The page's width and height: the trim, the size the printed page is cut to, in the units
    a panel uses. Printed, a unit is a tenth of a millimetre.
    """
    margin: float = Field(default=100.0, ge=0.0)
    """The blank border inside the page's edge, on all four sides."""
    gutter: float = Field(default=40.0, ge=0.0)
    """The gap between two panels, or two columns, side by side in a tier."""
    tier_gutter: float = Field(default=60.0, ge=0.0)
    """The gap between two tiers, and between two panels stacked in a column. Wider than
    `gutter`, as in print, so a tier reads as one row.
    """
    bleed: float = Field(default=0.0, ge=0.0)
    """How far the printed sheet runs past the trim on every side, so art that reaches the edge
    can be cut cleanly: 30 is 3 mm. Paper around the page; nothing on it moves.
    """

    @property
    def width(self) -> float:
        """Page width."""
        return self.size[0]

    @property
    def height(self) -> float:
        """Page height."""
        return self.size[1]

    @model_validator(mode="after")
    def check_positive(self) -> Self:
        """Reject a page with no area inside its margin."""
        _check_positive_page_format(self)
        return self


def _check_positive_page_format(page: PageFormat) -> None:
    """`PageFormat.check_positive`, outside the class so that mutmut mutates it."""
    if page.width <= 0 or page.height <= 0:
        raise RuleViolationError("page size must be positive", rule="page-layout", loc=("page",))
    if page.margin * 2 >= min(page.width, page.height):
        raise RuleViolationError(
            "the page margin leaves no room for panels", rule="page-layout", loc=("page",)
        )


class Corner(StrEnum):
    """Which corner of its parent an inset sits in.

    Example:
        >>> from scenet import Corner, Inset
        >>> Inset(use="detail", at="top_right", size=0.3).at is Corner.TOP_RIGHT
        True

    See Also:
        :class:`Inset <scenet.ir.Inset>`, whose `at` takes one.
    """

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


class InsetOrder(StrEnum):
    """Whether an inset is read before the panel it sits in, or after it.

    Example:
        >>> from scenet import Inset, InsetOrder
        >>> Inset(use="detail", at="top_right", size=0.3).read is InsetOrder.AFTER
        True

    See Also:
        :class:`Inset <scenet.ir.Inset>`, whose `read` takes one.
    """

    BEFORE = "before"
    AFTER = "after"


class Inset(Strict):
    """A small panel set into a corner of another, and drawn over it.

    Readers do not agree on when to read an inset: in Cohn's 2013 experiments, overlap
    split them about evenly between the inset and the panel under it. So the order is
    stated rather than guessed -- after its parent, unless `read: before`.

    Example:
        >>> from scenet import Inset
        >>> inset = Inset(use="detail", at="bottom_left", size=0.25)
        >>> inset.read.value
        'after'

    See Also:
        :class:`Corner <scenet.ir.Corner>` and :class:`InsetOrder <scenet.ir.InsetOrder>`,
        what it takes.
    """

    use: str
    """The name of a panel under `panels:`, set into this one."""
    at: Corner
    """The corner of its parent the inset sits in, a gutter in from both edges."""
    size: float = Field(gt=0.0, le=0.5)
    """The inset's width and height, as a fraction of its parent's: above 0, at most 0.5."""
    read: InsetOrder = InsetOrder.AFTER
    """When the inset is read: `after` its parent, or `before` it."""


class PanelPlacement(Strict):
    """One panel in a tier.

    Written as the panel's name alone, or as `{use: name, width: 2}` to give it a larger
    share of the tier.

    Example:
        >>> from scenet import PanelPlacement
        >>> PanelPlacement(use="one", width=2).width
        2.0

    See Also:
        :class:`Tier <scenet.ir.Tier>`, whose `panels` holds them.
        :class:`Inset <scenet.ir.Inset>`, a panel set into this one.
    """

    use: str
    """The name of a panel under `panels:`. Writing the name alone means `{use: name}`."""
    width: float = Field(default=1.0, gt=0.0)
    """The panel's share of its tier's width, relative to its neighbours."""
    insets: tuple[Inset, ...] = ()
    """Panels set into its corners, and drawn over it."""
    bleed: bool | tuple[Side, ...] = False
    """Run the frame past the trim to the bleed line, with no border there: `true` on every side
    that reaches the page's margin, or a list of those sides.
    """


class StackedPanel(Strict):
    """One panel in a column.

    Written as the panel's name alone, or as `{use: name, height: 2}` to give it a larger
    share of the column.

    Example:
        >>> from scenet import StackedPanel
        >>> StackedPanel(use="top", height=2).height
        2.0

    See Also:
        :class:`Column <scenet.ir.Column>`, whose `panels` holds them.
    """

    use: str
    """The name of a panel under `panels:`. Writing the name alone means `{use: name}`."""
    height: float = Field(default=1.0, gt=0.0)
    """The panel's share of its column's height, relative to the others in it."""
    insets: tuple[Inset, ...] = ()
    """Panels set into its corners, and drawn over it."""
    bleed: bool | tuple[Side, ...] = False
    """Run the frame past the trim to the bleed line, with no border there: `true` on every side
    that reaches the page's margin, or a list of those sides.
    """


def _read_with_insets(
    placement: PanelPlacement | StackedPanel, path: tuple[str | int, ...]
) -> list[tuple[str, tuple[str | int, ...]]]:
    """A panel and its insets, each with its path, in the order they are read."""
    insets = [(inset, (*path, "insets", index)) for index, inset in enumerate(placement.insets)]
    return [
        *((inset.use, at) for inset, at in insets if inset.read is InsetOrder.BEFORE),
        (placement.use, path),
        *((inset.use, at) for inset, at in insets if inset.read is InsetOrder.AFTER),
    ]


class Column(Strict):
    """Panels stacked top to bottom, beside the other columns of a tier.

    Example:
        >>> from scenet import Column
        >>> column = Column(width=1, panels=[{"use": "top"}, {"use": "bottom"}])
        >>> [panel.use for panel in column.panels]
        ['top', 'bottom']

    See Also:
        :class:`StackedPanel <scenet.ir.StackedPanel>`, one panel in it.
    """

    width: float = Field(default=1.0, gt=0.0)
    """The column's share of its tier's width, relative to the other columns."""
    panels: tuple[StackedPanel, ...] = Field(min_length=1)
    """The panels in the column, read top to bottom."""


class Tier(Strict):
    """A row of panels read in turn, or of columns each read top to bottom.

    Columns are how a tall panel beside a stack of short ones is written. The stack is
    read down before the page is read across, which is what readers do when a panel
    spanning the tier blocks the way across (Cohn, *Navigating Comics*, 2013).

    A tier of panels can lean the gutters between them by `slant` degrees, for a beat that
    should not sit square: each gutter tilts about its centre at the tier's mid-height,
    neighbours share the cut, and the tier's outer edges stay upright.

    Example:
        >>> from scenet import Tier
        >>> tier = Tier(panels=[{"use": "wide"}, {"use": "narrow", "width": 0.5}])
        >>> [placement.width for placement in tier.panels]
        [1.0, 0.5]

    See Also:
        :class:`Column <scenet.ir.Column>`, panels stacked within a tier.
        :class:`PageSpec <scenet.ir.PageSpec>`, whose `tiers` holds them.
    """

    height: float = Field(default=1.0, gt=0.0)
    """The tier's share of the page's height, relative to the other tiers."""
    panels: tuple[PanelPlacement, ...] = ()
    """The panels in the tier, in reading order: left to right, or right to left for a comic
    read that way.
    """
    columns: tuple[Column, ...] = ()
    """In place of `panels`: columns side by side, each a stack of panels read top to bottom
    before the next.
    """
    slant: float = Field(default=0.0, ge=-30.0, le=30.0)
    """How far the gutters between the tier's panels lean, in degrees, from -30 to 30. Positive
    leans the top of each gutter to the right.
    """

    @model_validator(mode="after")
    def check_one_kind(self) -> Self:
        """A tier is a row of panels or a row of columns: never both, never neither."""
        _check_one_kind(self)
        return self

    @model_validator(mode="after")
    def check_slant(self) -> Self:
        """A slant leans the gutters between panels, so it needs some to lean.

        Refused rather than ignored where it would do nothing, or something undefined: a
        column's gutters run across it, and an inset is set into a rectangular corner.
        """
        _check_slant(self)
        return self

    @property
    def placed(self) -> tuple[tuple[str, tuple[str | int, ...]], ...]:
        """Each panel's name and path within the tier, insets included, in reading order."""
        if self.panels:
            return tuple(
                entry
                for index, placement in enumerate(self.panels)
                for entry in _read_with_insets(placement, ("panels", index))
            )
        return tuple(
            entry
            for column_index, column in enumerate(self.columns)
            for index, stacked in enumerate(column.panels)
            for entry in _read_with_insets(stacked, ("columns", column_index, "panels", index))
        )


def _check_one_kind(tier: Tier) -> None:
    """`Tier.check_one_kind`, outside the class so that mutmut mutates it."""
    if bool(tier.panels) == bool(tier.columns):
        raise RuleViolationError(
            "a tier holds either `panels:` or `columns:`, and this one has "
            + ("both" if tier.panels else "neither"),
            rule="page-layout",
        )


def _check_slant(tier: Tier) -> None:
    """`Tier.check_slant`, outside the class so that mutmut mutates it."""
    if not tier.slant:
        return
    if tier.columns:
        problem = "a tier of columns has no upright gutters between panels to lean"
    elif len(tier.panels) == 1:
        problem = "this tier has one panel, so there is no gutter to lean"
    elif any(placement.insets for placement in tier.panels):
        problem = "an inset is set into a square corner, which a slanted panel lacks"
    else:
        return
    raise RuleViolationError(
        f"`slant` leans the gutters between panels; {problem}", rule="page-layout"
    )


class PageSpec(Strict):
    """One page: tiers, top to bottom.

    A page is read tier by tier, left to right within a tier -- right to left, for a
    document whose `direction` is `rtl` -- and down each column of a tier of columns, so the
    order panels are written in is the order they are read in.
    That is the page's version of the rule a balloon obeys, and it holds by construction:
    columns that readers would not read down are refused by
    :class:`PageLayout <scenet.ir.PageLayout>`.

    Example:
        >>> from scenet import PageSpec, Tier
        >>> page = PageSpec(tiers=[Tier(panels=[{"use": "one"}, {"use": "two"}])])
        >>> [placement.use for placement in page.tiers[0].panels]
        ['one', 'two']

    See Also:
        :class:`Tier <scenet.ir.Tier>`, one row of it.
    """

    tiers: tuple[Tier, ...] = Field(min_length=1)
    """The page's tiers, top to bottom."""


class PageLayout(Strict):
    r"""Every page of a scene, and the format they share.

    The panels themselves are not part of it: a page names them, and
    :func:`check_placements <scenet.ir.check_placements>` checks the names against the
    panels the document defines.

    Example:
        >>> from scenet import PageLayout, parse_scene_document
        >>> document = parse_scene_document(
        ...     "cast: {a: {reference: alice}}\npanels: {one: {}}\n"
        ...     "pages: [{tiers: [{panels: [one]}]}]"
        ... )
        >>> isinstance(document.layout, PageLayout), len(document.layout.pages)
        (True, 1)

    See Also:
        :class:`PageSpec <scenet.ir.PageSpec>`, one page.
        :class:`PageFormat <scenet.ir.PageFormat>`, the page's size and margins.
    """

    page: PageFormat = PageFormat()
    """The format every page shares: its size, margin, gutters and bleed."""
    pages: tuple[PageSpec, ...] = ()
    """The pages, in order, each a list of tiers top to bottom."""

    @model_validator(mode="after")
    def check_room(self) -> Self:
        """Every tier must have room for its panels and every page for its tiers."""
        _check_room(self)
        return self


def _check_room(layout: PageLayout) -> None:
    """`PageLayout.check_room`, outside the class so that mutmut mutates it."""
    usable_width = layout.page.width - 2 * layout.page.margin
    usable_height = layout.page.height - 2 * layout.page.margin
    for page_index, page in enumerate(layout.pages):
        tiers_height = usable_height - layout.page.tier_gutter * (len(page.tiers) - 1)
        if tiers_height <= 0:
            raise RuleViolationError(
                f"page {page_index + 1} has no room for {len(page.tiers)} tiers between "
                "its margins and tier gutters",
                rule="page-layout",
                loc=("pages", page_index),
            )
        total_height = sum(tier.height for tier in page.tiers)
        for tier_index, tier in enumerate(page.tiers):
            loc: tuple[str | int, ...] = ("pages", page_index, "tiers", tier_index)
            where = f"tier {tier_index + 1} of page {page_index + 1}"
            across = len(tier.panels) or len(tier.columns)
            what = "panels" if tier.panels else "columns"
            if usable_width - layout.page.gutter * (across - 1) <= 0:
                raise RuleViolationError(
                    f"{where} has no room for {across} {what} between its margins and gutters",
                    rule="page-layout",
                    loc=loc,
                )
            height = tiers_height * tier.height / total_height
            for column_index, column in enumerate(tier.columns):
                if height - layout.page.tier_gutter * (len(column.panels) - 1) <= 0:
                    raise RuleViolationError(
                        f"column {column_index + 1} of {where} has no room for "
                        f"{len(column.panels)} panels between its tier gutters",
                        rule="page-layout",
                        loc=(*loc, "columns", column_index),
                    )
            _check_stacks_are_blocked(tier, loc, where)


def _check_stacks_are_blocked(tier: Tier, loc: tuple[str | int, ...], where: str) -> None:
    """Refuse two stacked columns side by side.

    A stack is read down before across because the panel beside it spans the tier and
    blocks the way across: about nine readers in ten then go down (Cohn 2013, *blockage*).
    Beside another stack nothing blocks the way. That is a grid, or a staggered one, which
    about nine readers in ten read across instead, so reading down it would put its panels
    in an order the reader does not follow.
    """
    for index in range(1, len(tier.columns)):
        if len(tier.columns[index - 1].panels) > 1 and len(tier.columns[index].panels) > 1:
            raise RuleViolationError(
                f"columns {index} and {index + 1} of {where} are both stacks; with no panel "
                "spanning the tier between them, readers go across them rather than down. "
                "Put a panel that spans the tier between them, or write them as tiers",
                rule="page-layout",
                loc=(*loc, "columns", index),
            )


def check_placements(layout: PageLayout, panels: Sequence[str]) -> None:
    """Check that every placement names a panel, and that none is placed twice.

    A panel that is on no page is allowed: it may exist only to be inherited from.

    Args:
        layout: The validated pages.
        panels: The names the document's `panels:` defines.

    Raises:
        RuleViolationError: Rule `page-layout`, located at the placement at fault.
    """
    known = set(panels)
    placed: dict[str, tuple[str | int, ...]] = {}
    for page_index, page in enumerate(layout.pages):
        for tier_index, tier in enumerate(page.tiers):
            for use, within in tier.placed:
                loc = ("pages", page_index, "tiers", tier_index, *within)
                if use not in known:
                    raise RuleViolationError(
                        f"page {page_index + 1} places panel '{use}', which "
                        f"`panels:` does not define; it has {sorted(known)}",
                        rule="page-layout",
                        loc=loc,
                    )
                if use in placed:
                    raise RuleViolationError(
                        f"panel '{use}' is placed twice; a panel has one frame, "
                        "so it can be on one page once",
                        rule="page-layout",
                        loc=loc,
                    )
                placed[use] = loc
