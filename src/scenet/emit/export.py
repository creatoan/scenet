"""Every export of a panel's staging for image models, at once (#72).

Five files, each another emitter reading Panel Core alone: the pose as OpenPose JSON, boxes
with phrases, a depth map in painter's order, an instance mask, and the semantics as
structure. **No model runs in Scenet** -- what a reader feeds these to is outside the pipeline,
as a tracing over the SVG would be -- and nothing is rasterised: text, JSON and SVG only, each
byte-identical across runs and platforms.
"""

import io
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import astuple, dataclass

from scenet.core import PanelCore
from scenet.emit.boxes import render_boxes
from scenet.emit.depth import render_depth
from scenet.emit.mask import render_mask
from scenet.emit.pose import render_pose
from scenet.emit.semantics import render_semantics

#: Each export, by the suffix its file takes after the panel's own name, in the order
#: `scenet build --conditioning` writes them -- which is also the order of the fields of
#: :class:`Conditioning <scenet.emit.export.Conditioning>`, the one place it is written.
EXPORTS: tuple[tuple[str, Callable[[PanelCore], str]], ...] = (
    (".pose.json", render_pose),
    (".boxes.json", render_boxes),
    (".depth.svg", render_depth),
    (".mask.svg", render_mask),
    (".semantics.json", render_semantics),
)


@dataclass(frozen=True, slots=True)
class Conditioning:
    """A panel's staging, exported for image models.

    Attributes:
        pose: Each actor's skeleton, OpenPose COCO-18 JSON.
        boxes: Each actor's and figure's box and phrase, GLIGEN style.
        depth: The panel's planes as grey on black, white nearest, as SVG.
        mask: Each actor, figure and mass in its own colour, as SVG.
        semantics: What the panel holds, as JSON -- structure, not a prompt.
    """

    pose: str
    boxes: str
    depth: str
    mask: str
    semantics: str

    def files(self) -> tuple[tuple[str, str], ...]:
        """Each export by the suffix its file takes, in the order `build` writes them.

        Example:
            >>> from scenet import compile_source, render_conditioning
            >>> exports = render_conditioning(
            ...     compile_source("{cast: {a: {reference: alice}}}").core
            ... )
            >>> [suffix for suffix, _ in exports.files()]
            ['.pose.json', '.boxes.json', '.depth.svg', '.mask.svg', '.semantics.json']
        """
        texts: tuple[str, ...] = astuple(self)
        return tuple(zip((suffix for suffix, _ in EXPORTS), texts, strict=True))


def render_conditioning(core: PanelCore) -> Conditioning:
    """Export a panel's staging for image models: pose, boxes, depth, mask and semantics.

    Args:
        core: The compiled panel.

    Returns:
        The five exports, as text.

    Example:
        >>> from scenet import compile_source, render_conditioning
        >>> exports = render_conditioning(compile_source("{cast: {a: {reference: alice}}}").core)
        >>> 'id="actor-a"' in exports.mask, exports.depth.count('fill="#ffffff"')
        (True, 1)
    """
    return Conditioning(*(export(core) for _, export in EXPORTS))


#: What every file in an archive is stamped with, whatever machine made it: the earliest date
#: a ZIP can hold, an ordinary file readable by all, made on Unix.
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_ZIP_MODE = 0o100644 << 16
_ZIP_UNIX = 3


def conditioning_archive(panels: Mapping[str, PanelCore], stem: str) -> bytes:
    """Every panel's exports in one ZIP, named as `scenet build --conditioning` names them.

    What the playground offers for a document of several panels, where five downloads a
    panel would be a click for every file. Unpacked, it is what the command line writes: a
    panel document's five files are `stem.pose.json` and the rest, and every other
    document's are named after their panel, `stem.one.pose.json`, even a lone one.

    Stored, not deflated, and stamped with no clock or machine of its own, so the same panels
    give the same bytes on every run and every platform.

    Args:
        panels: Each panel's Core, by name, in the document's order.
        stem: The document's name without its kinds: `story` for `story.scene.yaml`.

    Returns:
        The archive.
    """
    single = len(panels) == 1 and "panel" in panels
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, core in panels.items():
            prefix = stem if single else f"{stem}.{name}"
            for suffix, export in EXPORTS:
                entry = zipfile.ZipInfo(f"{prefix}{suffix}", date_time=_ZIP_DATE)
                entry.create_system = _ZIP_UNIX
                entry.external_attr = _ZIP_MODE
                archive.writestr(entry, export(core).encode("utf-8"))
    return buffer.getvalue()


__all__ = ["EXPORTS", "Conditioning", "conditioning_archive", "render_conditioning"]
