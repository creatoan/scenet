"""The YAML surface syntax: text in, validated IR out.

This is one frontend among several planned -- a comic-script frontend will target the
same IR. Keeping parsing separate from the IR is what makes that possible without
touching anything downstream.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scenet.compose import (
    DIRECTION_KEY,
    NOT_DEFAULTS,
    PANELS_SHAPE,
    Lowered,
    lowered,
    merge,
    own_direction,
    resolve_beneath,
    resolve_overrides,
    settle,
    without_nulls,
)
from scenet.errors import CompositionError, PanelSyntaxError, RuleViolationError
from scenet.frontends.common import (
    LAYOUT_KEYS,
    check_defaults,
    first_fault,
    normalise,
    normalise_layout,
    summarise,
)
from scenet.frontends.positions import KEY
from scenet.ir import IDENTIFIERS, Direction, PageLayout, PanelIR, check_placements
from scenet.limits import LIMIT_RULE, LIMITS, past
from scenet.namespace import (
    DOCUMENT_KEYS,
    DocumentHead,
    Kind,
    kind_fault,
    language_fault,
    own_document_key,
    split_head,
    stripped,
)
from scenet.paths import read_document
from scenet.safe_yaml import ProfileError, carrier, describe, is_json_file, load


def _load_document(text: str, source: Path | None) -> dict[str, Any]:
    """Read YAML text and check it is a mapping, or raise a language diagnostic.

    Every extension key is taken out of it, at every depth: nothing past here reads one.

    Args:
        text: The document source.
        source: Path it came from, used only to prefix error messages.

    Returns:
        The parsed top-level mapping.

    Raises:
        PanelSyntaxError: The text is not valid YAML, is empty, or is not a mapping.
    """
    size = len(text.encode("utf-8", "surrogatepass"))
    if size > LIMITS.document_bytes:
        raise PanelSyntaxError(
            past("document_bytes", size, LIMITS.document_bytes), source=source, rule=LIMIT_RULE
        )
    try:
        # A SafeLoader, never the full loader: panel sources are untrusted input and full
        # YAML can construct arbitrary Python objects. And one that refuses a key written
        # twice, which plain PyYAML would drop without a word.
        data = load(text, as_json=is_json_file(source))
    except ProfileError as exc:
        raise PanelSyntaxError(
            f"line {exc.line}: {exc.summary}", source=source, rule=exc.rule
        ) from exc
    except yaml.YAMLError as exc:
        written = carrier(text, as_json=is_json_file(source))
        raise PanelSyntaxError(f"invalid {written}: {describe(exc)}", source=source) from exc

    if data is None:
        raise PanelSyntaxError("panel source is empty", source=source)
    if not isinstance(data, dict):
        raise PanelSyntaxError(
            f"expected a mapping at the top level, found {type(data).__name__}", source=source
        )
    return stripped(data)


def _read_document(text: str, source: Path | None) -> tuple[dict[str, Any], Kind, Lowered]:
    """A document without its own keys, checked, and the kind its shape makes it.

    Its keyed collections are lowered to the mapping form before anything is merged, and
    what comes back says where each member of a list form was written.

    Raises:
        PanelSyntaxError: The text is not a document, or its own keys are wrong: a later
            language, a key of the wrong shape, one kept for later, or a kind it is not; or
            an item of a list form is.
    """
    head, data = split_head(_load_document(text, source), DOCUMENT_KEYS)
    shape = Kind.SCENE if "panels" in data else Kind.PANEL
    # The language first and alone: a later one's document is not this one's to read.
    fault = language_fault(head)
    if fault is None:
        try:
            DocumentHead.model_validate(head)
        except ValidationError as exc:
            rule, loc = first_fault(exc)
            raise PanelSyntaxError(
                summarise(exc, what="document"), source=source, rule=rule, loc=loc
            ) from exc
        fault = kind_fault(head, shape)
    if fault is not None:
        raise PanelSyntaxError(str(fault), source=source, rule=fault.rule, loc=fault.loc)
    found = lowered(data)
    if found.faults:
        first = found.faults[0]
        raise PanelSyntaxError(first.message, source=source, rule=first.rule, loc=first.loc)
    return found.document, shape, found


def _as_written(found: Lowered, exc: PanelSyntaxError | CompositionError) -> None:
    """Point a fault at the value as the document writes it: `cast[2].at`, in a list form."""
    exc.loc = found.where(exc.loc)


def _validate_panel(
    data: dict[str, Any], source: Path | None, *, beneath: dict[str, Any] | None = None
) -> PanelIR:
    """Normalise a parsed mapping and validate it into IR.

    Args:
        data: A parsed top-level panel mapping.
        source: Path it came from, used only to prefix error messages.
        beneath: The same panel with no removal written, for `settle`.

    Returns:
        The validated scene graph.

    Raises:
        PanelSyntaxError: The document is well-formed YAML but not a valid panel.
    """
    data, _ = settle(data, beneath=beneath)
    try:
        return PanelIR.model_validate(normalise(data))
    except PanelSyntaxError as exc:
        # Kept along with the message: a fault the frontend found itself knows its rule
        # and where it is, and `build` reports both just as `check` does.
        raise PanelSyntaxError(str(exc), source=source, rule=exc.rule, loc=exc.loc) from exc
    except ValidationError as exc:
        rule, loc = first_fault(exc)
        raise PanelSyntaxError(summarise(exc), source=source, rule=rule, loc=loc) from exc


def parse_panel(text: str, *, source: Path | None = None) -> PanelIR:
    """Parse panel source into validated IR, without compiling it.

    What :func:`compile_source <scenet.pipeline.compile_source>` does first: everything an
    author can get wrong is found here, and nothing is placed.

    Args:
        text: A single-panel document in the YAML surface syntax.
        source: Path the text came from, prefixed to every error message.

    Returns:
        The validated scene graph. No coordinates yet -- that is the solver's job.

    Raises:
        PanelSyntaxError: The document is malformed or invalid, with each fault's place.

    Note:
        A puppet the cast names is not looked up here, and a file the document names is
        not read: both are the compile's. A document with `panels:` is refused.

    Example:
        >>> from scenet import parse_panel
        >>> panel = parse_panel("cast: {a: {reference: alice, at: left_third}}")
        >>> panel.cast["a"].at
        <AnchorX.LEFT_THIRD: 'left_third'>

    See Also:
        :func:`compile_ir <scenet.pipeline.compile_ir>`, to compile what it returns.
        :func:`load_panel <scenet.frontends.yaml_front.load_panel>`, to read a file.
    """
    data, _, found = _read_document(text, source)
    try:
        return _validate_panel(data, source)
    except PanelSyntaxError as exc:
        _as_written(found, exc)
        raise


def load_panel(path: Path) -> PanelIR:
    """Read and validate a single-panel document from disk.

    Args:
        path: A `*.panel.yaml` file.

    Returns:
        The validated scene graph. No coordinates yet -- that is the solver's job.

    Raises:
        FileReadError: The file cannot be read: a
            :exc:`MissingFileError <scenet.errors.MissingFileError>`, also a
            `FileNotFoundError`, when it is not there.
        PanelSyntaxError: The document is malformed, invalid, or not UTF-8. The path is in the
            message.

    Note:
        Only the document is read; files it names are read when it is compiled.

    Example:
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> from scenet import load_panel
        >>> with TemporaryDirectory() as folder:
        ...     path = Path(folder) / "hello.panel.yaml"
        ...     _ = path.write_text("cast: {a: {reference: alice}}", encoding="utf-8")
        ...     panel = load_panel(path)
        >>> list(panel.cast)
        ['a']

    See Also:
        :func:`parse_panel <scenet.frontends.yaml_front.parse_panel>`, for text.
        :func:`compile_file <scenet.pipeline.compile_file>`, to compile the file.
    """
    return parse_panel(read_document(path), source=path)


@dataclass(frozen=True, slots=True)
class SceneDocument:
    """A scene, read: its panels, and the pages they are laid out on.

    Attributes:
        panels: Panel name to validated IR, in declaration order -- which is reading
            order. A single-panel document has one, named `panel`.
        layout: The page format and the pages. `layout.pages` is empty for a document
            that lays nothing out, which is every document written before pages existed.
        notes: What reading it noticed that is worth saying but is no fault, each naming
            its line. Only a comic script has any yet.

    Example:
        >>> from scenet import SceneDocument, parse_scene_document
        >>> document = parse_scene_document("cast: {a: {reference: alice}}")
        >>> isinstance(document, SceneDocument), list(document.panels)
        (True, ['panel'])

    See Also:
        :func:`parse_scene_document <scenet.frontends.yaml_front.parse_scene_document>`, which
        returns one.
    """

    panels: dict[str, PanelIR]
    layout: PageLayout
    notes: tuple[str, ...] = ()

    @property
    def direction(self) -> Direction:
        """Which way the document is read: the one direction every panel in it shares.

        Every panel takes it from the document and none may write its own, so the first
        panel's is everyone's; a document with no panels reads the default way.
        """
        return next((panel.direction for panel in self.panels.values()), Direction.LTR)


def parse_scene(text: str, *, source: Path | None = None) -> dict[str, PanelIR]:
    """Parse a multi-panel document, resolving `over` inheritance.

    A document with a top-level `panels:` mapping holds a sequence; anything else is
    treated as a single panel named "panel", so the two forms share one entry point
    and a single-panel file needs no ceremony.

    Panel order follows declaration order, which is reading order. `page:` and `pages:`
    are read and checked, but only the panels come back: see
    :func:`parse_scene_document <scenet.frontends.yaml_front.parse_scene_document>`.

    Args:
        text: A `panels:` document.
        source: Path the text came from, prefixed to every error message.

    Returns:
        Panel name to scene graph, each with the chain of `over` it names already resolved.

    Raises:
        PanelSyntaxError: The document is malformed, or a panel does not validate.
        CompositionError: An `over:` names a panel that does not exist, or the chain is a
            cycle.

    Note:
        Pages are not read: :func:`parse_scene_document
        <scenet.frontends.yaml_front.parse_scene_document>` keeps them.

    Example:
        >>> from scenet import parse_scene
        >>> panels = parse_scene(
        ...     "panels: {wide: {cast: {a: {reference: alice}}}, close: {over: wide}}"
        ... )
        >>> list(panels), list(panels["close"].cast)
        (['wide', 'close'], ['a'])

    See Also:
        :func:`compile_scene <scenet.pipeline.compile_scene>`, to compile it.
    """
    return parse_scene_document(text, source=source).panels


def parse_scene_document(text: str, *, source: Path | None = None) -> SceneDocument:
    r"""Parse a scene and the pages it is laid out on.

    `page:` and `pages:` are not panel defaults, unlike every other key beside `panels:`,
    so they are taken out before the defaults are applied.

    Args:
        text: The document source.
        source: Path it came from, used only to prefix error messages.

    Returns:
        The panels and the layout.

    Raises:
        PanelSyntaxError: A panel or the layout is malformed. A placement naming a panel
            that does not exist, or one placed twice, is rule `page-layout`.
        CompositionError: An `over:` chain is unresolvable or cyclic.

    Note:
        Composition is resolved and pages validated against the panels, but nothing is
        laid out.

    Example:
        >>> from scenet import parse_scene_document
        >>> document = parse_scene_document(
        ...     "cast: {a: {reference: alice}}\n"
        ...     "panels: {one: {}}\n"
        ...     "pages: [{tiers: [{panels: [one]}]}]"
        ... )
        >>> list(document.panels), len(document.layout.pages)
        (['one'], 1)

    See Also:
        :func:`compile_book <scenet.pipeline.compile_book>`, to compile it.
    """
    data, shape, found = _read_document(text, source)
    try:
        return _scene_document(data, shape, source)
    except (PanelSyntaxError, CompositionError) as exc:
        _as_written(found, exc)
        raise


def _scene_document(data: dict[str, Any], shape: Kind, source: Path | None) -> SceneDocument:
    """`parse_scene_document`, once the document is read and its collections lowered."""
    if shape is Kind.PANEL:
        if any(key in data for key in LAYOUT_KEYS):
            raise PanelSyntaxError(
                "`page:` and `pages:` lay out the panels of a scene, so a document with them "
                "needs a `panels:` mapping",
                source=source,
                rule="page-layout",
                loc=("pages",) if "pages" in data else ("page",),
            )
        # A document with no `panels:` key is a single panel. Validated from the mapping
        # already in hand rather than by handing the text back to parse_panel, which
        # would run the YAML parser over it a second time.
        return SceneDocument(panels={"panel": _validate_panel(data, source)}, layout=PageLayout())

    layout = _validate_layout(data, source)
    panels = _validate_panels({k: v for k, v in data.items() if k not in LAYOUT_KEYS}, source)
    try:
        check_placements(layout, list(panels))
    except RuleViolationError as exc:
        raise PanelSyntaxError(str(exc), source=source, rule=exc.rule, loc=exc.loc) from exc
    return SceneDocument(panels=panels, layout=layout)


def _layout_without_nulls(data: dict[str, Any]) -> dict[str, Any]:
    """A scene's `page:` and `pages:` with every key whose value is `null` taken away."""
    layout = {key: data[key] for key in LAYOUT_KEYS if key in data}
    rest = {key: value for key, value in data.items() if key not in LAYOUT_KEYS}
    return {**rest, **without_nulls(layout, PageLayout)}


def _validate_layout(data: dict[str, Any], source: Path | None) -> PageLayout:
    """Validate `page:` and `pages:`, keeping a broken rule's name when there is one."""
    try:
        return PageLayout.model_validate(normalise_layout(_layout_without_nulls(data)))
    except ValidationError as exc:
        rule, loc = first_fault(exc)
        raise PanelSyntaxError(summarise(exc), source=source, rule=rule, loc=loc) from exc


def _refuse_too_many(panels: dict[str, Any], source: Path | None) -> None:
    """Refuse more panels than the language's limit, before any is read.

    Reading each of a million first would be the cost the limit is there to stop.
    """
    if len(panels) > LIMITS.panels_per_document:
        raise PanelSyntaxError(
            past("panels_per_document", len(panels), LIMITS.panels_per_document),
            source=source,
            rule=LIMIT_RULE,
            loc=("panels",),
        )


def _validate_panels(data: dict[str, Any], source: Path | None) -> dict[str, PanelIR]:
    """The panels of a scene, with `over:` resolved and the defaults applied."""
    panels = data["panels"]
    if not isinstance(panels, dict):
        raise PanelSyntaxError(PANELS_SHAPE, source=source)
    _refuse_too_many(panels, source)
    for name, document in panels.items():
        if not isinstance(document, dict):
            raise PanelSyntaxError(f"panel '{name}' must be a mapping", source=source)
        problem = IDENTIFIERS.problem(str(name))
        if problem is not None:
            # Refused here, where `scenet check` refuses it, rather than when its file is
            # named: a name that climbs out of the folder, `../../evil`, never gets that far.
            raise PanelSyntaxError(
                problem, source=source, rule="invalid-identifier", loc=("panels", name, KEY)
            )
        if DIRECTION_KEY in document:
            # Looked for before `over:` is resolved, so it is found in the panel that wrote
            # it, `null` included: no panel can write one, so no panel can pass one on.
            raise PanelSyntaxError(
                own_direction("beside `panels:`"),
                source=source,
                rule="panel-direction",
                loc=("panels", name, DIRECTION_KEY),
            )
        # The document's own keys, its language and the rest, are no panel's either.
        for key in DOCUMENT_KEYS:
            if key in document:
                raise PanelSyntaxError(
                    own_document_key(key, "at the top of the document"),
                    source=source,
                    rule="unknown-key",
                    loc=("panels", name, key),
                )

    # Anything alongside `panels` is a default every panel inherits, which saves
    # restating the panel size and camera on each one -- except a description, which
    # says what one picture shows, and a script, which is what one panel says.
    for key, why in NOT_DEFAULTS.items():
        if key in data:
            raise PanelSyntaxError(why, source=source, rule="unknown-key", loc=(key,))
    defaults = {key: value for key, value in data.items() if key != "panels"}

    try:
        composed = resolve_overrides(panels)
    except CompositionError as exc:
        # Re-raised rather than converted: a caller that wants to distinguish an
        # unresolvable `over:` chain from a syntax error can only do so if the type
        # survives. Both are SourceError, so a caller that does not care is unaffected.
        raise CompositionError(str(exc), source=source) from exc
    standing = resolve_beneath(panels)

    result: dict[str, PanelIR] = {}
    for name, document in composed.items():
        merged = merge(defaults, document) if defaults else document
        beneath = merge(defaults, standing[name]) if defaults else standing[name]
        try:
            result[name] = _validate_panel(merged, None, beneath=beneath)
        except PanelSyntaxError as exc:
            # Located from the top of the document, as every other fault in a scene is.
            raise PanelSyntaxError(
                f"in panel '{name}': {exc}",
                source=source,
                rule=exc.rule,
                loc=("panels", name, *exc.loc),
            ) from exc
    # A default every panel overrides was read by none of them, and is written all the same.
    check_defaults(defaults, source)
    return result


def load_scene(path: Path) -> dict[str, PanelIR]:
    r"""Read and validate a multi-panel document from disk.

    Args:
        path: A `*.scene.yaml` file. A single-panel document also works and comes back
            as one entry named `panel`.

    Returns:
        Panel name to scene graph, in declaration order -- which is reading order.

    Raises:
        FileReadError: The file cannot be read: a
            :exc:`MissingFileError <scenet.errors.MissingFileError>`, also a
            `FileNotFoundError`, when it is not there.
        PanelSyntaxError: The document is malformed, invalid, or not UTF-8.
        CompositionError: An `over:` names a panel that does not exist, or the chain is a
            cycle.

    Note:
        Pages are not read: :func:`load_scene_document
        <scenet.frontends.yaml_front.load_scene_document>` keeps them.

    Example:
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> from scenet import load_scene
        >>> with TemporaryDirectory() as folder:
        ...     path = Path(folder) / "two.scene.yaml"
        ...     _ = path.write_text(
        ...         "cast: {a: {reference: alice}}\npanels: {one: {}, two: {}}", encoding="utf-8"
        ...     )
        ...     panels = load_scene(path)
        >>> list(panels)
        ['one', 'two']

    See Also:
        :func:`parse_scene <scenet.frontends.yaml_front.parse_scene>`, for text.
    """
    return parse_scene(read_document(path), source=path)


def load_scene_document(path: Path) -> SceneDocument:
    r"""Read a scene and the pages it is laid out on, from disk.

    Args:
        path: A `*.scene.yaml` file, or any YAML document the frontend reads.

    Returns:
        The panels and the layout.

    Raises:
        FileReadError: The file cannot be read: a
            :exc:`MissingFileError <scenet.errors.MissingFileError>`, also a
            `FileNotFoundError`, when it is not there.
        PanelSyntaxError: The document is malformed, invalid, or not UTF-8.
        CompositionError: An `over:` names a panel that does not exist, or the chain is a
            cycle.

    Note:
        Nothing is laid out; the pages are validated against the panels only.

    Example:
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> from scenet import load_scene_document
        >>> with TemporaryDirectory() as folder:
        ...     path = Path(folder) / "page.scene.yaml"
        ...     _ = path.write_text(
        ...         "cast: {a: {reference: alice}}\n"
        ...         "panels: {one: {}}\npages: [{tiers: [{panels: [one]}]}]",
        ...         encoding="utf-8",
        ...     )
        ...     document = load_scene_document(path)
        >>> len(document.layout.pages)
        1

    See Also:
        :func:`parse_scene_document <scenet.frontends.yaml_front.parse_scene_document>`, for text.
    """
    return parse_scene_document(read_document(path), source=path)
