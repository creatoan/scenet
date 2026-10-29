"""Panel Core: the resolved intermediate format.

Every position is absolute and numeric, but identifiers survive -- which is what
separates this from SVG. A Core document can be read, diffed, hand-adjusted and
re-emitted.

Golden-file tests target this tier rather than the SVG, because it changes only when
layout genuinely changes. Diffing SVG text is brittle: a reordered attribute or a
different path-rounding convention produces a huge diff that means nothing.
"""

import json
from typing import Annotated, Any, Literal, NamedTuple, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, Tag, model_validator
from pydantic.json_schema import SkipJsonSchema

from scenet.geom import PRECISION, BBox, Circle, Point, Vector, rounded
from scenet.images import MediaType
from scenet.ir import (
    UNTAGGED,
    BalloonKind,
    CameraAngle,
    CaptionKind,
    Direction,
    Face,
    Fit,
    Mark,
    MassKind,
    Plane,
    ShotType,
    Side,
    SvgText,
    TimeOfDay,
    Weather,
    tag_by,
)
from scenet.paths import check_relative
from scenet.places import Place

CORE_FORMAT_VERSION = 1


class CoreModel(BaseModel):
    """Base for every Panel Core type: frozen, and rejecting unknown keys.

    Strictness matters more here than in the IR. A Core document is something a user
    may hand-edit and feed back in, and a silently-ignored key would mean their edit
    had no effect with nothing to say so. `json.loads` reads `NaN` and `Infinity`, and
    neither is a coordinate, so a Core holding one is refused rather than drawn.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Transform(CoreModel):
    """Where a puppet's root joint lands, and how it is scaled and mirrored."""

    x: float
    y: float
    scale: float
    mirrored: bool


class Box(CoreModel):
    """A rectangle, as stored in a Core document.

    The serialisable twin of :class:`BBox <scenet.geom.BBox>`. The geometry code works in
    `BBox`; this is what gets written to JSON, with every value already rounded so the
    file is byte-identical across platforms.

    Attributes:
        x: Left edge.
        y: Top edge.
        width: Extent rightward.
        height: Extent downward.
    """

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        """The right edge, `x + width`."""
        return self.x + self.width

    @property
    def bottom(self) -> float:
        """The bottom edge, `y + height`."""
        return self.y + self.height

    @classmethod
    def of(cls, bbox: BBox) -> Self:
        """Build a `Box` from a geometry `BBox`, rounding for emission.

        Args:
            bbox: The box to convert.

        Returns:
            The serialisable equivalent, with all four values rounded.
        """
        return cls(
            x=rounded(bbox.x),
            y=rounded(bbox.y),
            width=rounded(bbox.width),
            height=rounded(bbox.height),
        )

    def as_bbox(self) -> BBox:
        """Convert back to a geometry `BBox` for further computation."""
        return BBox(self.x, self.y, self.width, self.height)


class Disc(CoreModel):
    """A circle, as stored in a Core document.

    Usually a face exclusion zone -- the region no balloon may cover. Also a fleck of
    falling snow, which is the same shape and wants the same rounding.

    Attributes:
        cx: Centre x.
        cy: Centre y.
        r: Radius.
    """

    cx: float
    cy: float
    r: float

    @classmethod
    def of(cls, circle: Circle) -> Self:
        """Build a `Disc` from a geometry `Circle`, rounding for emission.

        Args:
            circle: The circle to convert.

        Returns:
            The serialisable equivalent.
        """
        return cls(cx=rounded(circle.cx), cy=rounded(circle.cy), r=rounded(circle.r))

    def as_circle(self) -> Circle:
        """Convert back to a geometry `Circle` for further computation."""
        return Circle(self.cx, self.cy, self.r)


class Capsule(CoreModel):
    """A limb segment, as a thick line with rounded ends."""

    start: tuple[float, float]
    end: tuple[float, float]
    width: float


class Blob(CoreModel):
    """A rounded mass -- a head, a hand -- drawn as a filled circle.

    Attributes:
        centre: `(x, y)` of the centre.
        radius: Radius in panel units.
    """

    centre: tuple[float, float]
    radius: float


class FaceStroke(CoreModel):
    """One line of a drawn face, already sampled into straight segments.

    Curves are sampled during compilation rather than emitted as Bezier control
    points, so that everything an expression does is a number here. A face can then be
    read, diffed and hand-adjusted exactly like the rest of this tier, and the emitter
    has nothing left to decide.

    Attributes:
        mark: Always `stroke`. What distinguishes this from a `FaceDisc`.
        id: Which feature this draws -- `brow_l`, `mouth`, and so on.
        points: The polyline, in panel coordinates.
        width: Stroke width in panel units.
        closed: Whether the last point joins back to the first, which is what makes an
            open mouth a shape rather than a stray arc.
    """

    mark: Literal["stroke"] = "stroke"
    id: str
    points: tuple[tuple[float, float], ...]
    width: float
    closed: bool = False


class FaceDisc(CoreModel):
    """A round mark on a face -- an eye, or the pupil inside it.

    Attributes:
        mark: Always `disc`.
        id: Which feature this draws.
        centre: `(x, y)` of the centre.
        radius: Radius in panel units.
        filled: Filled marks are pupils; outlined ones are the eyes around them.
        width: Outline width in panel units, ignored when `filled`.
    """

    mark: Literal["disc"] = "disc"
    id: str
    centre: tuple[float, float]
    radius: float
    filled: bool = False
    width: float = 0.0


#: One mark on a drawn face, or of the emanata drawn around it -- they are made of the
#: same two primitives. Chosen by its `mark`, exactly as a script entry is by its verb, so
#: a hand-edited disc with a bad radius is not also reported as every reason it is not a
#: stroke. A mark written without the tag is still accepted.
FaceMark = Annotated[
    Annotated[FaceStroke, Tag("stroke")]
    | Annotated[FaceDisc, Tag("disc")]
    | Annotated[SkipJsonSchema[FaceStroke | FaceDisc], Tag(UNTAGGED)],
    tag_by("mark"),
]


class CoreMass(CoreModel):
    """One tonal mass of the backdrop, resolved to a numeric polygon.

    The same discipline as `capsules`, `blobs` and `face_marks`: everything the emitter
    needs is a number by the time it gets here, so drawing a backdrop involves no layout
    decision at all.

    Attributes:
        id: Stable identifier, `m0`, `m1`, ... back to front.
        kind: What the mass is made of. Carried so a Core document stays readable -- it
            is not consulted when drawing, since the tone is already resolved. The depth
            export reads it: the sky is at infinity, and a ground, floor, water or ceiling
            recedes.
        plane: How far back it sits.
        depth: Painter's order, shared with the actors. Backdrop planes are negative;
            a foreground mass sits above the frontmost actor.
        tone: The `#rrggbb` fill, already chosen from the value ladder.
        polygon: The silhouette, in panel coordinates.
    """

    id: str
    kind: MassKind
    plane: Plane
    depth: int
    tone: str
    polygon: tuple[tuple[float, float], ...]


class CoreVeil(CoreModel):
    """The atmospheric noise layer, as parameters rather than as pixels.

    SVG has Perlin noise built in through `feTurbulence`, and the specification includes
    reference code, so a fixed `seed` is reproducible **by definition**: the emitted text
    is byte-identical. Browsers agree only approximately on what to paint from it, which
    is fine and is exactly why the determinism contract is on the SVG text and has never
    been on pixels.

    Attributes:
        tone: The `#rrggbb` the veil is tinted.
        opacity: How much of it lands, `0 .. 1`.
        frequency: `baseFrequency`, per panel unit.
        octaves: `numOctaves`.
        seed: `seed`, derived from the declared content and the panel size.
    """

    tone: str
    opacity: float
    frequency: float
    octaves: int
    seed: int


class CoreStreak(CoreModel):
    """One streak of falling rain.

    The width is on :class:`CoreAtmosphere <scenet.core.CoreAtmosphere>` rather than
    here: every streak in a panel shares it, and repeating it per streak would make the
    file longer without making it say anything more.
    """

    start: tuple[float, float]
    end: tuple[float, float]


class CoreAtmosphere(CoreModel):
    """What the air is doing, resolved.

    Attributes:
        time: When the panel happens. Recorded rather than re-derived, for the same
            reason `CoreCaption.italic` is: the emitter must not be able to draw
            something the solver did not resolve.
        weather: What is falling, if anything.
        tone: The atmosphere's own value at this hour.
        veil: The noise layer -- fog, or cloud for rain and snow.
        streaks: Rain, every streak at the same angle.
        flecks: Snow.
        streak_width: Stroke width for a streak, in panel units.
        fall_tone: What rain and snow are drawn in -- ink over a bright sky, paper over
            a dark one. Resolved rather than left to the emitter, because which one
            reads is a fact about this panel.
    """

    time: TimeOfDay
    weather: Weather
    tone: str
    veil: CoreVeil | None = None
    streaks: tuple[CoreStreak, ...] = ()
    flecks: tuple[Disc, ...] = ()
    streak_width: float = 0.0
    fall_tone: str = ""


def _relative(href: str) -> str:
    """Refuse a hand-edited link no document could have written."""
    check_relative(href, what="image", rule="image-file")
    return href


class CoreImage(CoreModel):
    """A supplied picture behind the cast, placed (#70).

    Everything a renderer needs, resolved: where the picture is, what it is, and the
    rectangle it is drawn in. Nothing about its content -- the solver never saw any.

    Attributes:
        href: The path exactly as the document wrote it, relative to the document. A
            linked SVG points at the picture by it; nothing else about where the file
            was reaches the output.
        media_type: `image/png` or `image/jpeg`, from the file's own bytes -- what a
            `data:` URI of it is labelled.
        sha256: The digest of its bytes, which is what it is known by: an embedding
            renderer is handed bytes by digest, and refuses a Core naming bytes it was
            not given, as it refuses a font.
        pixels: Its size, `(width, height)`, read from its header.
        fit: How it fills the panel.
        preserve_aspect_ratio: The same fit in SVG's words, `xMidYMid slice` for `cover`
            and `xMidYMid meet` for `contain`. Recorded rather than derived, as
            :attr:`CoreCaption.italic <scenet.core.CoreCaption.italic>` is: the emitter
            copies it. `box` already has the picture's proportions, so a renderer that
            reads them as the compiler did draws the same either way; this says what to
            do to one that does not.
        box: Where the picture is drawn, in panel units: centred, larger than the panel
            under `cover` and cropped by it, inside it under `contain`. Change it and
            the picture moves.
        keep_out: The regions of the picture its artwork contract asks lettering to stay
            off (#71), in panel units: what balloons, captions and sound effects paid to
            cover, and were never forbidden to. Left out of the JSON when there are none.
    """

    href: Annotated[str, AfterValidator(_relative)]
    media_type: MediaType
    sha256: str
    pixels: tuple[int, int]
    fit: Fit
    preserve_aspect_ratio: Literal["xMidYMid slice", "xMidYMid meet"]
    box: Box
    keep_out: tuple[tuple[tuple[float, float], ...], ...] = ()


class CoreBackdrop(CoreModel):
    """Where the panel is, resolved: masses, tones, the air, or a supplied picture.

    Attributes:
        horizon: Where the ground meets what is behind it, in panel units. Left out over
            a supplied picture, whose horizon the compiler does not know.
        seed: What every silhouette in here was generated from. Kept so that a Core
            document explains itself: two panels with the same masses and different
            skylines differ here, and here is where to look.
        masses: The tonal masses, back to front.
        atmosphere: The air, or None when the weather is clear.
        image: The supplied picture behind everything, or None. Left out of the JSON
            when unset.
        place: The named place these masses are -- `street`, `docks` -- whether `place:`
            wrote them or an author wrote the same list out (#72). None for masses no place
            expands into, and over a picture. A name for what is here, never read to draw
            it. Left out of the JSON when None.
        time: The hour the values were chosen for (#72), which `atmosphere` records too
            but only when something is in the air. None over a picture, whose hour is in
            the picture. Left out of the JSON when None.

    Optional on :class:`PanelCore <scenet.core.PanelCore>`, so every document written
    before this existed is still a valid one -- which is why adding it did not need a
    `format_version` bump, the same argument captions made. `image` and a missing
    `horizon` are additions of the same kind: a backdrop of masses reads and writes
    byte for byte as it did.
    """

    horizon: float | None = None
    seed: int
    masses: tuple[CoreMass, ...] = ()
    atmosphere: CoreAtmosphere | None = None
    image: CoreImage | None = None
    place: Place | None = None
    time: TimeOfDay | None = None


class CoreActor(CoreModel):
    """One character, fully resolved: placed, posed, scaled and measured.

    This is the geometric contract in its final form. Everything the emitter needs to
    draw the figure, and everything the balloon placer needed to avoid it, with no
    reference to artwork of any kind.

    Attributes:
        id: The actor id from the panel source.
        reference: Which puppet was used. Two actors may share one.
        pose: Which named pose was applied.
        expression: Which named expression was applied.
        transform: Where the root joint landed, and the scale and mirroring applied.
        anchors: Named attachment points -- `mouth`, `eyes`, and whatever else the
            puppet declared -- already in panel coordinates.
        face_exclusion: The disc no balloon may overlap.
        gaze: Unit direction the character is facing, `(dx, dy)`. Derived from the
            head's rotation, and what balloon placement reads to keep out of a line of
            sight.
        gaze_aim: Unit direction from the eyes to whoever this character is
            `looking_at`, or None when they are looking at nobody. Separate from
            `gaze` because it is known only after every actor has been placed, and
            because balloon placement must go on reading the same vector it always
            has. This is what aims the pupils.
        face_marks: The drawn face -- brows, eyes, pupils, nose, mouth -- as resolved
            numeric primitives. Empty when the puppet declares no features, or when
            the figure is too small for features to read as anything but a smudge.
        marks: Which emanata were asked for -- `plewds`, `grawlixes`, and so on.
        emanata: The marks drawn around the character, as the same strokes and discs
            a face is made of. Empty when there are no marks, or when the figure is too
            small to have a face. Ids are numbered per mark: `plewd_0`, `plewd_1`, ...
        emanata_zones: One polygon per mark, enclosing what it draws. Balloons and
            captions pay to cover these and are never forbidden to. Kept apart from
            `hull` on purpose: the hull is what staging spaces characters by, and a
            character who starts sweating must not move.
        hull: Convex silhouette, used for the soft occlusion cost.
        capsules: Limb segments, as thick rounded lines.
        blobs: Rounded masses such as the head.
        depth: Painter's order. Lower is drawn first, so higher sits in front.
        joints: Where every joint of the skeleton landed, by the puppet's name for it, in
            panel coordinates (#72). `_l` and `_r` are the sides of the screen in the
            puppet's rest pose, so on a figure facing left `shoulder_l` is on the right.
            Nothing here draws from them; they are the posed skeleton, for an export.
        features: Where each face feature point sits -- `eye_l`, `nose`, `mouth` and the
            rest the puppet declares -- in panel coordinates (#72). The anatomy, not the
            marks: the same whatever the expression, and recorded when the face is too
            small to draw.
        looking_at: Whom this character looks at (#72): an actor id, or the name of
            somebody heard from off panel. `gaze_aim` is the direction; this is who.

    The last three are left out of the JSON when empty, so an actor written before them
    reads and writes as it did.
    """

    id: str
    reference: str
    pose: str
    transform: Transform
    anchors: dict[str, tuple[float, float]]
    face_exclusion: Disc
    gaze: tuple[float, float]
    hull: tuple[tuple[float, float], ...]
    expression: str = "neutral"
    gaze_aim: tuple[float, float] | None = None
    face_marks: tuple[FaceMark, ...] = ()
    marks: tuple[Mark, ...] = ()
    emanata: tuple[FaceMark, ...] = ()
    emanata_zones: tuple[tuple[tuple[float, float], ...], ...] = ()
    capsules: tuple[Capsule, ...] = ()
    blobs: tuple[Blob, ...] = ()
    # Painter's order: lower values are drawn first, so higher values sit in front.
    depth: int = 0
    joints: dict[str, tuple[float, float]] = Field(default_factory=dict)
    features: dict[str, tuple[float, float]] = Field(default_factory=dict)
    looking_at: SvgText | None = None

    @property
    def bounds(self) -> BBox:
        """Axis-aligned bounds of the silhouette."""
        xs = [x for x, _ in self.hull]
        ys = [y for _, y in self.hull]
        return BBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class CoreFigure(CoreModel):
    """A figure a supplied picture draws, as its artwork contract declares it (#71).

    Not a :class:`CoreActor <scenet.core.CoreActor>`: nobody posed it, so it has no
    transform, no skeleton and nothing to draw -- the picture draws it. What is here is
    what lettering worked around, in panel units, mapped from the picture's pixels through
    the same fit as the picture's `box`.

    Attributes:
        figure: Its name in the contract.
        actor: The cast member it plays, or None for a figure nobody cast -- whose face
            lettering kept clear of just the same. Left out of the JSON when None.
        face_exclusion: The disc no balloon, caption or sound effect may overlap.
        mouth: Where a tail it speaks aims, if the contract declares one; otherwise the
            face's centre. Left out of the JSON when None.
        body: Its silhouette, which lettering paid to cover. Left out of the JSON when
            the contract declares none.
    """

    figure: SvgText
    face_exclusion: Disc
    actor: SvgText | None = None
    mouth: tuple[float, float] | None = None
    body: tuple[tuple[float, float], ...] = ()


class Speaking(NamedTuple):
    """Somebody a balloon points at, in a Core: the face, and where its tail aims."""

    face: Disc
    mouth: tuple[float, float]


class Tail(CoreModel):
    """The pointer from a balloon to its speaker's mouth.

    `control` is present only when the straight route was obstructed and the tail had
    to bend, which keeps the common case honest about being a simple straight line.
    """

    start: tuple[float, float]
    end: tuple[float, float]
    control: tuple[float, float] | None = None
    width: float = 14.0

    @property
    def is_curved(self) -> bool:
        """Whether this tail had to bend around an obstacle."""
        return self.control is not None


class CoreRun(CoreModel):
    """A stretch of one line set in one face.

    Attributes:
        text: The characters.
        face: The face they are measured and drawn in.
    """

    text: str
    face: Face


def _check_runs(lines: tuple[str, ...], runs: tuple[tuple[CoreRun, ...], ...]) -> None:
    """Refuse runs that do not spell their lines, which would draw text never measured."""
    if not runs:
        return
    if len(runs) != len(lines):
        raise ValueError(f"runs must be given for every line: {len(lines)} lines, {len(runs)} runs")
    for index, (line, cut) in enumerate(zip(lines, runs, strict=True)):
        spelled = "".join(run.text for run in cut)
        if spelled != line:
            raise ValueError(f"the runs of line {index} spell {spelled!r}, not {line!r}")


class CoreFont(CoreModel):
    """A font file the lettering was measured in, named by what is in it.

    Attributes:
        family: Its family name, from the font's own `name` table.
        style: Its style within the family.
        sha256: The digest of the file's bytes. A renderer is handed fonts by this, and
            refuses to draw a panel whose fonts it was not handed: lettering drawn in a
            face it was not measured in would not fit the balloons drawn for it.

    Never a path. Where the file was is a fact about one machine, and a Core is the same
    wherever it was compiled.
    """

    family: str
    style: str
    sha256: str


class CoreBalloon(CoreModel):
    """One balloon, placed and with its lettering already broken into lines.

    Attributes:
        id: Stable identifier, `b0`, `b1`, ... in script order.
        speaker: Actor id of whoever is talking -- or, when `off_panel` is set, the name
            of somebody off panel, who is not an actor.
        order: Position in reading order, counting from zero.
        kind: Which sort of balloon to draw.
        box: Where it sits.
        lines: The **resolved** line breaking, not the source string.
        font_size: Type size in panel units.
        line_height: Baseline-to-baseline distance in panel units.
        tail: The pointer to the speaker's mouth.
        runs: For a line with emphasis, the line cut wherever its face changes, so each
            run is drawn in the face it was measured in. Empty when no line has any --
            and then left out of the JSON, so a balloon without emphasis reads and writes
            exactly as it did before emphasis existed. `lines` stays the plain text.
        label: Who says it, how, and the words -- `Bob, whispering: I know.` -- as
            accessible output reads it. Left out of the JSON when unset.

    Storing broken lines rather than the original string is deliberate. Wrapping is
    decided during compilation against real font metrics; if the emitter re-measured,
    it could disagree with the solver about how wide the balloon needed to be, and the
    text would overflow the shape drawn for it.
    """

    id: str
    speaker: str
    order: int
    kind: BalloonKind
    box: Box
    # The *resolved* line breaking, not the source string. Wrapping is decided during
    # compilation using real font metrics, so the emitter never re-measures and can
    # never disagree with the solver about how wide the balloon needed to be.
    lines: tuple[str, ...]
    font_size: float
    line_height: float
    tail: Tail
    runs: tuple[tuple[CoreRun, ...], ...] = ()
    # Set when the speaker is off panel: the side of the frame they are on, which the
    # tail ends on. Then `speaker` names somebody who is not an actor. Left out of the
    # document when unset, so every Core written before it reads -- and is written --
    # exactly as it was.
    off_panel: Side | None = None
    # Who says it, how, and the words, as a screen reader is to read them. Left out of the
    # document when unset, so a Core written before it reads as it did.
    label: SvgText | None = None

    @model_validator(mode="after")
    def check_runs(self) -> "CoreBalloon":
        """Runs, when given, must spell each line exactly.

        Returns:
            The validated balloon.

        Raises:
            ValueError: A line has no runs, or its runs spell something else.
        """
        _check_runs(self.lines, self.runs)
        return self


class CoreCaption(CoreModel):
    """One caption box, placed and with its lettering already broken into lines.

    Attributes:
        id: Stable identifier, `c0`, `c1`, ... in the order the captions appear.
        order: Position in the panel's reading order. Captions and balloons share one
            sequence, so a caption written between two lines of dialogue takes the
            number between theirs.
        kind: What the box is doing, which is what decides how it is set.
        box: Where it sits.
        lines: The **resolved** line breaking, quotation marks included. A `spoken`
            caption's quotes are part of the text by the time it reaches here, because
            marks added after measurement would not fit the box drawn for them.
        font_size: Type size in panel units.
        line_height: Baseline-to-baseline distance in panel units.
        italic: Whether the lettering is set in the italic face. Recorded rather than
            re-derived from `kind` so the emitter cannot draw the box in a face the
            solver did not measure it in.
        fill: The value the box is filled with, resolved from the declared tone.
        ink: The value the lettering is drawn in. Chosen against `fill` by contrast, so
            a dark box is lettered in paper -- reversed type. Resolved rather than left
            to the emitter for the same reason `italic` is, and the same reason
            :attr:`CoreAtmosphere.fall_tone <scenet.core.CoreAtmosphere>` is: which
            mark reads is a fact about the panel.
        speaker: Who is talking, for a `spoken` caption. **Not an actor id**: the
            speaker is off panel, so this resolves to nobody in `actors`.
        runs: For a line with emphasis, the line cut wherever its face changes, exactly
            as on :class:`CoreBalloon <scenet.core.CoreBalloon>`. Left out of the JSON
            when empty.
        label: What the box says, and in whose voice -- `Caption: Midnight.` -- without
            the quotation marks a `spoken` caption is lettered with. Left out of the JSON
            when unset.

    There is no tail. That is the difference that makes this its own type rather than
    a fifth :class:`BalloonKind <scenet.ir.BalloonKind>`.

    `fill` and `ink` are defaulted to the white and the near-black every caption has
    had since captions shipped, so a Core document written before tones existed is
    still a valid one -- which is why adding them needed no `format_version` bump.
    """

    id: str
    order: int
    kind: CaptionKind
    box: Box
    lines: tuple[str, ...]
    font_size: float
    line_height: float
    italic: bool
    fill: str = "#ffffff"
    ink: str = "#111111"
    speaker: str | None = None
    runs: tuple[tuple[CoreRun, ...], ...] = ()
    label: SvgText | None = None

    @model_validator(mode="after")
    def check_runs(self) -> "CoreCaption":
        """Runs, when given, must spell each line exactly.

        Returns:
            The validated caption.

        Raises:
            ValueError: A line has no runs, or its runs spell something else.
        """
        _check_runs(self.lines, self.runs)
        return self


class CoreGlyph(CoreModel):
    """One letter of a sound effect, where it is drawn.

    Attributes:
        char: The letter. Its outline comes from the display face the Core names.
        origin: Where its baseline starts, in panel units.
        angle: Its rotation about `origin`, in degrees clockwise.
    """

    char: str
    origin: tuple[float, float]
    angle: float


class CoreSfx(CoreModel):
    """One sound effect, placed, with every letter resolved.

    Attributes:
        id: `s0`, `s1`, ... in script order.
        order: Its number in the panel's one reading order, which it shares with
            balloons and captions. It is exempt from the geometric reading-order rule: a
            sound sits where the sound is.
        text: The sound, as written -- what a reader of the text is given.
        source: The actor it comes from, if it names one.
        font_size: Its type size in panel units, in the display face.
        glyphs: Every letter: where it starts, and how far it is turned. The arc and the
            rotation are already in these numbers, so the emitter decides nothing.
        zone: What the letters cover, outline included: the polygon balloons and captions
            paid to avoid, and which no face was allowed inside.
        fill: What the letters are filled with -- ink, or `none` for a hollow effect.
        stroke: What they are outlined in -- a paper halo, or ink for a hollow effect.
        stroke_width: The outline's width, in panel units.
        hollow: Whether it is an open effect: all outline, so the art shows through.
        label: The sound as it is read -- `Sound effect, from Bob: BLAM.` Left out of the
            JSON when unset.
    """

    id: str
    order: int
    text: str
    font_size: float
    glyphs: tuple[CoreGlyph, ...]
    zone: tuple[tuple[float, float], ...]
    fill: str
    stroke: str
    stroke_width: float
    source: str | None = None
    hollow: bool = False
    label: SvgText | None = None


class CoreCamera(CoreModel):
    """The camera's verdict for a panel, recorded (#72).

    Every position in a Core already follows from it, so nothing here is read to draw the
    panel; it says what framed it. The shot asked for and the angle are what a reader of
    the panel would name; the numbers are what the solver made of them.

    Attributes:
        shot: The shot asked for -- the tightest the camera would go.
        angle: The camera's height, which changed the headroom and nothing else.
        reference: The puppet the shot was composed on, by its name.
        scale: The one scale every actor is drawn at.
        headroom: The air above the reference actor's head, as a fraction of the panel's
            height.
        footroom: The room below the crop line, as a fraction of the panel's height.
        pullback: How far the camera retreated to fit the cast across the panel: 1.0 for
            the shot as asked, less when it was loosened.
    """

    shot: ShotType
    angle: CameraAngle
    reference: str
    scale: float
    headroom: float
    footroom: float
    pullback: float = 1.0


class PanelCore(CoreModel):
    """A fully resolved panel: numeric, named, and ready to emit.

    The middle tier, and the architectural idea of the project. Every position here is
    absolute and final, but **identifiers survive** -- which is exactly what separates
    this from SVG. You can read a Core document, see that `alice` sits at x=280 with her
    balloon top-left of her head, change one number, and emit it again.

    The approach is borrowed from Vega-Lite, which compiles a high-level grammar into a
    lower-level one before emitting anything drawable.

    Attributes:
        format_version: Bumped when the shape of this document changes incompatibly.
        width: Panel width in panel units.
        height: Panel height in panel units.
        actors: Resolved characters, back to front by `depth`, and at one depth left to
            right as staged. The SVG draws them back to front too, but breaks a tie at one
            depth by id (:func:`in_painters_order <scenet.emit.svg.in_painters_order>`).
        balloons: Resolved balloons, in reading order.
        captions: Resolved caption boxes, in reading order. Balloons and captions
            share one `order` sequence, since the reader takes them in one sequence.
        backdrop: Where the panel is, or None when it says nothing about that -- which
            is every panel written before the setting layer existed.
        exclusions: Areas the lettering kept clear of because something is drawn over
            them: on a page, the insets set into this panel, ringed by a gutter. The art
            under them is drawn as if they were not there. Left out of the JSON when
            empty, so a panel with no inset reads and writes exactly as it always did.
        outline: For a panel in a slanted tier, the shape of its border: four corners,
            clockwise from the top left, in panel units. The panel is drawn clipped to it,
            and its lettering stays inside it. Left out of the JSON for a rectangle.
        sfx: Sound effects, in script order. Left out of the JSON when there are none.
        fonts: The faces lettered in a font other than the shipped one, by face. A face
            not listed is the shipped family's. Left out of the JSON when every face is
            the shipped one.
        description: What the panel shows, in words, for a reader who cannot see it: the
            author's, or generated from what it holds. With the labels in `order`, it is
            what accessible output reads. Left out of the JSON when unset.
        figures: The figures a supplied picture draws, as its artwork contract declares
            them (#71), whether cast or not. Left out of the JSON when there are none, so
            every panel without them reads and writes as it always did.
        direction: Which way the panel is read, which is why its lettering is where it is
            (#68). Left out of the JSON for `ltr`, so every panel written before it reads
            and writes as it always did.
        camera: What framed the panel (#72), or None when a supplied picture draws the
            cast: the artist framed it, and the camera did not run. Left out of the JSON
            when None.

    Golden-file tests target this tier rather than the SVG, because it changes only when
    the layout genuinely changes. Diffing SVG text is brittle -- a reordered attribute or
    a different path-rounding convention produces an enormous diff that means nothing.

    Example:
        >>> from scenet import compile_source
        >>> core = compile_source("{cast: {a: {reference: alice}}}").core
        >>> core.width, core.height
        (1000.0, 1000.0)
        >>> core.actor("a").reference
        'alice'
        >>> core.to_json().splitlines()[0]
        '{'
    """

    format_version: int = CORE_FORMAT_VERSION
    width: float
    height: float
    actors: tuple[CoreActor, ...] = ()
    balloons: tuple[CoreBalloon, ...] = ()
    captions: tuple[CoreCaption, ...] = ()
    backdrop: CoreBackdrop | None = None
    exclusions: tuple[Box, ...] = ()
    outline: tuple[tuple[float, float], ...] | None = None
    fonts: dict[Face, CoreFont] = Field(default_factory=dict)
    sfx: tuple[CoreSfx, ...] = ()
    description: SvgText | None = None
    figures: tuple[CoreFigure, ...] = ()
    direction: Direction = Direction.LTR
    camera: CoreCamera | None = None

    @property
    def bounds(self) -> BBox:
        """The panel rectangle, origin at `(0, 0)`."""
        return BBox(0.0, 0.0, self.width, self.height)

    def face_exclusions(self) -> tuple[Disc, ...]:
        """Every face lettering kept clear of: the actors', then the figures'.

        Example:
            >>> from scenet import compile_source
            >>> len(compile_source("{cast: {a: {reference: alice}}}").core.face_exclusions())
            1
        """
        return (
            *(actor.face_exclusion for actor in self.actors),
            *(figure.face_exclusion for figure in self.figures),
        )

    def speaker(self, actor_id: str) -> Speaking:
        """Who speaks a balloon, wherever they are drawn: a puppet, or a figure a picture draws.

        Args:
            actor_id: The id a balloon names as its `speaker`.

        Returns:
            Their face, and where a tail to them aims: the mouth, or the face's centre
            when there is none.

        Raises:
            KeyError: Nobody in this panel plays that part.
        """
        for actor in self.actors:
            if actor.id == actor_id:
                face = actor.face_exclusion
                return Speaking(face, actor.anchors.get("mouth", (face.cx, face.cy)))
        for figure in self.figures:
            if figure.actor == actor_id:
                face = figure.face_exclusion
                return Speaking(face, figure.mouth or (face.cx, face.cy))
        raise KeyError(f"nobody in panel plays '{actor_id}'")

    def actor(self, actor_id: str) -> CoreActor:
        """Look up one actor by id.

        Args:
            actor_id: The id used in the panel source.

        Returns:
            That actor.

        Raises:
            KeyError: No actor in this panel has that id.
        """
        for actor in self.actors:
            if actor.id == actor_id:
                return actor
        raise KeyError(f"no actor '{actor_id}' in panel")

    def to_json(self) -> str:
        """Serialise deterministically.

        Keys are sorted and floats already rounded at construction, so the same input
        yields byte-identical output on any platform. A trailing newline keeps the
        file well-formed for line-oriented tools like git diff.
        """
        payload: Any = self.model_dump(mode="json")
        _drop_unused(
            payload,
            exclusions=(),
            outline=None,
            fonts={},
            sfx=(),
            description=None,
            figures=(),
            direction=Direction.LTR,
            camera=None,
        )
        for actor in payload["actors"]:
            _drop_unused(actor, joints={}, features={}, looking_at=None)
        for figure in payload.get("figures", []):
            _drop_unused(figure, actor=None, mouth=None, body=())
        for lettered in (*payload["balloons"], *payload["captions"]):
            _drop_unused(lettered, runs=(), label=None)
        if payload.get("backdrop") is not None:
            _drop_unused(payload["backdrop"], horizon=None, image=None, place=None, time=None)
            if payload["backdrop"].get("image") is not None:
                _drop_unused(payload["backdrop"]["image"], keep_out=())
        for effect in payload.get("sfx", []):
            _drop_unused(effect, label=None)
        for balloon in payload["balloons"]:
            _drop_unused(balloon, off_panel=None)
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Self:
        """Read a Core document back in.

        The inverse of :meth:`to_json <scenet.core.PanelCore.to_json>`, and the reason Panel
        Core is a real format rather than a private data structure: a layout can be
        exported, adjusted by hand or by another tool, and read back for emission.

        Args:
            text: A Core document.

        Returns:
            The parsed panel.

        Raises:
            pydantic.ValidationError: The document is not a valid Core panel.
            json.JSONDecodeError: The text is not JSON at all.
        """
        return cls.model_validate(json.loads(text))


def _drop_unused(payload: dict[str, Any], **unused: object) -> None:
    """Leave out of a document each field still at the value that means "not used".

    For fields added after the format was published: a document that does not use one
    is then byte-identical to what it was before the field existed, which is what golden
    files and anyone diffing two builds rely on. Done here, not with pydantic's
    `exclude_if`, which needs pydantic 2.12 while this package accepts 2.9.
    """
    for name, value in unused.items():
        if name in payload and payload[name] == (
            list(value) if isinstance(value, tuple) else value
        ):
            del payload[name]


class CoreFrame(CoreModel):
    """Where one panel sits on a page.

    Attributes:
        panel: The panel's name, as `panels:` gives it. Its own Panel Core is a separate
            document, compiled at exactly this width and height.
        x: Left edge, in page units.
        y: Top edge, in page units.
        width: Frame width, which is the panel's width.
        height: Frame height, which is the panel's height.
        inset_of: For an inset, the panel it is set into. Left out of the JSON otherwise.
        clearance: For an inset, the area it covers with its ring of white, in page
            units: painted white under it, and kept clear by its parent's lettering. Left
            out of the JSON otherwise.
        outline: For a panel in a slanted tier, its four corners in page units, clockwise
            from the top left; the frame is their bounding box. Left out of the JSON for a
            rectangle.
    """

    panel: str
    x: float
    y: float
    width: float
    height: float
    inset_of: str | None = None
    clearance: Box | None = None
    outline: tuple[tuple[float, float], ...] | None = None


class PageCore(CoreModel):
    r"""A fully resolved page: where every panel's frame is.

    The page tier of the same idea as :class:`PanelCore <scenet.core.PanelCore>`. It holds
    the frames and nothing drawn: each panel's contents are its own Panel Core, compiled
    at its frame's size, so a page adds no layout decision to a panel and a panel's Core
    reads the same whether or not it is on a page.

    Attributes:
        format_version: Bumped when the shape of this document changes incompatibly.
        width: Page width, in page units.
        height: Page height.
        lettering_height: The height every panel on the page took its type size from, in
            place of its own -- so that a short panel and a tall one letter alike.
        frames: One per panel, in reading order: tier by tier, left to right, or right to
            left for a page read that way.
        direction: Which way the page is read (#68). Left out of the JSON for `ltr`, so every
            page written before it reads and writes as it always did.

    Example:
        >>> from scenet import compile_book
        >>> book = compile_book(
        ...     "cast: {a: {reference: alice}}\n"
        ...     "pages: [{tiers: [{panels: [one]}]}]\npanels: {one: {}}"
        ... )
        >>> [(f.panel, f.width) for f in book.pages[0].frames]
        [('one', 1800.0)]
    """

    format_version: int = CORE_FORMAT_VERSION
    width: float
    height: float
    lettering_height: float
    frames: tuple[CoreFrame, ...] = ()
    direction: Direction = Direction.LTR

    def to_json(self) -> str:
        """Serialise deterministically, exactly as a Panel Core is."""
        payload: Any = self.model_dump(mode="json")
        _drop_unused(payload, direction=Direction.LTR)
        for frame in payload["frames"]:
            _drop_unused(frame, inset_of=None, clearance=None, outline=None)
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Self:
        """Read a Page Core back in.

        Args:
            text: A Page Core document.

        Returns:
            The parsed page.

        Raises:
            pydantic.ValidationError: The document is not a valid Page Core.
            json.JSONDecodeError: The text is not JSON at all.
        """
        return cls.model_validate(json.loads(text))


def point_pair(point: Point) -> tuple[float, float]:
    """Convert a point to the rounded `(x, y)` pair a Core document stores."""
    return point.as_tuple()


def vector_pair(vector: Vector) -> tuple[float, float]:
    """Convert a vector to the rounded `(dx, dy)` pair a Core document stores."""
    return vector.as_tuple()


def round_pairs(points: tuple[Point, ...]) -> tuple[tuple[float, float], ...]:
    """Convert a sequence of points -- a hull, typically -- to rounded pairs."""
    return tuple(point.as_tuple() for point in points)


__all__ = [
    "CORE_FORMAT_VERSION",
    "PRECISION",
    "Blob",
    "Box",
    "Capsule",
    "CoreActor",
    "CoreAtmosphere",
    "CoreBackdrop",
    "CoreBalloon",
    "CoreCamera",
    "CoreCaption",
    "CoreFigure",
    "CoreFont",
    "CoreFrame",
    "CoreGlyph",
    "CoreMass",
    "CoreRun",
    "CoreSfx",
    "CoreStreak",
    "CoreVeil",
    "Disc",
    "FaceDisc",
    "FaceMark",
    "FaceStroke",
    "PageCore",
    "PanelCore",
    "Speaking",
    "Tail",
    "Transform",
    "point_pair",
    "round_pairs",
    "vector_pair",
]
