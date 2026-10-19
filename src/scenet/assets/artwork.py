"""The artwork contract: what a supplied picture draws, declared in its own pixels (#71).

A puppet's contract (:mod:`scenet.assets.contract`) declares everything the solver needs
about a character, so it never has to look at the drawing. An artwork contract does the
same for a picture whose people are already drawn in it: where each face is, where each
mouth is, what each body covers, and which regions lettering should stay off. The solver
reads that, and never a pixel::

    # art/p01-street.art.yaml, beside art/p01-street.png
    size: [3000, 2000]
    figures:
      ana:
        face: {center: [1240, 610], radius: 150}
        mouth: [1270, 700]
        body: [[1050, 520], [1450, 520], [1500, 2000], [1000, 2000]]
      ben:
        face: {center: [2210, 580], radius: 140}
    keep_out:
      - [[400, 1200], [900, 1200], [900, 1700], [400, 1700]]

The vocabulary is Manga109's -- a face and a body per character, with an identity -- plus
the one thing a letterer needs that Manga109 does not record: the mouth, where a tail ends.

**It is found beside its picture, by name.** `art/p01-street.png` has its contract at
`art/p01-street.art.yaml`: the contract is a measurement of one picture and travels with
it, as a puppet's joint offsets live in its own file and never in a panel. It is read
through :func:`read_relative <scenet.paths.read_relative>`, from a folder or from the files
sent with a document, exactly as the picture is.

**Coordinates are the picture's own pixels**, `x` rightward and `y` downward from its top
left corner, and the contract states the size it was measured on. That size must be the
picture's: a contract measured on another export of it would put every face in the wrong
place, and nothing could tell.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from shapely.geometry import Polygon

from scenet.errors import PanelSyntaxError, RuleViolationError
from scenet.frontends.positions import Position, Region, locate
from scenet.images import SuppliedImage
from scenet.ir import SvgText
from scenet.paths import Folder, read_relative
from scenet.safe_yaml import DuplicateKeyError, describe, load

__all__ = [
    "CONTRACT_RULE",
    "CONTRACT_SUFFIX",
    "ArtworkContract",
    "ArtworkFace",
    "ArtworkFigure",
    "ContractError",
    "LoadedContract",
    "contract_path",
    "load_contract",
]

#: The rule every fault in a contract is reported under.
CONTRACT_RULE = "artwork-contract"

#: What a contract's name ends in, in place of its picture's extension.
CONTRACT_SUFFIX = ".art.yaml"

#: A point in the picture's pixels: `x` rightward, `y` downward, from its top left.
Pixel = tuple[float, float]

#: A region of the picture: a simple polygon, three corners or more.
Outline = Annotated[tuple[Pixel, ...], Field(min_length=3)]

#: A figure's name, as the cast's `figure:` gives it.
FigureName = Annotated[SvgText, Field(min_length=1)]


class _Strict(BaseModel):
    """Frozen, refusing unknown keys and numbers that are not finite.

    The same discipline as the puppet contract and the IR: a misspelled `mouht` is a fault
    to report, not a key to ignore while the tail aims somewhere else.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ArtworkFace(_Strict):
    """A face, as a disc no lettering may cover.

    Attributes:
        center: Its centre, in the picture's pixels.
        radius: How far it reaches, in pixels. Generous is safer than tight: a balloon may
            not overlap this disc at all, and a tail stops on its edge.
    """

    center: Pixel
    radius: Annotated[float, Field(gt=0)]


class ArtworkFigure(_Strict):
    """One figure the picture draws.

    Attributes:
        face: The disc no balloon, caption or sound effect may cover.
        mouth: Where the tail of a line they speak ends -- or whatever the sound comes
            from. Without one, a tail aims at the face's centre, and stops on its edge.
        body: The silhouette a balloon pays to cover, as a polygon, or `None`. Covering a
            speaker's own body costs half, as covering a puppet's does.
    """

    face: ArtworkFace
    mouth: Pixel | None = None
    body: Outline | None = None


class ArtworkContract(_Strict):
    """Everything the solver may know about a supplied picture's content.

    Attributes:
        size: The picture's size in pixels, `[width, height]`, as it was measured. It must
            be the picture's own.
        figures: Each figure the picture draws, by name. Every face here is kept clear of
            lettering, whether or not the panel casts that figure.
        keep_out: Regions lettering should stay off -- a sign, a hand, something the
            panel is about. A cost, not a rule: a balloon covers one before it fails.
    """

    size: tuple[Annotated[int, Field(gt=0)], Annotated[int, Field(gt=0)]]
    figures: dict[FigureName, ArtworkFigure] = Field(default_factory=dict)
    keep_out: tuple[Outline, ...] = ()

    @model_validator(mode="after")
    def check_inside_the_picture(self) -> Self:
        """Every point lies on the picture, and every region is a simple polygon.

        A point off the picture is a slip -- a coordinate measured on another export, or
        `x` and `y` swapped -- and a polygon that crosses itself has no inside to cost.
        """
        for name, figure in self.figures.items():
            self._on_picture(figure.face.center, ("figures", name, "face", "center"))
            if figure.mouth is not None:
                self._on_picture(figure.mouth, ("figures", name, "mouth"))
            if figure.body is not None:
                self._region(figure.body, ("figures", name, "body"))
        for index, region in enumerate(self.keep_out):
            self._region(region, ("keep_out", index))
        return self

    def _on_picture(self, point: Pixel, loc: tuple[str | int, ...]) -> None:
        width, height = self.size
        x, y = point
        if not (0 <= x <= width and 0 <= y <= height):
            raise RuleViolationError(
                f"[{x:g}, {y:g}] is off the picture, which is {width} by {height} pixels",
                rule=CONTRACT_RULE,
                loc=loc,
            )

    def _region(self, region: Sequence[Pixel], loc: tuple[str | int, ...]) -> None:
        for index, point in enumerate(region):
            self._on_picture(point, (*loc, index))
        shape = Polygon(region)
        if not shape.is_valid or shape.area == 0:
            raise RuleViolationError(
                "a region must be a simple polygon with an inside: its edges may not cross "
                "or fold back, and its corners may not all lie on one line",
                rule=CONTRACT_RULE,
                loc=loc,
            )


class ContractError(PanelSyntaxError):
    """A contract that cannot be read, located in it as well as where its picture is named.

    Attributes:
        contract: The contract's path, as derived from the picture's -- relative to the
            document.
        inner: Where in the contract the fault is, in pydantic's `loc` form; empty for
            the contract as a whole.
        region: The fault's span in the contract's text, when it was parsed far enough to
            find it.
    """

    def __init__(
        self,
        message: str,
        *,
        contract: str,
        inner: tuple[str | int, ...] = (),
        region: Region | None = None,
        loc: tuple[str | int, ...] = (),
    ) -> None:
        """Build the error.

        Args:
            message: What is wrong, without the contract's name.
            contract: The contract's path, relative to the document.
            inner: Where in the contract.
            region: Where in its text.
            loc: Where in the document its picture is named.
        """
        self.contract = contract
        self.inner = inner
        self.region = region
        line = f", line {region.start.line}" if region is not None else ""
        super().__init__(
            f"artwork contract {contract!r}{line}: {message}", rule=CONTRACT_RULE, loc=loc
        )


@dataclass(frozen=True, slots=True)
class LoadedContract:
    """A contract, read and held to its picture.

    Attributes:
        path: Where it was found, relative to the document.
        contract: What it declares.
        sha256: The digest of its bytes.
    """

    path: str
    contract: ArtworkContract
    sha256: str


def contract_path(image: str) -> str:
    """Where a picture's contract is: beside it, its extension replaced.

    Args:
        image: The picture's path, as the document writes it.

    Returns:
        The contract's path, relative to the document as the picture's is.

    Example:
        >>> contract_path("art/p01-street.png")
        'art/p01-street.art.yaml'
        >>> contract_path("cover.final.jpg")
        'cover.final.art.yaml'
    """
    path = PurePosixPath(image)
    return str(path.with_name(path.stem + CONTRACT_SUFFIX))


def load_contract(
    image: SuppliedImage, base: Folder | None, *, loc: tuple[str | int, ...] = ()
) -> LoadedContract:
    """Read the contract beside a picture, and hold it to the picture's size.

    Args:
        image: The picture, already read.
        base: The document's folder, or the files sent with it.
        loc: Where in the document the picture is named.

    Returns:
        The contract.

    Raises:
        PanelSyntaxError: Rule `artwork-contract`, for a contract that is not there or
            cannot be read -- located where the picture is named.
        ContractError: The same rule, for a contract that is there and wrong, located in
            it too: not text, not YAML, a key written twice or unknown, a value out of
            place, or a size that is not the picture's.
    """
    path = contract_path(image.href)
    data = read_relative(path, base, what="artwork contract", rule=CONTRACT_RULE, loc=loc)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("it is not UTF-8 text", contract=path, loc=loc) from exc
    try:
        raw = load(text)
    except DuplicateKeyError as exc:
        raise ContractError(exc.summary, contract=path, region=_line(exc.line), loc=loc) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        region = _line(mark.line + 1) if mark is not None else None
        problem = getattr(exc, "problem", None) or describe(exc)
        raise ContractError(
            f"it is not valid YAML: {problem}", contract=path, region=region, loc=loc
        ) from exc
    if not isinstance(raw, dict):
        raise ContractError(
            "it must be a mapping of size, figures and keep_out", contract=path, loc=loc
        )
    contract = _validated(raw, text, path, loc)
    if contract.size != (image.width, image.height):
        width, height = contract.size
        raise ContractError(
            f"it was measured on a picture {width} by {height} pixels, and "
            f"{image.href!r} is {image.width} by {image.height}: measure it again on "
            "this one, or scale every coordinate in it",
            contract=path,
            inner=("size",),
            region=locate(text, ("size",)),
            loc=loc,
        )
    return LoadedContract(path=path, contract=contract, sha256=hashlib.sha256(data).hexdigest())


def _validated(
    raw: dict[Any, Any], text: str, path: str, loc: tuple[str | int, ...]
) -> ArtworkContract:
    """The contract, or its first fault, located in its text."""
    try:
        return ArtworkContract.model_validate(raw)
    except ValidationError as exc:
        error = exc.errors()[0]
        original = (error.get("ctx") or {}).get("error")
        if isinstance(original, RuleViolationError):
            inner, message = original.loc, str(original)
        else:
            inner = tuple(error["loc"])
            message = _plain(error["type"], error["msg"])
        where = ".".join(str(part) for part in inner)
        raise ContractError(
            f"{where}: {message}" if where else message,
            contract=path,
            inner=inner,
            region=locate(text, inner),
            loc=loc,
        ) from exc


def _plain(kind: str, message: str) -> str:
    """The message pydantic gave, in the contract's terms where it has its own."""
    if kind == "extra_forbidden":
        return (
            "not a key an artwork contract has: size, figures and keep_out at the top, "
            "and face, mouth and body for a figure"
        )
    return message


def _line(number: int) -> Region:
    """A whole line, for a fault the parser knows only the line of."""
    return Region(start=Position(line=number, column=1), end=Position(line=number + 1, column=1))
