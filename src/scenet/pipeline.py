"""The compiler: source through IR to Panel Core.

Each stage is separable and independently testable, which is the point of having
tiers at all. The frontend never computes a coordinate, the solver never touches
artwork, and the emitter never makes a layout decision.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from shapely.geometry import Point, Polygon

from scenet.assets.artwork import LoadedContract, load_contract, pictureless, undrawn
from scenet.assets.contract import PuppetLibrary, default_library
from scenet.assets.emanata import SINGULAR, build_emanata
from scenet.assets.face import ResolvedDisc, ResolvedStroke, build_face
from scenet.assets.kinematics import ResolvedPuppet, resolve
from scenet.core import (
    Blob,
    Box,
    Capsule,
    CoreActor,
    CoreAtmosphere,
    CoreBackdrop,
    CoreBalloon,
    CoreCamera,
    CoreCaption,
    CoreFigure,
    CoreFont,
    CoreFrame,
    CoreGlyph,
    CoreImage,
    CoreMass,
    CoreRun,
    CoreSfx,
    CoreStreak,
    CoreVeil,
    Disc,
    FaceDisc,
    FaceMark,
    FaceStroke,
    PageCore,
    PanelCore,
    Tail,
    Transform,
    point_pair,
    round_pairs,
    vector_pair,
)
from scenet.errors import PanelSyntaxError, RuleViolationError, ScenetError
from scenet.frontends.script_front import load_script, parse_script_document
from scenet.frontends.yaml_front import (
    SceneDocument,
    load_panel,
    load_scene,
    load_scene_document,
    parse_panel,
    parse_scene_document,
)
from scenet.geom import BBox, Vector, rounded
from scenet.geom import Point as GeomPoint
from scenet.images import SuppliedImage, load_image
from scenet.ir import Face, Fit, Mark, PanelIR, PanelSpec, SayEvent, SettingSpec, Side
from scenet.lettering import Lettering, typeface_for
from scenet.paths import Folder
from scenet.places import place_of
from scenet.solve.backdrop import ResolvedBackdrop, solve_backdrop
from scenet.solve.balloons import place_script
from scenet.solve.camera import CameraSolution
from scenet.solve.describe import describe, labels
from scenet.solve.figures import PlacedPicture, place_figures
from scenet.solve.page import Frame, lettering_height, resolve_frames
from scenet.solve.sfx import PlacedEffect
from scenet.solve.speakers import speaker_of
from scenet.solve.staging import Placement, solve_staging
from scenet.solve.text import SHIPPED_FACES, FontMetrics, TextBlock, Typeface

#: What each kind of compile note is called: a stable name, as a check's rule has one, by
#: which a gallery entry's `notes:` declares it (#240) while the sentence stays free to be
#: reworded. One name per sentence; `docs/howto/debug_a_layout.md` explains each.
CompileNoteRule = Literal[
    "camera-retreated",
    "curved-tail",
    "cropped-mouth",
    "cropped-marks",
    "inset-covers-face",
    "slant-cuts-face",
    "italic-stand-in",
    "bold-italic-stand-in",
]


@dataclass(frozen=True, slots=True)
class CompileNote:
    """Something the compiler decided that the source did not literally ask for.

    Attributes:
        rule: What kind of decision it was, by its stable name.
        message: The sentence that says so, as
            :attr:`CompileResult.notes <scenet.pipeline.CompileResult.notes>` gives it.
    """

    rule: CompileNoteRule
    message: str


@dataclass(frozen=True, slots=True)
class CompileResult:
    """The compiled panel, with the intermediate results kept for inspection.

    Diagnostics -- notably whether the camera had to retreat to fit the cast -- are
    part of the result rather than log output, so tooling can surface them.
    """

    core: PanelCore
    #: The framing the camera chose, or None for a panel whose cast a supplied picture
    #: draws (#71): the artist framed it, and the camera does not run.
    camera: CameraSolution | None
    placements: tuple[Placement, ...]
    posed: dict[str, ResolvedPuppet]
    #: The fonts the lettering was measured in, other than the shipped family's, by the
    #: digest `PanelCore.fonts` names them by. Hand them to the renderer.
    fonts: dict[str, FontMetrics] = field(default_factory=dict)
    #: The supplied pictures it was drawn over, by the digest `PanelCore` names them by:
    #: their bytes, for a renderer asked to embed them rather than link them.
    images: dict[str, bytes] = field(default_factory=dict)
    #: Faces the document named no file for, and what was used instead -- reported in
    #: `notes` only when something was actually set in one.
    lettering_notes: tuple[CompileNote, ...] = ()

    @property
    def notes(self) -> tuple[str, ...]:
        """Human-readable diagnostics about how this panel was compiled.

        Returns:
            Zero or more sentences describing decisions the compiler had to make that
            were not literally what the source asked for -- a camera that retreated to
            fit the cast, a balloon tail that had to bend around a face, a mark drawn
            partly outside the panel. Each is a :class:`CompileNote`'s message, in the
            order of :attr:`compile_notes`, which also names what kind it is.

        These are returned rather than logged so that tooling can put them in front of
        the person who wrote the panel. A camera that silently retreats leaves you with
        a panel that is quietly not the shot you asked for, which you would eventually
        notice and have no way to explain.

        Example:
            >>> from scenet import compile_source
            >>> crowded = compile_source(
            ...     "{panel: {size: [600.0, 400.0]}, camera: {shot: close_up},"
            ...     " cast: {a: {reference: alice}, b: {reference: bob}},"
            ...     " staging: [a left_of b]}"
            ... )
            >>> any("camera retreated" in note for note in crowded.notes)
            True
        """
        return tuple(note.message for note in self.compile_notes)

    @property
    def compile_notes(self) -> tuple[CompileNote, ...]:
        """The notes, each with the name of what kind it is.

        Returns:
            The same notes as :attr:`notes`, in the same order, each a sentence and a
            :data:`CompileNoteRule <scenet.pipeline.CompileNoteRule>` -- the name a
            gallery entry declares it by, which stays when the sentence is reworded.

        Example:
            >>> from scenet import compile_source
            >>> crowded = compile_source(
            ...     "{panel: {size: [600.0, 400.0]}, camera: {shot: close_up},"
            ...     " cast: {a: {reference: alice}, b: {reference: bob}},"
            ...     " staging: [a left_of b]}"
            ... )
            >>> [note.rule for note in crowded.compile_notes]
            ['camera-retreated']
        """
        notes: list[CompileNote] = []
        if self.camera is not None and self.camera.was_pulled_back:
            notes.append(
                CompileNote(
                    "camera-retreated",
                    f"camera retreated to {self.camera.pullback:.0%} of the requested "
                    f"'{self.camera.shot.value}' framing so the cast would fit across the panel",
                )
            )
        for balloon in self.core.balloons:
            if balloon.tail.is_curved:
                notes.append(
                    CompileNote(
                        "curved-tail", f"balloon {balloon.id} needed a curved tail to clear a face"
                    )
                )
        notes.extend(_cropped_mouths(self.core))
        # The camera frames by body landmarks and makes no room for emanata, which is
        # what keeps them from ever moving anybody. The cost is that a tight shot can
        # crop them, so say so: a mark that silently vanished is the same complaint as
        # a camera that silently retreated.
        for actor in self.core.actors:
            for mark in actor.marks:
                if _cropped(self.core, actor, mark):
                    notes.append(
                        CompileNote(
                            "cropped-marks",
                            f"{actor.id}'s {mark.value} run off the panel at this framing; "
                            "the camera makes no room for marks, so a looser shot shows more",
                        )
                    )
        # An inset is drawn over the art, which does not move for it, so it can cover a
        # face as easily as a sky. The lettering keeps clear; the face cannot.
        for who, disc in _named_faces(self.core):
            face = disc.as_circle()
            if any(area.as_bbox().intersects_circle(face) for area in self.core.exclusions):
                notes.append(
                    CompileNote(
                        "inset-covers-face",
                        f"an inset covers {who}'s face; it is drawn over the art, which does "
                        "not move for it, so put the inset in another corner or reframe the "
                        "panel",
                    )
                )
        # A slanted edge crops the art like a margin, and the camera does not know it is
        # there. Say so when it runs through a face.
        if self.core.outline is not None:
            edge = Polygon(self.core.outline)
            for who, face in _named_faces(self.core):
                if not edge.contains(Point(face.cx, face.cy).buffer(face.r)):
                    notes.append(
                        CompileNote(
                            "slant-cuts-face",
                            f"the slanted edge of this panel cuts across {who}'s face; "
                            "lean the tier less, or frame the shot so the face is clear of it",
                        )
                    )
        notes.extend(self.lettering_notes)
        return tuple(notes)


def _cropped_mouths(core: PanelCore) -> list[CompileNote]:
    """A note for each balloon whose speaker's mouth a picture's fit cropped out of the panel.

    A `cover` fit overhangs, and can crop a figure's mouth away. The tail then stops on the
    frame, aimed at it: correct, and worth knowing about.
    """
    notes: list[CompileNote] = []
    mouths = {figure.actor: figure.mouth for figure in core.figures if figure.actor}
    for balloon in core.balloons:
        mouth = mouths.get(balloon.speaker)
        if mouth is not None and not (0 <= mouth[0] <= core.width and 0 <= mouth[1] <= core.height):
            notes.append(
                CompileNote(
                    "cropped-mouth",
                    f"{balloon.speaker}'s mouth is outside the panel, cropped by the picture's "
                    f"fit, so balloon {balloon.id}'s tail stops on the frame; `fit: contain` "
                    "shows the whole picture",
                )
            )
    return notes


def _named_faces(core: PanelCore) -> list[tuple[str, Disc]]:
    """Every face in a panel, with whose it is: actors by id, figures by part or name."""
    return [
        *((actor.id, actor.face_exclusion) for actor in core.actors),
        *((figure.actor or figure.figure, figure.face_exclusion) for figure in core.figures),
    ]


def _cropped(core: PanelCore, actor: CoreActor, mark: Mark) -> bool:
    """Whether any part of one of an actor's marks is drawn outside the panel."""
    prefix = f"{SINGULAR[mark]}_"
    for drawn in actor.emanata:
        if not drawn.id.startswith(prefix):
            continue
        if isinstance(drawn, FaceDisc):
            (cx, cy), r = drawn.centre, drawn.radius
            extent = [(cx - r, cy - r), (cx + r, cy + r)]
        else:
            extent = list(drawn.points)
        if any(not (0 <= x <= core.width and 0 <= y <= core.height) for x, y in extent):
            return True
    return False


#: Which way to look for a voice from each side of the frame.
_TOWARDS = {
    Side.LEFT: Vector(-1.0, 0.0),
    Side.RIGHT: Vector(1.0, 0.0),
    Side.TOP: Vector(0.0, -1.0),
    Side.BOTTOM: Vector(0.0, 1.0),
}


def _sides_looked_to(panel: PanelIR, placements: Sequence[Placement]) -> dict[str, Side]:
    """The side of the frame each off-panel speaker somebody looks at is heard from.

    The side the script names, or else the one the first figure looking at them faces --
    so a voice with no side named comes from where the figure answering it looks, rather
    than from wherever its balloon happens to go.
    """
    heard = panel.off_panel_speakers()
    facing = {placement.actor_id: placement.facing_right for placement in placements}
    sides: dict[str, Side] = {}
    for actor, target in panel.gaze_targets().items():
        if target in heard and target not in sides:
            named = heard[target]
            sides[target] = named or (Side.RIGHT if facing[actor] else Side.LEFT)
    return sides


def _gaze_aims(
    panel: PanelIR,
    posed: dict[str, ResolvedPuppet],
    origins: dict[str, str],
    heard: Mapping[str, Side] | None = None,
) -> dict[str, Vector]:
    """Unit vectors from each looking character's eyes to what they are looking at.

    `looking_at` has always turned a figure toward its target and made the space in
    front of them expensive for a balloon. What it never did was show up on the face,
    because the only gaze vector available was the head's forward direction -- which,
    with no pose rotating the head, is the facing direction and nothing more. This is
    the real thing, and it is what the pupils follow.

    Args:
        panel: The validated panel, for its `looking_at` relations.
        posed: Every actor, already placed. Both ends of a gaze must be resolved
            before the vector between them exists, which is why this runs here.
        origins: Actor id to the anchor its puppet declares as the gaze origin.
        heard: Off-panel speaker to the side of the frame they are heard from. Looking
            at one is looking straight out of the frame on that side.

    Returns:
        Actor id to unit aim vector, for looking actors only.
    """
    aims: dict[str, Vector] = {}
    for actor, target in panel.gaze_targets().items():
        if target not in posed:
            side = (heard or {}).get(target)
            if side is not None:
                aims[actor] = _TOWARDS[side]
            continue
        looker, looked_at = posed[actor], posed[target]
        eyes = looker.anchors.get(origins[actor], looker.face.centre)
        towards = looked_at.face.centre
        aim = Vector(towards.x - eyes.x, towards.y - eyes.y)
        if aim.length:
            aims[actor] = aim.normalised()
    return aims


def _core_mark(mark: ResolvedStroke | ResolvedDisc) -> FaceMark:
    """Reduce one resolved mark, of a face or of its emanata, to its Core twin."""
    if isinstance(mark, ResolvedDisc):
        return FaceDisc(
            id=mark.id,
            centre=point_pair(mark.centre),
            radius=rounded(mark.radius),
            filled=mark.filled,
            width=rounded(mark.width),
        )
    return FaceStroke(
        id=mark.id,
        points=round_pairs(mark.points),
        width=rounded(mark.width),
        closed=mark.closed,
    )


def _core_sfx(effect: PlacedEffect) -> CoreSfx:
    """Reduce one placed sound effect to its Core twin, rounding as every tier boundary does."""
    zone = effect.zone.exterior.coords[:-1]
    return CoreSfx(
        id=effect.id,
        order=effect.order,
        text=effect.text,
        source=effect.source,
        font_size=rounded(effect.font_size),
        glyphs=tuple(
            CoreGlyph(
                char=glyph.character, origin=point_pair(glyph.origin), angle=rounded(glyph.angle)
            )
            for glyph in effect.glyphs
        ),
        zone=tuple((rounded(x), rounded(y)) for x, y in zone),
        fill=effect.fill,
        stroke=effect.stroke,
        stroke_width=rounded(effect.stroke_width),
        hollow=effect.hollow,
    )


def _core_runs(block: TextBlock, base: Face) -> tuple[tuple[CoreRun, ...], ...]:
    """A block's runs as Panel Core records them: only when some line leaves its face.

    A balloon or caption with no emphasis records none, so its Core is byte-identical to
    what it was before emphasis existed, and the emitter draws each line whole.
    """
    if all(face is base for line in block.runs for _, face in line):
        return ()
    return tuple(tuple(CoreRun(text=text, face=face) for text, face in line) for line in block.runs)


def _declared_faces(family: Typeface) -> dict[Face, FontMetrics]:
    """The faces of a family that are not the shipped ones, which is what Core records."""
    declared: dict[Face, FontMetrics] = {}
    for face in Face:
        chosen = getattr(family, face.value)
        if chosen is not None and chosen.path != SHIPPED_FACES[face]:
            declared[face] = chosen
    return declared


def _stand_in_notes(
    core: PanelCore, lettering: Lettering, family: Typeface
) -> tuple[CompileNote, ...]:
    """Say so when lettering was set in a face standing in for one the document did not name."""
    notes: list[CompileNote] = []
    if lettering.stands_in(Face.ITALIC) and any(caption.italic for caption in core.captions):
        regular = family.face(Face.REGULAR)
        notes.append(
            CompileNote(
                "italic-stand-in",
                "no italic face is named in lettering.font, so italic captions are set in "
                f"{regular.family} {regular.style}; name one as `italic:`",
            )
        )
    stressed = any(
        run.face is Face.BOLD_ITALIC
        for item in (*core.balloons, *core.captions)
        for line in item.runs
        for run in line
    )
    if lettering.stands_in(Face.BOLD_ITALIC) and stressed:
        used = family.face(Face.BOLD_ITALIC)
        notes.append(
            CompileNote(
                "bold-italic-stand-in",
                "no bold italic face is named in lettering.font, so emphasis is set in "
                f"{used.family} {used.style}; name one as `bold_italic:`",
            )
        )
    return tuple(notes)


def _folder(source: Path | None, base: Folder | None) -> Folder | None:
    """The folder files a document names are read from: given, or the document's own."""
    if base is not None:
        return base
    return source.parent if source is not None else None


#: A fit, as SVG's `preserveAspectRatio` says it.
PRESERVE_ASPECT_RATIO: dict[Fit, Literal["xMidYMid slice", "xMidYMid meet"]] = {
    Fit.COVER: "xMidYMid slice",
    Fit.CONTAIN: "xMidYMid meet",
}


def _core_backdrop(
    backdrop: ResolvedBackdrop | None,
    image: SuppliedImage | None,
    setting: SettingSpec,
    keep_out: Sequence[Sequence[GeomPoint]] = (),
) -> CoreBackdrop | None:
    """Reduce a resolved backdrop to its serialisable Core twin.

    Rounding happens here, as it does for every other tier boundary, so that a Core
    document is byte-identical across platforms whose float formatting differs in the
    last digit. The picture's facts -- its path, type and digest -- join the rectangle
    the solver placed it in here, since the solver was told nothing but its size. The
    place and the hour are the setting's, except over a picture, which holds its own.
    """
    if backdrop is None:
        return None

    air = backdrop.atmosphere
    placed = backdrop.image
    return CoreBackdrop(
        horizon=None if backdrop.horizon is None else rounded(backdrop.horizon),
        image=None
        if placed is None or image is None
        else CoreImage(
            href=image.href,
            media_type=image.media_type,
            sha256=image.sha256,
            pixels=placed.pixels,
            fit=placed.fit,
            preserve_aspect_ratio=PRESERVE_ASPECT_RATIO[placed.fit],
            box=Box.of(placed.box),
            keep_out=tuple(round_pairs(tuple(region)) for region in keep_out),
        ),
        seed=backdrop.seed,
        place=None if image is not None else place_of(setting.masses),
        time=None if image is not None else setting.time,
        masses=tuple(
            CoreMass(
                id=mass.id,
                kind=mass.kind,
                plane=mass.plane,
                depth=mass.depth,
                tone=mass.tone,
                polygon=round_pairs(mass.polygon),
                colour=mass.colour,
            )
            for mass in backdrop.masses
        ),
        atmosphere=None
        if air is None
        else CoreAtmosphere(
            time=air.time,
            weather=air.weather,
            tone=air.tone,
            veil=None
            if air.veil is None
            else CoreVeil(
                tone=air.veil.tone,
                opacity=air.veil.opacity,
                frequency=air.veil.frequency,
                octaves=air.veil.octaves,
                seed=air.veil.seed,
                colour=air.veil.colour,
            ),
            streaks=tuple(
                CoreStreak(start=point_pair(start), end=point_pair(end))
                for start, end in air.streaks
            ),
            flecks=tuple(Disc.of(fleck) for fleck in air.flecks),
            streak_width=rounded(air.streak_width),
            fall_tone=air.fall_tone,
            colour=air.colour,
            fall_colour=air.fall_colour,
        ),
    )


def compile_ir(
    panel: PanelIR,
    *,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
    base: Folder | None = None,
    lettering_height: float | None = None,
    exclusions: Sequence[BBox] = (),
    outline: Sequence[tuple[float, float]] | None = None,
) -> CompileResult:
    """Compile validated IR into Panel Core.

    Args:
        panel: The validated panel.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: A regular face to measure lettering against, in place of the one the
            panel declares or the shipped one.
        base: The folder the panel's document is in, which the font files and the
            picture it declares are read from -- or those files themselves, by the
            path it writes. Without one, a panel that names a file is refused.
        lettering_height: The height type sizes are a fraction of, instead of the panel's
            own. A page passes the same value to every panel on it; a panel compiled on
            its own leaves it out. A panel that sets `lettering.size` letters at that size
            instead, and this is not consulted.
        exclusions: Areas no balloon or caption may touch, in panel units, because
            something is drawn over them -- on a page, the insets set into this panel.
            Nothing else moves for them: the art under an inset is drawn as usual.
        outline: The panel's border when it is not a rectangle -- on a page, a panel in a
            slanted tier -- in panel units. The panel is staged and framed in its bounding
            box as usual, and cropped to this; lettering stays inside it, a margin in.

    Returns:
        The compiled panel, with the fonts it was lettered in.

    Raises:
        PanelSyntaxError: Rule `font-file`, for a declared font that cannot be read,
            `image-file`, for a picture, `artwork-contract`, for the contract beside a
            picture whose figures the panel casts, or `unknown-figure`, for a figure the
            picture does not draw.
    """
    library = library or default_library()
    # Read first: a font that cannot be read is the author's to fix, and is better said
    # before the solver spends anything on a panel it could not letter.
    lettering = typeface_for(panel.lettering, base)
    image = (
        load_image(panel.setting.image, base, loc=("setting", "image"))
        if panel.setting.image is not None
        else None
    )
    contract = _contract_for(panel, image, base)
    family = lettering.typeface
    if metrics is not None:
        family = replace(family, regular=metrics)
    # A cast the picture draws was framed and staged by the artist: the camera and staging
    # do not run, and nobody is posed.
    camera: CameraSolution | None
    if panel.drawn_by_its_picture:
        placements, camera = (), None
    else:
        placements, camera = solve_staging(panel, library)

    posed = {
        placement.actor_id: resolve(
            library.get(placement.reference),
            pose=placement.pose,
            expression=placement.expression,
            facing_right=placement.facing_right,
            scale=placement.scale,
            origin=placement.origin,
        )
        for placement in placements
    }
    # Aiming has to happen here rather than in `resolve`, because where a character is
    # looking is a fact about two actors and is not known until both are placed. It is
    # still nothing to do with the solver: no constraint reads it, and it changes no
    # position -- it only turns the pupils.
    specs = {placement.actor_id: library.get(placement.reference) for placement in placements}
    heard = _sides_looked_to(panel, placements)
    aims = _gaze_aims(
        panel, posed, {actor: spec.gaze.origin for actor, spec in specs.items()}, heard
    )
    faces = {
        actor: build_face(
            posed[actor], spec.expression_states(posed[actor].expression), aims.get(actor)
        )
        if spec.expressions
        else ()
        for actor, spec in specs.items()
    }
    # Emanata are drawn outside the head, so unlike the face they matter to placement:
    # each one's zone is a soft cost for every balloon and caption. They are still
    # resolved here, after staging, and never reach the hull -- marks move nobody.
    emanata = {actor: build_emanata(posed[actor], panel.cast[actor].marks) for actor in posed}

    # The backdrop is resolved against the whole panel, not the margined frame: artwork
    # bleeds to the edge and only lettering is kept inside a margin. It runs after
    # staging, which is what knows how deep the cast goes, and before placement, which
    # reads the masses as a soft cost.
    backdrop = solve_backdrop(
        panel.setting,
        BBox(0.0, 0.0, panel.panel.width, panel.panel.height),
        frontmost_actor=max((placement.depth for placement in placements), default=0),
        pixels=None if image is None else (image.width, image.height),
        palette=panel.palette,
    )

    picture = (
        place_figures(contract.contract, backdrop.image)
        if contract is not None and backdrop is not None and backdrop.image is not None
        else PlacedPicture()
    )
    playing = {figure: actor for actor, figure in panel.figures().items()}
    speakers = {actor: speaker_of(puppet) for actor, puppet in posed.items()}
    speakers.update(
        (playing[figure.name], figure.speaker)
        for figure in picture.figures
        if figure.name in playing
    )

    frame = BBox(
        panel.panel.margin,
        panel.panel.margin,
        panel.panel.width - 2 * panel.panel.margin,
        panel.panel.height - 2 * panel.panel.margin,
    )
    # A line from off panel with no side named is heard from where whoever answers it
    # looks; with nobody looking, the solver takes the side nearer its balloon.
    script = tuple(
        event.model_copy(update={"off_panel": heard[event.by]})
        if isinstance(event, SayEvent) and event.off_panel is True and event.by in heard
        else event
        for event in panel.script
    )
    layout = place_script(
        script,
        speakers,
        frame,
        bystanders=[figure.speaker for figure in picture.figures if figure.name not in playing],
        keep_out=picture.keep_out,
        typeface=family,
        type_size=panel.lettering.size,
        lettering_height=lettering_height,
        backdrop=backdrop,
        emanata={actor: drawn.zones for actor, drawn in emanata.items() if drawn.zones},
        exclusions=exclusions,
        inside=_margined(outline, panel.panel.margin) if outline is not None else None,
        # The frame itself, which an off-panel speaker's tail ends on: lettering keeps
        # inside the margin, a pointer to somebody outside the panel does not.
        bounds=BBox(0.0, 0.0, panel.panel.width, panel.panel.height),
        outline=outline,
        direction=panel.direction,
        palette=panel.palette,
    )

    declared = _declared_faces(family)
    # The words it is read in, built here so the emitter copies them. Where a figure is
    # comes from its face, rounded as Panel Core records it; each label is indexed by
    # `order`, which is the script index, sound effects included.
    width = rounded(panel.panel.width)
    where = {
        placement.actor_id: rounded(posed[placement.actor_id].face.cx) for placement in placements
    }
    where.update(
        (playing[figure.name], rounded(figure.face.cx))
        for figure in picture.figures
        if figure.name in playing
    )
    said = labels(script)
    looked_at = panel.gaze_targets()
    core = PanelCore(
        width=width,
        height=rounded(panel.panel.height),
        actors=tuple(
            CoreActor(
                id=placement.actor_id,
                reference=placement.reference,
                pose=placement.pose,
                expression=placement.expression,
                transform=Transform(
                    x=rounded(placement.x),
                    y=rounded(placement.y),
                    scale=rounded(placement.scale),
                    mirrored=not placement.facing_right,
                ),
                anchors={
                    name: point_pair(point)
                    for name, point in sorted(posed[placement.actor_id].anchors.items())
                },
                face_exclusion=Disc.of(posed[placement.actor_id].face),
                gaze=vector_pair(posed[placement.actor_id].gaze),
                gaze_aim=(
                    vector_pair(aims[placement.actor_id]) if placement.actor_id in aims else None
                ),
                face_marks=tuple(_core_mark(mark) for mark in faces[placement.actor_id]),
                marks=panel.cast[placement.actor_id].marks,
                emanata=tuple(_core_mark(mark) for mark in emanata[placement.actor_id].marks),
                emanata_zones=tuple(
                    round_pairs(zone) for zone in emanata[placement.actor_id].zones
                ),
                hull=round_pairs(posed[placement.actor_id].hull),
                capsules=tuple(
                    Capsule(
                        start=point_pair(capsule.start),
                        end=point_pair(capsule.end),
                        width=rounded(capsule.width),
                    )
                    for capsule in posed[placement.actor_id].capsules
                ),
                blobs=tuple(
                    Blob(centre=point_pair(blob.centre), radius=rounded(blob.radius))
                    for blob in posed[placement.actor_id].blobs
                ),
                depth=placement.depth,
                joints={
                    name: point_pair(point)
                    for name, point in sorted(posed[placement.actor_id].joints.items())
                },
                features={
                    feature.value: point_pair(resolved.centre)
                    for feature, resolved in sorted(posed[placement.actor_id].features.items())
                },
                looking_at=looked_at.get(placement.actor_id),
            )
            for placement in placements
        ),
        balloons=tuple(
            CoreBalloon(
                id=balloon.id,
                speaker=balloon.speaker,
                order=balloon.order,
                kind=balloon.kind,
                box=Box.of(balloon.box),
                lines=balloon.block.lines,
                font_size=rounded(balloon.block.font_size),
                line_height=rounded(balloon.block.line_height),
                tail=Tail(
                    start=point_pair(balloon.tail.start),
                    end=point_pair(balloon.tail.end),
                    control=(point_pair(balloon.tail.control) if balloon.tail.control else None),
                ),
                runs=_core_runs(balloon.block, Face.REGULAR),
                off_panel=balloon.off_panel,
                label=said[balloon.order],
            )
            for balloon in layout.balloons
        ),
        captions=tuple(
            CoreCaption(
                id=caption.id,
                order=caption.order,
                kind=caption.kind,
                box=Box.of(caption.box),
                lines=caption.block.lines,
                font_size=rounded(caption.block.font_size),
                line_height=rounded(caption.block.line_height),
                italic=caption.kind.is_italic,
                fill=caption.fill,
                ink=caption.ink,
                speaker=caption.speaker,
                colour=caption.colour,
                runs=_core_runs(
                    caption.block, Face.ITALIC if caption.kind.is_italic else Face.REGULAR
                ),
                label=said[caption.order],
            )
            for caption in layout.captions
        ),
        backdrop=_core_backdrop(backdrop, image, panel.setting, picture.keep_out),
        figures=tuple(
            CoreFigure(
                figure=figure.name,
                actor=playing.get(figure.name),
                face_exclusion=Disc.of(figure.face),
                mouth=point_pair(figure.mouth) if figure.mouth is not None else None,
                body=round_pairs(figure.body),
            )
            for figure in picture.figures
        ),
        exclusions=tuple(Box.of(area) for area in exclusions),
        outline=tuple(outline) if outline is not None else None,
        sfx=tuple(
            _core_sfx(effect).model_copy(update={"label": said[effect.order]})
            for effect in layout.effects
        ),
        fonts={
            face: CoreFont(family=font.family, style=font.style, sha256=font.sha256)
            for face, font in declared.items()
        },
        description=describe(panel, where, width),
        direction=panel.direction,
        palette=panel.palette,
        camera=None
        if camera is None
        else CoreCamera(
            shot=camera.shot,
            angle=panel.camera.angle,
            reference=camera.reference,
            scale=rounded(camera.scale),
            headroom=rounded(camera.headroom),
            footroom=rounded(camera.footroom),
            pullback=rounded(camera.pullback),
        ),
    )
    return CompileResult(
        core=core,
        camera=camera,
        placements=placements,
        posed=posed,
        fonts={font.sha256: font for font in declared.values()},
        images={image.sha256: image.data} if image is not None else {},
        lettering_notes=_stand_in_notes(core, lettering, family),
    )


def _contract_for(
    panel: PanelIR, image: SuppliedImage | None, base: Folder | None
) -> LoadedContract | None:
    """The artwork contract of the picture a cast of figures is drawn by, held to the cast.

    Read only when the cast names a figure, so a file beside a picture changes nothing
    on its own. Faults are raised exactly as `scenet check` reports them.

    Raises:
        PanelSyntaxError: Rule `unknown-figure`, for figures with no picture or a line
            spoken by one the picture does not draw; `artwork-contract`, for a contract
            that cannot be read.
    """
    if not panel.figures():
        return None
    if image is None:
        raise pictureless(panel)
    loaded = load_contract(image, base, loc=("setting", "image"))
    faults = undrawn(panel, loaded.contract, image.href)
    if faults:
        raise faults[0]
    return loaded


def compile_source(
    text: str,
    *,
    source: Path | None = None,
    base: Folder | None = None,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> CompileResult:
    """Compile one panel from a source string.

    The usual entry point, and the one to reach for first.

    Args:
        text: A single-panel document in the YAML surface syntax.
        source: Path the text came from, used to prefix error messages and to find the
            files it names beside it. Pass it when you have one; the diagnostics are much
            more useful with it.
        base: The folder files the document names are read from, when it is not the one
            `source` is in -- or when there is no `source` at all.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: Font to measure lettering against. Defaults to the font that ships as
            a dependency of this package.

    Returns:
        The compiled panel, with the intermediate results kept for inspection.

    Raises:
        PanelSyntaxError: The document is malformed or invalid.
        UnknownPuppetError: A cast member references a character the library lacks.
        LayoutError: The required constraints cannot all be satisfied.
        BalloonPlacementError: A balloon has no legal position.

    Example:
        >>> from scenet import compile_source, render
        >>> result = compile_source(
        ...     "{cast: {alice: {reference: alice}}, script: [{say: {by: alice, text: Hello.}}]}"
        ... )
        >>> len(result.core.balloons)
        1
        >>> result.core.balloons[0].lines
        ('Hello.',)
        >>> svg = render(result.core)

    See Also:
        :func:`compile_file <scenet.pipeline.compile_file>`, to read from disk.
        :func:`compile_scene <scenet.pipeline.compile_scene>`, for multi-panel documents.
        :func:`compile_document <scenet.pipeline.compile_document>`, to dispatch on
        extension and accept any supported syntax.
    """
    return compile_ir(
        parse_panel(text, source=source),
        library=library,
        metrics=metrics,
        base=_folder(source, base),
    )


def compile_file(
    path: Path,
    *,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> CompileResult:
    """Compile one panel from a file.

    Args:
        path: A `*.panel.yaml` document.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: Font to measure lettering against.

    Returns:
        The compiled panel.

    Raises:
        OSError: The file cannot be read.
        PanelSyntaxError: The document is malformed or invalid. The path is included
            in the message.
    """
    return compile_ir(load_panel(path), library=library, metrics=metrics, base=path.parent)


@dataclass(frozen=True, slots=True)
class Book:
    """A scene compiled: every panel, and the pages they are laid out on.

    Attributes:
        panels: Panel name to compiled panel, in reading order. A panel on a page was
            compiled at its frame's size and the page's type size; one on no page, as it
            would have been alone.
        pages: One Page Core per page, in order. Empty for a scene with no `pages:`.
        notes: What reading the document noticed that is worth saying but is no fault --
            in a comic script, a cue with nothing said under it, or a page whose stated
            count its panels do not match. Each names its line. A panel's own notes, on
            what the compiler decided, are on its `CompileResult`.
    """

    panels: dict[str, CompileResult]
    pages: tuple[PageCore, ...]
    notes: tuple[str, ...] = ()

    @property
    def fonts(self) -> dict[str, FontMetrics]:
        """Every declared font any panel was lettered in, by digest: what to render with."""
        return {
            digest: font for result in self.panels.values() for digest, font in result.fonts.items()
        }

    @property
    def images(self) -> dict[str, bytes]:
        """Every supplied picture any panel was drawn over, once, by digest: what to embed."""
        return {
            digest: data
            for result in self.panels.values()
            for digest, data in result.images.items()
        }


def compile_book(
    text: str,
    *,
    source: Path | None = None,
    base: Folder | None = None,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> Book:
    r"""Compile a scene and lay its panels out on pages.

    A page decides two things about each panel on it -- the size of its frame, and the
    height its type size is a fraction of -- and nothing else. Each panel is still compiled
    on its own, so a panel on a page is exactly that panel compiled alone at that size, and
    a panel's composition never depends on what sits beside it.

    Args:
        text: A scene document. One with no `pages:` compiles exactly as
            :func:`compile_scene <scenet.pipeline.compile_scene>` always has.
        source: Path it came from, used to prefix error messages and to find the files
            it names beside it.
        base: The folder files the document names are read from, in place of the one
            `source` is in.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: Font to measure lettering against.

    Returns:
        The compiled panels and pages.

    Raises:
        PanelSyntaxError: A panel or the layout is malformed, including rule
            `page-layout` for a placement naming no panel, or a panel placed twice.
        CompositionError: An `over:` chain is unresolvable or cyclic.

    Example:
        >>> from scenet import compile_book
        >>> book = compile_book(
        ...     "pages: [{tiers: [{panels: [a, b]}]}]\n"
        ...     "panels: {a: {cast: {x: {reference: alice}}}, b: {over: a}}"
        ... )
        >>> [(frame.panel, frame.width) for frame in book.pages[0].frames]
        [('a', 880.0), ('b', 880.0)]
        >>> book.panels["a"].core.width
        880.0
    """
    return _compile_document(
        parse_scene_document(text, source=source), library, metrics, _folder(source, base)
    )


def _compile_document(
    document: SceneDocument,
    library: PuppetLibrary | None,
    metrics: FontMetrics | None,
    base: Folder | None,
) -> Book:
    """Lay out every page, then compile every panel at the size its page gave it."""
    library = library or default_library()
    layout = document.layout
    type_height = lettering_height(layout.page)

    pages: list[PageCore] = []
    frames: dict[str, Frame] = {}
    for index, page in enumerate(layout.pages):
        try:
            resolved = resolve_frames(layout.page, page, index=index, direction=document.direction)
        except RuleViolationError as exc:
            raise PanelSyntaxError(str(exc), rule=exc.rule, loc=exc.loc) from exc
        frames.update((frame.panel, frame) for frame in resolved)
        pages.append(
            PageCore(
                width=rounded(layout.page.width),
                height=rounded(layout.page.height),
                lettering_height=type_height,
                frames=tuple(_core_frame(frame) for frame in resolved),
                direction=document.direction,
            )
        )
    exclusions = _inset_clearances(frames)

    panels: dict[str, CompileResult] = {}
    for name, panel in document.panels.items():
        frame = frames.get(name)
        try:
            if frame is None:
                panels[name] = compile_ir(panel, library=library, metrics=metrics, base=base)
                continue
            panels[name] = compile_ir(
                _framed(name, panel, frame),
                library=library,
                metrics=metrics,
                base=base,
                lettering_height=type_height,
                exclusions=exclusions.get(name, ()),
                outline=_local_outline(frame),
            )
        except ScenetError as exc:
            # Which panel, so `check --deep` can say: it compiles a document the one way
            # `build` does, and that way names no panel in its errors.
            exc.panel = name
            raise
    return Book(panels=panels, pages=tuple(pages), notes=document.notes)


def _core_frame(frame: Frame) -> CoreFrame:
    """A resolved frame as the Page Core records it."""
    return CoreFrame(
        panel=frame.panel,
        x=frame.x,
        y=frame.y,
        width=frame.width,
        height=frame.height,
        inset_of=frame.inset_of,
        clearance=Box.of(frame.clearance) if frame.clearance is not None else None,
        outline=frame.outline,
    )


def _margined(
    outline: Sequence[tuple[float, float]], margin: float
) -> tuple[tuple[float, float], ...]:
    """An outline drawn in by the panel's margin, square at the corners as a margin is."""
    shrunk = Polygon(outline).buffer(-margin, join_style="mitre") if margin else Polygon(outline)
    if not isinstance(shrunk, Polygon) or shrunk.is_empty:
        return ()
    return tuple((float(x), float(y)) for x, y in shrunk.exterior.coords[:-1])


def _local_outline(frame: Frame) -> tuple[tuple[float, float], ...] | None:
    """A slanted frame's outline in its own panel's units, or `None` for a rectangle."""
    if frame.outline is None:
        return None
    return tuple((rounded(x - frame.x), rounded(y - frame.y)) for x, y in frame.outline)


def _inset_clearances(frames: Mapping[str, Frame]) -> dict[str, tuple[BBox, ...]]:
    """For each panel with insets, what its lettering must keep clear of, in its own units.

    Taken from the very clearance the page paints white, moved into the parent's
    coordinates, so what the lettering avoids and what is drawn over it cannot disagree.
    """
    clearances: dict[str, list[BBox]] = {}
    for frame in frames.values():
        if frame.inset_of is None or frame.clearance is None:
            continue
        parent = frames[frame.inset_of]
        clearances.setdefault(frame.inset_of, []).append(
            BBox(
                rounded(frame.clearance.x - parent.x),
                rounded(frame.clearance.y - parent.y),
                frame.clearance.width,
                frame.clearance.height,
            )
        )
    return {name: tuple(boxes) for name, boxes in clearances.items()}


def _framed(name: str, panel: PanelIR, frame: Frame) -> PanelIR:
    """The panel at its frame's size, its own margin kept.

    The size is validated again, because a margin that fitted the panel's declared size
    may not fit a smaller frame.
    """
    try:
        spec = PanelSpec(size=(frame.width, frame.height), margin=panel.panel.margin)
    except (ValidationError, RuleViolationError) as exc:
        raise PanelSyntaxError(
            f"panel '{name}' has a margin of {panel.panel.margin}, which leaves no room in "
            f"its {frame.width} x {frame.height} frame on the page",
            rule="page-layout",
        ) from exc
    return panel.model_copy(update={"panel": spec})


def compile_scene(
    text: str,
    *,
    source: Path | None = None,
    base: Folder | None = None,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> dict[str, CompileResult]:
    """Compile every panel in a multi-panel document.

    Each panel is compiled independently. A panel's composition must not depend on
    what sits beside it, or the same source would compile differently in isolation --
    which would make panels non-reusable and golden tests meaningless. A panel that a
    page lays out is compiled at its frame's size; see
    :func:`compile_book <scenet.pipeline.compile_book>`, which also returns the pages.
    """
    return compile_book(text, source=source, base=base, library=library, metrics=metrics).panels


def compile_scene_file(
    path: Path,
    *,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> dict[str, CompileResult]:
    """Compile every panel in a multi-panel file.

    Args:
        path: A `*.scene.yaml` document. A single-panel document also works and comes
            back as one entry named `panel`.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: Font to measure lettering against.

    Returns:
        Panel name to compiled panel, in declaration order -- which is reading order.

    Raises:
        OSError: The file cannot be read.
        PanelSyntaxError: A panel is malformed or invalid.
        CompositionError: An `over:` chain refers to a panel that does not exist, or
            forms a cycle.
    """
    return _compile_document(load_scene_document(path), library, metrics, path.parent).panels


# Which frontend handles which extension. Adding a syntax means adding a line here and
# nothing else, because every frontend produces the same IR.
FRONTENDS = {
    ".script": load_script,
    ".yaml": load_scene,
    ".yml": load_scene,
}


def _script_document(text: str, *, source: Path | None) -> SceneDocument:
    """A comic script, as a scene: its PAGE headings lay its panels out on pages."""
    document = parse_script_document(text, source=source)
    return SceneDocument(
        panels=document.panels,
        layout=document.layout,
        notes=tuple(note.message for note in document.notes),
    )


def _load_script_document(path: Path) -> SceneDocument:
    """A comic script read from disk, as `compile_script` reads one handed over as text."""
    return _script_document(path.read_text(encoding="utf-8"), source=path)


def compile_script(
    text: str,
    *,
    source: Path | None = None,
    base: Folder | None = None,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> Book:
    r"""Compile a comic script, every panel and page of it.

    The one way a script is compiled, whoever asks: `scenet build`, `scenet check --deep`,
    the MCP server and the playground used to each assemble one by hand, and would have
    drifted apart the day a script laid out pages.

    Args:
        text: The script.
        source: Path it came from, used to prefix error messages and to find the files it
            names beside it.
        base: The folder files the script names are read from, in place of the one
            `source` is in.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: Font to measure lettering against.

    Returns:
        Every panel, and the pages they are laid out on -- none yet, for a script.

    Raises:
        ScriptSyntaxError: The script cannot be read, or a panel does not validate.

    Example:
        >>> from scenet import compile_script
        >>> book = compile_script("---\ncast: {A: {reference: alice}}\n---\nPANEL 1\nA\nHi.\n")
        >>> list(book.panels)
        ['1']
    """
    return _compile_document(
        _script_document(text, source=source), library, metrics, _folder(source, base)
    )


#: The same extensions, read as whole documents -- panels and the pages they go on.
DOCUMENT_LOADERS = {
    ".script": _load_script_document,
    ".yaml": load_scene_document,
    ".yml": load_scene_document,
}


def compile_book_file(
    path: Path,
    *,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> Book:
    """Compile any supported document and its pages, choosing the frontend by extension.

    Args:
        path: A `*.panel.yaml`, `*.scene.yaml` or `*.script` file.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: Font to measure lettering against.

    Returns:
        Every panel, and the pages they are laid out on -- none for a single panel or a
        comic script.

    Raises:
        ValueError: The extension is not one any frontend reads.
        OSError: The file cannot be read.
        PanelSyntaxError: The document is malformed or invalid.
    """
    loader = DOCUMENT_LOADERS.get(path.suffix.lower())
    if loader is None:
        supported = ", ".join(sorted(FRONTENDS))
        raise ValueError(
            f"{path}: unsupported extension '{path.suffix}'; expected one of {supported}"
        )
    return _compile_document(loader(path), library, metrics, path.parent)


def compile_document(
    path: Path,
    *,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> dict[str, CompileResult]:
    """Compile any supported document, choosing the frontend by extension."""
    return compile_book_file(path, library=library, metrics=metrics).panels
