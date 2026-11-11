"""What a character puppet must declare.

The solver never sees artwork -- only this contract. That is what keeps rendering
swappable: the same panel lays out identically whether it is drawn as wireframe
boxes, as vector puppets, or eventually as real artwork.

A character is a skeleton plus parametric limbs rather than a picture, so a pose is
a set of joint angles and not a drawing. That avoids the combinatorial explosion of
one image per pose per expression per facing direction.
"""

from collections.abc import Mapping
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    model_validator,
)

from scenet.errors import (
    FileReadError,
    MalformedAssetError,
    RuleViolationError,
    UnknownExpressionError,
    UnknownPoseError,
    UnknownPuppetError,
)
from scenet.frontends.common import summarise
from scenet.paths import Folder, NamedFileError, read_model, record_dependency
from scenet.safe_yaml import load

__all__ = [
    "DEFAULT_LIBRARY_PATH",
    "DEFAULT_POSE",
    "PUPPET_RULE",
    "PUPPET_SUFFIX",
    "AnchorSpec",
    "BlobPart",
    "BonePart",
    "BrowState",
    "ExpressionSpec",
    "EyeState",
    "FaceSpec",
    "Feature",
    "FeatureSpec",
    "GazeSpec",
    "JointSpec",
    "Landmark",
    "MouthState",
    "PuppetFileError",
    "PuppetLibrary",
    "PuppetSpec",
    "Strict",
    "default_library",
    "is_puppet_file",
    "library_for",
    "load_puppet",
    "load_puppet_file",
]

#: What a puppet file's name ends in. A cast member's `reference` that ends in it names a
#: file, relative to the document, rather than a shipped puppet.
PUPPET_SUFFIX = ".puppet.yaml"

#: The pose a cast member gets when it does not ask for one, which every puppet declares.
DEFAULT_POSE = "standing_neutral"

#: The rule every fault in a puppet file a document names is reported under.
PUPPET_RULE = "puppet-file"


def _fault(message: str, *loc: str | int) -> RuleViolationError:
    """A puppet that is wrong at a key: said as it always was, and located at the key.

    A validator of the whole puppet knows exactly which key it found wrong, and pydantic
    would report it at the top of the file. This says where, so `scenet check` can put the
    finding on the line of a puppet file the author has to open.
    """
    return RuleViolationError(message, rule=PUPPET_RULE, loc=loc)


class Landmark(StrEnum):
    """Vertical body landmarks, measured downward from the top of the head.

    These are the crop lines a shot type names -- see docs/reference/shot_types.md.

    Example:
        >>> from scenet import Landmark, default_library
        >>> alice = default_library().get("alice")
        >>> alice.landmarks[Landmark.CHIN] < alice.landmarks[Landmark.FEET]
        True

    See Also:
        :class:`ShotType <scenet.ir.ShotType>`, each of which crops at one of these.
        :class:`PuppetSpec <scenet.assets.contract.PuppetSpec>`, which declares where each is.
    """

    HEAD_TOP = "head_top"
    EYES = "eyes"
    CHIN = "chin"
    SHOULDERS = "shoulders"
    CHEST = "chest"
    WAIST = "waist"
    MID_THIGH = "mid_thigh"
    KNEES = "knees"
    FEET = "feet"


class Strict(BaseModel):
    """Base for every puppet model: frozen, and rejecting unknown keys.

    A misspelled key in a puppet file that was silently ignored would produce a
    character that is subtly wrong -- an arm the wrong length, an anchor in the wrong
    place -- with nothing to point at. A length of `.inf` or `.nan` is refused as well:
    it is a valid YAML float, and nothing downstream can draw it.
    """

    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, use_attribute_docstrings=True
    )


class JointSpec(Strict):
    """One joint in the skeleton.

    `offset` is the rest-pose displacement from the parent joint, in native units.
    A joint's pose angle rotates the bone arriving at it *and* everything below it,
    which is the formulation that makes posing read naturally: bending `elbow_l`
    swings the upper arm and takes the forearm and hand with it.
    """

    parent: str | None = None
    """The joint it hangs from. Left out for the root."""
    offset: tuple[float, float] = (0.0, 0.0)
    """Where it is from its parent in the rest pose, in the puppet's own units."""


class BonePart(Strict):
    """A limb segment drawn as a capsule between two joints."""

    from_joint: str = Field(alias="from")
    """The joint the bone starts at."""
    to_joint: str = Field(alias="to")
    """The joint the bone ends at."""
    width: float = Field(gt=0)
    """How thick it is drawn, in the puppet's own units."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, allow_inf_nan=False
    )


class BlobPart(Strict):
    """A rounded mass -- the head, or a torso -- centred on a joint."""

    at: str
    """The joint it is centred on."""
    radius: float = Field(gt=0)
    """Its radius, in the puppet's own units."""
    offset: tuple[float, float] = (0.0, 0.0)
    """Where its centre is from that joint, in the puppet's own units."""


def _kind_of_part(value: object) -> str | None:
    """Say which kind of part `value` is written as, from the keys it uses.

    A part carries no tag, but the two kinds share no key: a bone joins two joints with
    `from` and `to`, a blob sits `at` one. Validated as a plain union, a part that failed
    as a bone was tried as a blob too, and pydantic reported both -- one bad `width` was
    six errors, five of them about a blob nobody wrote. Picking the kind first reports
    only the one that was meant.

    Returns:
        `"bone"` or `"blob"`, or `None` for a part that uses the keys of neither kind or
        of both, which is then one error saying what a part must be.
    """
    if isinstance(value, BonePart):
        return "bone"
    if isinstance(value, BlobPart):
        return "blob"
    if not isinstance(value, dict):
        return None
    bone = any(key in value for key in ("from", "to", "from_joint", "to_joint"))
    blob = "at" in value
    if bone == blob:
        return None
    return "bone" if bone else "blob"


#: One drawn part of a puppet, a bone or a blob, chosen by the keys it is written with.
Part = Annotated[
    Annotated[BonePart, Tag("bone")] | Annotated[BlobPart, Tag("blob")],
    Discriminator(
        _kind_of_part,
        custom_error_type="part_kind",
        custom_error_message=(
            "a part is a bone, with `from`, `to` and `width`, or a blob, with `at` and "
            "`radius`; this one is not exactly one of the two"
        ),
    ),
]


class AnchorSpec(Strict):
    """A named point that rides along with a joint.

    Anchors are how the solver addresses anatomy without knowing anatomy: the balloon
    tail terminates at `mouth`, and it neither knows nor cares how the head is drawn.
    """

    joint: str
    """The joint it rides along with."""
    offset: tuple[float, float] = (0.0, 0.0)
    """Where it is from that joint, in the puppet's own units, before posing."""


class Feature(StrEnum):
    """The points on a face that an expression can move.

    Named after the **groups** of the MPEG-4 FBA facial definition parameters -- brow,
    eye, nose, mouth -- rather than its full point set. The standard defines 66
    displacements over dozens of points, which is a measurement rather than a
    notation; the grouping is the part worth reusing, and it lands at about the right
    size for a drawn face. `docs/reference/asset_contract.md` records the mapping to
    MediaPipe landmark indices, which is what buys convertibility later without
    importing 478 points into the language now.

    Two omissions are deliberate. **Pupils are derived, not declared** -- they are
    offset inside the eye by where the character is looking, so authoring them would
    be authoring something the compiler already knows. And there is **no jaw**: the
    head is a circle that does not deform, so a jaw group would have no geometry to
    move.
    """

    BROW_L = "brow_l"
    BROW_R = "brow_r"
    EYE_L = "eye_l"
    EYE_R = "eye_r"
    NOSE = "nose"
    MOUTH = "mouth"

    @property
    def is_paired(self) -> bool:
        """Whether this feature is one of a left/right pair."""
        return self.value.endswith(("_l", "_r"))

    @property
    def twin(self) -> "Feature | None":
        """The other half of a left/right pair, or None for a single feature."""
        if not self.is_paired:
            return None
        stem, side = self.value[:-2], self.value[-1]
        return Feature(f"{stem}_{'r' if side == 'l' else 'l'}")


class FeatureSpec(Strict):
    """Where one facial feature sits, and how big it is.

    Structurally an :class:`AnchorSpec <scenet.assets.contract.AnchorSpec>` with a size,
    and resolved through exactly the same forward kinematics -- but declared under
    `face` rather than in `anchors`, deliberately. Anchors are how the *solver*
    addresses anatomy: the balloon tail terminates at `mouth` and the solver never
    learns how a head is drawn. Features are artwork. Mixing them would put drawing
    landmarks into the one namespace that is supposed to be free of them.
    """

    joint: str = "head"
    """The joint the feature rides, practically always `head`."""
    offset: tuple[float, float] = (0.0, 0.0)
    """Where the feature is from that joint, in the puppet's own units, before posing."""
    size: float = Field(default=0.0, ge=0.0)
    """How big the feature is drawn, in the puppet's own units: an eye's radius, a brow's or a
    mouth's half-width, a nose's length.
    """


class BrowState(StrEnum):
    """What the eyebrows are doing.

    `angled_in` puts the inner ends down, which is the anger brow; `angled_out` puts
    them up, which is the sad or frightened one. Inner and outer are resolved against
    the face centre rather than the screen, so both survive mirroring.
    """

    NEUTRAL = "neutral"
    RAISED = "raised"
    LOWERED = "lowered"
    ANGLED_IN = "angled_in"
    ANGLED_OUT = "angled_out"


class EyeState(StrEnum):
    """How open the eyes are.

    `half` is the heavy-lidded eye of boredom, distinct from `narrowed`, which is the
    squint of anger or suspicion: one is drooping, the other is tightened.
    """

    OPEN = "open"
    WIDE = "wide"
    NARROWED = "narrowed"
    HALF = "half"
    CLOSED = "closed"


class MouthState(StrEnum):
    """What the mouth is doing.

    `grin` is an open smile, `smile` a closed one, and `small` the reticent little
    mouth that does most of the work in a coy face.
    """

    NEUTRAL = "neutral"
    FLAT = "flat"
    SMILE = "smile"
    GRIN = "grin"
    FROWN = "frown"
    OPEN = "open"
    SMALL = "small"


class ExpressionSpec(Strict):
    """One named expression, as a state per feature.

    An expression is to features what a pose is to joints: a record the panel selects
    by name. A face **deforms** rather than rotating about bones, which is why this is
    a set of states and not a set of angles -- a nose joint would swing a nose.

    Every field defaults, so a `neutral` expression is `{}` and a happy one is
    `{mouth: smile}`. Unknown keys are rejected, so `mouth: raised` -- a real state,
    on the wrong feature -- is an error rather than a silently ignored line.
    """

    brow: BrowState = BrowState.NEUTRAL
    """The brows' state."""
    eyes: EyeState = EyeState.OPEN
    """The eyes' state."""
    mouth: MouthState = MouthState.NEUTRAL
    """The mouth's state."""


class FaceSpec(Strict):
    """The region a balloon may never cover, and what is drawn inside it.

    A circle rather than a polygon: faces are roughly round, the test is cheap, and
    the cost of being slightly generous here is a balloon placed a little further
    away, which is never wrong.

    `features` is optional. A puppet that declares none is drawn exactly as it was
    before faces existed -- a head is a filled circle -- and a puppet that declares
    some has those drawn and no others. There is no requirement to declare all of
    them, because a stylised character genuinely may have no eyebrows.
    """

    joint: str = "head"
    """The joint the face is centred on: the head, unless the puppet says otherwise."""
    radius: float = Field(gt=0)
    """The face's radius, in the puppet's own units: the circle no balloon covers."""
    offset: tuple[float, float] = (0.0, 0.0)
    """Where the face's centre is from that joint, in the puppet's own units."""
    features: dict[Feature, FeatureSpec] = Field(default_factory=dict)
    """What is drawn inside the face, by feature. Empty for a plain round head."""


class GazeSpec(Strict):
    """Where a character's line of sight starts.

    The *direction* is not stored: it is derived at solve time from whom the character
    is looking at, so a `looking_at` relation is enough and nobody has to compute an
    angle by hand.
    """

    origin: str = "eyes"
    """The anchor the line of sight starts at, conventionally `eyes`. It must be declared."""


class PuppetSpec(Strict):
    """The complete geometric contract for one character.

    Everything the solver may know about a character, and nothing it draws: proportions in
    head units, a skeleton, named anchors, the face, its poses and expressions. The asset
    contract reference describes the file format, field by field.

    Example:
        >>> from scenet import PuppetSpec, default_library
        >>> alice = default_library().get("alice")
        >>> isinstance(alice, PuppetSpec), alice.name, "mouth" in alice.anchors
        (True, 'alice', True)

    See Also:
        :func:`load_puppet <scenet.assets.contract.load_puppet>`, to read one from a file.
        :class:`Landmark <scenet.assets.contract.Landmark>`, the crop lines it declares.
    """

    name: str
    """The name a cast member's `reference` uses."""
    units_per_head: float = Field(gt=0)
    """How many of the puppet's own units one head height is."""
    landmarks: dict[Landmark, float]
    """Each vertical body landmark, as a distance down from the top of the head, in head
    units: the crop lines a shot type names.
    """
    joints: dict[str, JointSpec]
    """The skeleton, by joint name."""
    root: str = "root"
    """The joint every other one hangs from."""
    # Which landmark the root joint physically sits at. The skeleton is built outward
    # from the root, while landmarks are measured downward from the top of the head;
    # this is what bridges the two frames. Declared rather than assumed, because a
    # puppet is free to root itself somewhere other than the waist.
    root_landmark: Landmark = Landmark.WAIST
    """The landmark the root joint sits at."""
    parts: tuple[Part, ...] = ()
    """The shapes the body is drawn from, back to front."""
    anchors: dict[str, AnchorSpec] = Field(default_factory=dict)
    """Named attachment points, such as `mouth` and `eyes`, each on a joint."""
    face: FaceSpec
    """Where the face is, and what is drawn in it."""
    gaze: GazeSpec = GazeSpec()
    """Where the puppet's line of sight starts."""
    poses: dict[str, dict[str, float]] = Field(default_factory=dict)
    """Named poses, each a set of joint angles."""
    expressions: dict[str, ExpressionSpec] = Field(default_factory=dict)
    """Named expressions, each a state of brow, eyes and mouth."""

    @model_validator(mode="after")
    def check_landmarks_complete_and_ordered(self) -> Self:
        """Require every landmark, in head-to-foot order.

        Returns:
            The validated puppet.

        Raises:
            ValueError: A landmark is missing, `head_top` is not zero, or the values do
                not increase downward.

        All nine landmarks are required rather than optional-with-defaults because any
        shot type may crop at any of them, so a puppet missing one is a puppet that
        cannot be framed at some perfectly ordinary shot.
        """
        missing = [landmark for landmark in Landmark if landmark not in self.landmarks]
        if missing:
            raise _fault(
                f"puppet '{self.name}' is missing landmarks {[m.value for m in missing]}; "
                "every landmark is required because any shot type may crop there",
                "landmarks",
            )
        if self.landmarks[Landmark.HEAD_TOP] != 0:
            raise _fault(
                f"puppet '{self.name}': head_top must be 0, it is the origin",
                "landmarks",
                Landmark.HEAD_TOP.value,
            )

        for earlier, later in pairwise(Landmark):
            if self.landmarks[later] <= self.landmarks[earlier]:
                raise _fault(
                    f"puppet '{self.name}': landmarks must increase downward from head_top "
                    f"to feet, but {self.landmarks[later]} follows {self.landmarks[earlier]}",
                    "landmarks",
                    later.value,
                )
        return self

    @model_validator(mode="after")
    def check_skeleton_is_a_tree(self) -> Self:
        """Require the skeleton to be a tree rooted at `root`.

        Returns:
            The validated puppet.

        Raises:
            ValueError: The root is undefined or has a parent, a joint names a parent
                that does not exist, or a joint sits in a cycle.

        Forward kinematics accumulates each joint's transform from its parent's. A
        cycle would make that non-terminating and an orphan would leave a limb with no
        defined position, so both are rejected here rather than discovered at pose time.
        """
        if self.root not in self.joints:
            raise _fault(f"puppet '{self.name}': root joint '{self.root}' is not defined", "root")
        if self.joints[self.root].parent is not None:
            raise _fault(
                f"puppet '{self.name}': root joint '{self.root}' must have no parent",
                "joints",
                self.root,
                "parent",
            )

        for name, joint in self.joints.items():
            if joint.parent is not None and joint.parent not in self.joints:
                raise _fault(
                    f"puppet '{self.name}': joint '{name}' names unknown parent '{joint.parent}'",
                    "joints",
                    name,
                    "parent",
                )

        # Every joint must reach the root, which rules out both cycles and orphans.
        for name in self.joints:
            seen: set[str] = set()
            cursor: str | None = name
            while cursor is not None:
                if cursor in seen:
                    raise _fault(
                        f"puppet '{self.name}': joint '{name}' sits in a cycle",
                        "joints",
                        name,
                        "parent",
                    )
                seen.add(cursor)
                cursor = self.joints[cursor].parent
        return self

    @model_validator(mode="after")
    def check_joint_references(self) -> Self:
        """Require every joint name mentioned anywhere to exist.

        Covers parts, anchors, the face, the gaze origin, and every angle in every
        declared pose.

        Returns:
            The validated puppet.

        Raises:
            ValueError: Something references a joint or anchor that is not declared.
        """

        def require(joint: str, context: str, *loc: str | int) -> None:
            if joint not in self.joints:
                raise _fault(
                    f"puppet '{self.name}': {context} references unknown joint '{joint}'", *loc
                )

        for index, part in enumerate(self.parts):
            if isinstance(part, BonePart):
                require(part.from_joint, "part", "parts", index, "from")
                require(part.to_joint, "part", "parts", index, "to")
            else:
                require(part.at, "part", "parts", index, "at")
        for anchor_name, anchor in self.anchors.items():
            require(anchor.joint, f"anchor '{anchor_name}'", "anchors", anchor_name, "joint")
        require(self.face.joint, "face", "face", "joint")
        for feature, spec in self.face.features.items():
            require(
                spec.joint,
                f"face feature '{feature.value}'",
                "face",
                "features",
                feature.value,
                "joint",
            )

        if self.gaze.origin not in self.anchors:
            raise _fault(
                f"puppet '{self.name}': gaze origin '{self.gaze.origin}' is not a declared anchor",
                "gaze",
                "origin",
            )
        for pose_name, angles in self.poses.items():
            for joint in angles:
                require(joint, f"pose '{pose_name}'", "poses", pose_name, joint)
        return self

    @model_validator(mode="after")
    def check_default_pose(self) -> Self:
        """Require the pose a cast member gets when it does not ask for one.

        Returns:
            The validated puppet.

        Raises:
            ValueError: The puppet declares no `standing_neutral`.

        The counterpart of the `neutral` expression, and for the same reason: without
        it, every member that names no pose -- most of them -- fails on its own line, and
        nothing says the puppet is what is wrong. A pose is looked up whether or not the
        puppet declares any, so this is required of every puppet.
        """
        if DEFAULT_POSE not in self.poses:
            raise _fault(
                f"puppet '{self.name}' declares no pose '{DEFAULT_POSE}', which is what a "
                "cast member gets when it does not ask for one",
                "poses",
            )
        return self

    @model_validator(mode="after")
    def check_face_is_drawable(self) -> Self:
        """Require paired features to come in pairs, and expressions to be usable.

        Returns:
            The validated puppet.

        Raises:
            ValueError: One half of a left/right pair is declared without the other,
                a puppet declares expressions but no features for them to move, or it
                declares expressions without a `neutral` one.

        The `neutral` check is not pedantry. `CastMember.expression` defaults to
        `neutral`, so a puppet that declares expressions without one fails on every
        panel that does not name an expression explicitly -- which is most of them.
        """
        for feature in self.face.features:
            twin = feature.twin
            if twin is not None and twin not in self.face.features:
                raise _fault(
                    f"puppet '{self.name}': face feature '{feature.value}' is declared "
                    f"without its pair '{twin.value}'; a face with one eyebrow is a "
                    "typo far more often than it is a character",
                    "face",
                    "features",
                    feature.value,
                )

        if self.expressions and not self.face.features:
            raise _fault(
                f"puppet '{self.name}' declares expressions but no face features for "
                "them to move; add `face.features` or drop the expressions",
                "expressions",
            )
        if self.expressions and "neutral" not in self.expressions:
            raise _fault(
                f"puppet '{self.name}' declares expressions but not 'neutral', which is "
                "what a cast member gets when it does not ask for one",
                "expressions",
            )
        return self

    @property
    def total_height(self) -> float:
        """Head top to feet, in the puppet's own native units."""
        return self.landmarks[Landmark.FEET]

    @property
    def heads_tall(self) -> float:
        """Height in head-heights -- the classic figure-drawing proportion.

        The unit the camera works in. Two puppets of different `heads_tall` framed at
        the same shot produce figures of visibly different build, which is the whole
        reason the shipped library has a 7.5-head character and a taller one.
        """
        return self.total_height / self.units_per_head

    def pose_angles(self, pose: str) -> dict[str, float]:
        """Look up the joint angles for a named pose.

        Args:
            pose: Name of a pose this puppet declares.

        Returns:
            Joint name to angle in degrees. Joints absent from the mapping keep their
            rest angle.

        Raises:
            UnknownPoseError: This puppet has no pose by that name. The message lists
                the ones it does have. Also a `KeyError`, so `except KeyError` keeps
                working.
        """
        if pose not in self.poses:
            raise UnknownPoseError(
                f"puppet '{self.name}' has no pose '{pose}'; available: {sorted(self.poses)}"
            )
        return self.poses[pose]

    def expression_states(self, expression: str) -> ExpressionSpec:
        """Look up the feature states for a named expression.

        The counterpart of :meth:`pose_angles <scenet.assets.contract.PuppetSpec.pose_angles>`,
        and deliberately identical in shape down to the error: an expression is
        selected by name exactly as a pose is.

        Args:
            expression: Name of an expression this puppet declares.

        Returns:
            The states its features take.

        Raises:
            UnknownExpressionError: This puppet has no expression by that name. The
                message lists the ones it does have. Also a `KeyError`, so
                `except KeyError` keeps working.

        Example:
            >>> from scenet import default_library
            >>> alice = default_library().get("alice")
            >>> alice.expression_states("angry").mouth.value
            'frown'
        """
        if expression not in self.expressions:
            raise UnknownExpressionError(
                f"puppet '{self.name}' has no expression '{expression}'; "
                f"available: {sorted(self.expressions)}"
            )
        return self.expressions[expression]


class PuppetLibrary:
    """A set of puppets, by name: what a cast member's `reference` is looked up in.

    Built by hand from a mapping, read from a directory of `*.puppet.yaml` files, or the two
    shipped puppets from :func:`default_library <scenet.assets.contract.default_library>`.
    Every compile takes one as `library=`.

    Example:
        >>> from scenet import PuppetLibrary, compile_source, default_library
        >>> alice = default_library().get("alice")
        >>> library = PuppetLibrary({"alice": alice})
        >>> library.names()
        ('alice',)
        >>> compile_source("cast: {a: {reference: alice}}", library=library).core.actors[
        ...     0
        ... ].reference
        'alice'

    See Also:
        :func:`load_puppet <scenet.assets.contract.load_puppet>`, to read one puppet.
        :class:`PuppetSpec <scenet.assets.contract.PuppetSpec>`, what each puppet is.
    """

    def __init__(self, puppets: dict[str, PuppetSpec]) -> None:
        """Wrap an already-loaded mapping of puppets.

        Args:
            puppets: Puppet name to specification. Usually built by
                :meth:`from_directory <scenet.assets.contract.PuppetLibrary.from_directory>`
                rather than passed in directly -- but constructing one by hand is how
                you supply your own characters without touching the filesystem.
        """
        self._puppets = puppets

    @classmethod
    def from_directory(cls, directory: Path) -> Self:
        """Load every `*.puppet.yaml` in a directory.

        Args:
            directory: Directory to scan. Not searched recursively.

        Returns:
            A library containing every puppet found.

        Raises:
            MalformedAssetError: Two files declare the same puppet name, or one is not a
                well-formed puppet. Also a `ValueError`.
            FileReadError: A file cannot be read.

        Files are visited in sorted order so that a duplicate-name collision reports the
        same offender on every platform, whatever order the filesystem hands them back.
        """
        record_dependency(directory)
        puppets: dict[str, PuppetSpec] = {}
        # Sorted so that a duplicate-name collision reports the same offender on
        # every platform, whatever order the filesystem hands files back in.
        for path in sorted(directory.glob("*.puppet.yaml")):
            spec = load_puppet(path)
            if spec.name in puppets:
                raise MalformedAssetError(
                    f"duplicate puppet name '{spec.name}': an earlier file declares it too",
                    source=path,
                )
            puppets[spec.name] = spec
        return cls(puppets)

    def get(self, name: str) -> PuppetSpec:
        """Look up one puppet by name.

        Args:
            name: The name a cast member's `reference` field points at.

        Returns:
            That puppet's specification.

        Raises:
            UnknownPuppetError: No puppet by that name. The message lists what is
                available, because the usual cause is a typo.
        """
        if name not in self._puppets:
            raise UnknownPuppetError(
                f"unknown character '{name}'; the library has {sorted(self._puppets)}"
            )
        return self._puppets[name]

    def names(self) -> tuple[str, ...]:
        """Every puppet name in this library, sorted.

        Example:
            >>> from scenet import default_library
            >>> default_library().names()
            ('alice', 'bob')
        """
        return tuple(sorted(self._puppets))

    def with_puppets(self, puppets: Mapping[str, PuppetSpec]) -> "PuppetLibrary":
        """This library and more puppets, each under the reference that names it.

        Args:
            puppets: Reference to puppet: a puppet file's, by the path a cast member writes.

        Returns:
            A new library. This one is unchanged.
        """
        return PuppetLibrary({**self._puppets, **puppets})


def load_puppet(path: Path) -> PuppetSpec:
    """Read one `*.puppet.yaml` file into a validated specification.

    Args:
        path: The puppet file to read.

    Returns:
        The validated puppet, ready to be posed.

    Raises:
        MalformedAssetError: The file is not UTF-8, not valid YAML -- including a key
            written twice in one mapping -- or not a mapping; or the mapping is not a
            well-formed puppet: an out-of-order landmark, a skeleton that is not a tree, a
            joint referring to a parent that does not exist. Also a `ValueError`.
        FileReadError: The file cannot be read: a
            :exc:`MissingFileError <scenet.errors.MissingFileError>`, also a
            `FileNotFoundError`, when it is not there.

    Note:
        A puppet a document names by path is read by the compile instead, and a fault in it
        is located in the document as well.

    Example:
        >>> from scenet import default_library, load_puppet
        >>> from scenet.assets.contract import DEFAULT_LIBRARY_PATH
        >>> alice = load_puppet(DEFAULT_LIBRARY_PATH / "alice.puppet.yaml")
        >>> alice.name
        'alice'
        >>> round(alice.heads_tall, 1)
        7.5

    See Also:
        :meth:`PuppetLibrary.from_directory <scenet.assets.contract.PuppetLibrary.from_directory>`,
        to read a whole directory at once.
    """
    record_dependency(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MalformedAssetError("not UTF-8 text", source=path) from exc
    except OSError as exc:
        raise FileReadError.of(exc) from exc
    try:
        # A second `pointing:` used to replace the first without a word.
        data = load(text)
    except yaml.YAMLError as exc:
        raise MalformedAssetError(str(exc), source=path) from exc
    if not isinstance(data, dict):
        raise MalformedAssetError("expected a mapping at the top level", source=path)
    try:
        return PuppetSpec.model_validate(data)
    except ValidationError as exc:
        raise MalformedAssetError(summarise(exc, what="puppet"), source=path) from exc


class PuppetFileError(NamedFileError):
    """A puppet file a cast member names, there and wrong: located in it.

    Its `file` is the path the member's `reference` writes, relative to the document, and
    its `loc` is that `reference`.
    """

    KIND = "puppet file"
    RULE = PUPPET_RULE


def is_puppet_file(reference: str) -> bool:
    """Whether a cast member's `reference` names a puppet file rather than a shipped puppet.

    A path is never a name: `alice` is the shipped puppet whatever sits beside the
    document, and `puppets/alice.puppet.yaml` is a file, whatever it calls itself.

    Example:
        >>> from scenet.assets.contract import is_puppet_file
        >>> is_puppet_file("puppets/pip.puppet.yaml"), is_puppet_file("alice")
        (True, False)
    """
    return reference.lower().endswith(PUPPET_SUFFIX)


def load_puppet_file(
    declared: str, base: Folder | None, *, loc: tuple[str | int, ...] = ()
) -> PuppetSpec:
    """Read the puppet file a cast member names, beside the document or among the files sent.

    Read as a document's font and picture are: relative to the folder it is in, with `/`
    between folders, never absolute -- so a document and its puppets travel together, and
    the command line, the playground and the MCP server all read it the same way.

    Args:
        declared: The path the member's `reference` writes.
        base: The document's folder, or the files sent with it, or `None` for text with
            neither.
        loc: Where in the document the file is named: the member's `reference`.

    Returns:
        The validated puppet.

    Raises:
        PanelSyntaxError: Rule `puppet-file`, for a path that cannot be read, located
            where the document names it.
        PuppetFileError: The same rule, for a file that is there and is not a puppet,
            located in it too: not text, not YAML, a key written twice or unknown, or a
            puppet the validators refuse -- at the key they find wrong.

    Example:
        >>> from scenet.assets.contract import DEFAULT_LIBRARY_PATH, load_puppet_file
        >>> bob = (DEFAULT_LIBRARY_PATH / "bob.puppet.yaml").read_bytes()
        >>> load_puppet_file("puppets/mine.puppet.yaml", {"puppets/mine.puppet.yaml": bob}).name
        'bob'
    """
    puppet, _, _ = read_model(
        declared,
        base,
        PuppetSpec,
        what="puppet",
        error=PuppetFileError,
        holds="a puppet's name, landmarks, joints, parts, anchors, face and the rest",
        unknown_key="not a key a puppet has here",
        loc=loc,
        tags=frozenset({"bone", "blob"}),
    )
    return puppet


def library_for(
    puppets: Mapping[str, str], base: Folder | None, library: PuppetLibrary
) -> PuppetLibrary:
    """The puppets a cast is drawn from: a library, and every puppet file the cast names.

    Each file is read once, however many members it draws, and filed under the reference
    that names it, so everything downstream looks a member's puppet up by its `reference`
    as it always has. Only what the cast names is read: a file beside the document that
    nobody casts changes nothing.

    Args:
        puppets: Each cast member's `reference`, by actor id, in the cast's order.
        base: The document's folder, or the files sent with it.
        library: The puppets a name finds: the shipped ones, unless a caller gave others.

    Returns:
        `library` itself when the cast names no file, or a new one with them added.

    Raises:
        PanelSyntaxError: Rule `puppet-file`, for the first member whose file cannot be
            read, as :func:`load_puppet_file <scenet.assets.contract.load_puppet_file>`
            reports it.
    """
    files: dict[str, PuppetSpec] = {}
    for actor, reference in puppets.items():
        if is_puppet_file(reference) and reference not in files:
            files[reference] = load_puppet_file(reference, base, loc=("cast", actor, "reference"))
    return library.with_puppets(files) if files else library


DEFAULT_LIBRARY_PATH = Path(__file__).parent / "library"


def default_library() -> PuppetLibrary:
    """Load the puppets shipped with Scenet.

    Two characters of deliberately different build, so that a bug in camera scaling
    cannot hide behind two figures that happen to be the same height.

    Returns:
        A library containing `alice` and `bob`.

    Note:
        It reads the shipped puppet files on every call, and caches nothing: call it once
        and pass the library on. It raises nothing; the shipped puppets are checked when the
        package is built.

    Example:
        >>> from scenet import default_library
        >>> library = default_library()
        >>> round(library.get("alice").heads_tall, 1)
        7.5

    See Also:
        :class:`PuppetLibrary <scenet.assets.contract.PuppetLibrary>`, to build one of your own.
    """
    return PuppetLibrary.from_directory(DEFAULT_LIBRARY_PATH)
