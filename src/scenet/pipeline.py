"""The compiler: source through IR to Panel Core.

Each stage is separable and independently testable, which is the point of having
tiers at all. The frontend never computes a coordinate, the solver never touches
artwork, and the emitter never makes a layout decision.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from shapely.geometry import Point, Polygon

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
    CoreCaption,
    CoreFrame,
    CoreMass,
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
from scenet.errors import PanelSyntaxError, RuleViolationError
from scenet.frontends.script_front import load_script
from scenet.frontends.yaml_front import (
    SceneDocument,
    load_panel,
    load_scene,
    load_scene_document,
    parse_panel,
    parse_scene_document,
)
from scenet.geom import BBox, Vector, rounded
from scenet.ir import Mark, PageLayout, PanelIR, PanelSpec
from scenet.solve.backdrop import ResolvedBackdrop, solve_backdrop
from scenet.solve.balloons import place_script
from scenet.solve.camera import CameraSolution
from scenet.solve.page import Frame, lettering_height, resolve_frames
from scenet.solve.staging import Placement, solve_staging
from scenet.solve.text import FontMetrics


@dataclass(frozen=True, slots=True)
class CompileResult:
    """The compiled panel, with the intermediate results kept for inspection.

    Diagnostics -- notably whether the camera had to retreat to fit the cast -- are
    part of the result rather than log output, so tooling can surface them.
    """

    core: PanelCore
    camera: CameraSolution
    placements: tuple[Placement, ...]
    posed: dict[str, ResolvedPuppet]

    @property
    def notes(self) -> tuple[str, ...]:
        """Human-readable diagnostics about how this panel was compiled.

        Returns:
            Zero or more sentences describing decisions the compiler had to make that
            were not literally what the source asked for -- a camera that retreated to
            fit the cast, a balloon tail that had to bend around a face, a mark drawn
            partly outside the panel.

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
        notes: list[str] = []
        if self.camera.was_pulled_back:
            notes.append(
                f"camera retreated to {self.camera.pullback:.0%} of the requested "
                f"'{self.camera.shot.value}' framing so the cast would fit across the panel"
            )
        for balloon in self.core.balloons:
            if balloon.tail.is_curved:
                notes.append(f"balloon {balloon.id} needed a curved tail to clear a face")
        # The camera frames by body landmarks and makes no room for emanata, which is
        # what keeps them from ever moving anybody. The cost is that a tight shot can
        # crop them, so say so: a mark that silently vanished is the same complaint as
        # a camera that silently retreated.
        for actor in self.core.actors:
            for mark in actor.marks:
                if _cropped(self.core, actor, mark):
                    notes.append(
                        f"{actor.id}'s {mark.value} run off the panel at this framing; "
                        "the camera makes no room for marks, so a looser shot shows more"
                    )
        # An inset is drawn over the art, which does not move for it, so it can cover a
        # face as easily as a sky. The lettering keeps clear; the face cannot.
        for actor in self.core.actors:
            face = actor.face_exclusion.as_circle()
            if any(area.as_bbox().intersects_circle(face) for area in self.core.exclusions):
                notes.append(
                    f"an inset covers {actor.id}'s face; it is drawn over the art, which does "
                    "not move for it, so put the inset in another corner or reframe the panel"
                )
        # A slanted edge crops the art like a margin, and the camera does not know it is
        # there. Say so when it runs through a face.
        if self.core.outline is not None:
            edge = Polygon(self.core.outline)
            for actor in self.core.actors:
                face = actor.face_exclusion
                if not edge.contains(Point(face.cx, face.cy).buffer(face.r)):
                    notes.append(
                        f"the slanted edge of this panel cuts across {actor.id}'s face; "
                        "lean the tier less, or frame the shot so the face is clear of it"
                    )
        return tuple(notes)


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


def _gaze_aims(
    panel: PanelIR, posed: dict[str, ResolvedPuppet], origins: dict[str, str]
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

    Returns:
        Actor id to unit aim vector, for looking actors only.
    """
    aims: dict[str, Vector] = {}
    for actor, target in panel.gaze_targets().items():
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


def _core_backdrop(backdrop: ResolvedBackdrop | None) -> CoreBackdrop | None:
    """Reduce a resolved backdrop to its serialisable Core twin.

    Rounding happens here, as it does for every other tier boundary, so that a Core
    document is byte-identical across platforms whose float formatting differs in the
    last digit.
    """
    if backdrop is None:
        return None

    air = backdrop.atmosphere
    return CoreBackdrop(
        horizon=rounded(backdrop.horizon),
        seed=backdrop.seed,
        masses=tuple(
            CoreMass(
                id=mass.id,
                kind=mass.kind,
                plane=mass.plane,
                depth=mass.depth,
                tone=mass.tone,
                polygon=round_pairs(mass.polygon),
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
            ),
            streaks=tuple(
                CoreStreak(start=point_pair(start), end=point_pair(end))
                for start, end in air.streaks
            ),
            flecks=tuple(Disc.of(fleck) for fleck in air.flecks),
            streak_width=rounded(air.streak_width),
            fall_tone=air.fall_tone,
        ),
    )


def compile_ir(
    panel: PanelIR,
    *,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
    lettering_height: float | None = None,
    exclusions: Sequence[BBox] = (),
    outline: Sequence[tuple[float, float]] | None = None,
) -> CompileResult:
    """Compile validated IR into Panel Core.

    Args:
        panel: The validated panel.
        library: Characters to draw from. Defaults to the two shipped puppets.
        metrics: Font to measure lettering against.
        lettering_height: The height type sizes are a fraction of, instead of the panel's
            own. A page passes the same value to every panel on it; a panel compiled on
            its own leaves it out.
        exclusions: Areas no balloon or caption may touch, in panel units, because
            something is drawn over them -- on a page, the insets set into this panel.
            Nothing else moves for them: the art under an inset is drawn as usual.
        outline: The panel's border when it is not a rectangle -- on a page, a panel in a
            slanted tier -- in panel units. The panel is staged and framed in its bounding
            box as usual, and cropped to this; lettering stays inside it, a margin in.

    Returns:
        The compiled panel.
    """
    library = library or default_library()
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
    aims = _gaze_aims(panel, posed, {actor: spec.gaze.origin for actor, spec in specs.items()})
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
    )

    frame = BBox(
        panel.panel.margin,
        panel.panel.margin,
        panel.panel.width - 2 * panel.panel.margin,
        panel.panel.height - 2 * panel.panel.margin,
    )
    layout = place_script(
        panel.script,
        posed,
        frame,
        metrics=metrics,
        lettering_height=lettering_height,
        backdrop=backdrop,
        emanata={actor: drawn.zones for actor, drawn in emanata.items() if drawn.zones},
        exclusions=exclusions,
        inside=_margined(outline, panel.panel.margin) if outline is not None else None,
    )

    core = PanelCore(
        width=rounded(panel.panel.width),
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
            )
            for caption in layout.captions
        ),
        backdrop=_core_backdrop(backdrop),
        exclusions=tuple(Box.of(area) for area in exclusions),
        outline=tuple(outline) if outline is not None else None,
    )
    return CompileResult(core=core, camera=camera, placements=placements, posed=posed)


def compile_source(
    text: str,
    *,
    source: Path | None = None,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> CompileResult:
    """Compile one panel from a source string.

    The usual entry point, and the one to reach for first.

    Args:
        text: A single-panel document in the YAML surface syntax.
        source: Path the text came from, used only to prefix error messages. Pass it
            when you have one; the diagnostics are much more useful with it.
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
    return compile_ir(parse_panel(text, source=source), library=library, metrics=metrics)


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
    return compile_ir(load_panel(path), library=library, metrics=metrics)


@dataclass(frozen=True, slots=True)
class Book:
    """A scene compiled: every panel, and the pages they are laid out on.

    Attributes:
        panels: Panel name to compiled panel, in reading order. A panel on a page was
            compiled at its frame's size and the page's type size; one on no page, as it
            would have been alone.
        pages: One Page Core per page, in order. Empty for a scene with no `pages:`.
    """

    panels: dict[str, CompileResult]
    pages: tuple[PageCore, ...]


def compile_book(
    text: str,
    *,
    source: Path | None = None,
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
        source: Path it came from, used only to prefix error messages.
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
    return _compile_document(parse_scene_document(text, source=source), library, metrics)


def _compile_document(
    document: SceneDocument, library: PuppetLibrary | None, metrics: FontMetrics | None
) -> Book:
    """Lay out every page, then compile every panel at the size its page gave it."""
    library = library or default_library()
    layout = document.layout
    type_height = lettering_height(layout.page)

    pages: list[PageCore] = []
    frames: dict[str, Frame] = {}
    for index, page in enumerate(layout.pages):
        try:
            resolved = resolve_frames(layout.page, page, index=index)
        except RuleViolationError as exc:
            raise PanelSyntaxError(str(exc), rule=exc.rule, loc=exc.loc) from exc
        frames.update((frame.panel, frame) for frame in resolved)
        pages.append(
            PageCore(
                width=rounded(layout.page.width),
                height=rounded(layout.page.height),
                lettering_height=type_height,
                frames=tuple(_core_frame(frame) for frame in resolved),
            )
        )
    exclusions = _inset_clearances(frames)

    panels: dict[str, CompileResult] = {}
    for name, panel in document.panels.items():
        frame = frames.get(name)
        if frame is None:
            panels[name] = compile_ir(panel, library=library, metrics=metrics)
            continue
        panels[name] = compile_ir(
            _framed(name, panel, frame),
            library=library,
            metrics=metrics,
            lettering_height=type_height,
            exclusions=exclusions.get(name, ()),
            outline=_local_outline(frame),
        )
    return Book(panels=panels, pages=tuple(pages))


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
    return compile_book(text, source=source, library=library, metrics=metrics).panels


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
    return _compile_document(load_scene_document(path), library, metrics).panels


# Which frontend handles which extension. Adding a syntax means adding a line here and
# nothing else, because every frontend produces the same IR.
FRONTENDS = {
    ".script": load_script,
    ".yaml": load_scene,
    ".yml": load_scene,
}


def _load_script_document(path: Path) -> SceneDocument:
    """A comic script, as a scene with no pages: its PAGE headings lay nothing out yet."""
    return SceneDocument(panels=load_script(path), layout=PageLayout())


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
    return _compile_document(loader(path), library, metrics)


def compile_document(
    path: Path,
    *,
    library: PuppetLibrary | None = None,
    metrics: FontMetrics | None = None,
) -> dict[str, CompileResult]:
    """Compile any supported document, choosing the frontend by extension."""
    return compile_book_file(path, library=library, metrics=metrics).panels
