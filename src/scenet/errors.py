"""Every exception Scenet raises, in one place.

A library that scatters its exception types across the modules that happen to raise
them forces callers to import from six places to write one `except` clause. Every error
Scenet raises is a :exc:`ScenetError`, and every one a caller can catch by name is
imported from `scenet`, so that ::

    except ScenetError:

catches every error a public function raises for bad input, a bad file or a call that
cannot be honoured, and nothing that is not Scenet's: a `ValueError` from elsewhere in
your program goes past it.

Two things are not covered, by design:

- Building a model yourself -- `PanelIR(...)`, `CameraSpec(...)` -- validates it as
  pydantic does, and raises pydantic's `ValidationError`, a `ValueError`. Scenet's own
  frontends turn that into a :exc:`PanelSyntaxError` with a location.
- A bug in Scenet -- an invariant of its own that fails -- is not your input's fault, and
  is not dressed up as if it were.

The hierarchy answers the question a caller actually has, which is *whose fault is it*::

    ScenetError
    |-- SourceError        the document is wrong -- report it to whoever wrote the panel
    |   |-- PanelSyntaxError, ScriptSyntaxError, CompositionError
    |   `-- CoreSyntaxError    a Panel or Page Core document that does not read back
    |-- SolverError        the document is fine, but no layout satisfies it
    |   `-- LayoutError, BalloonPlacementError, SfxPlacementError
    |-- AssetError         a puppet or a font is missing or malformed
    |   |-- UnknownPuppetError, UnknownPoseError, UnknownExpressionError
    |   `-- MalformedAssetError
    |-- FileReadError      a file a call names cannot be read
    |   `-- MissingFileError
    |-- RenderError        a renderer was not handed what the drawing needs
    `-- UnknownActorError  a Panel Core asked for an actor it does not hold

Each also inherits the built-in exception a caller would have reached for before this
module existed -- `SourceError` is a `ValueError`, `UnknownPuppetError` a `KeyError`,
`MissingFileError` a `FileNotFoundError` -- so pre-existing `except ValueError` handlers
keep working unchanged.
"""

from pathlib import Path

__all__ = [
    "AssetError",
    "BalloonPlacementError",
    "CompositionError",
    "CoreSyntaxError",
    "FileReadError",
    "LayoutError",
    "MalformedAssetError",
    "MissingFileError",
    "PanelSyntaxError",
    "RenderError",
    "RuleViolationError",
    "ScenetError",
    "ScriptSyntaxError",
    "SfxPlacementError",
    "SolverError",
    "SourceError",
    "UnknownActorError",
    "UnknownExpressionError",
    "UnknownPoseError",
    "UnknownPuppetError",
]


class ScenetError(Exception):
    """Root of every error Scenet raises.

    Catch this to handle anything the compiler can go wrong with, without having to
    enumerate the specific cases or accidentally swallowing an unrelated `ValueError`
    from elsewhere in your program.

    Example:
        >>> from scenet import ScenetError, compile_source
        >>> try:
        ...     compile_source("{panel: {size: [1000, 1000]}, cast: {ghost: {reference: nobody}}}")
        ... except ScenetError as exc:
        ...     print(type(exc).__name__)
        UnknownPuppetError

    See Also:
        :exc:`SourceError <scenet.errors.SourceError>`, for the "bad document" branch.
        :exc:`SolverError <scenet.errors.SolverError>`, for the "impossible layout" branch.

    Attributes:
        panel: The panel being compiled when it was raised, set as it passes out of a
            whole document's compile, so a finding can say which panel it is about; `None`
            when it was not raised compiling one.
    """

    panel: str | None = None


class RuleViolationError(ValueError):
    """A named rule, broken at a known place in the document.

    Raised *inside* pydantic validators rather than out of them. pydantic wraps whatever
    a validator raises into its own `ValidationError`, and for a model-level validator
    it records the location as `()` -- the whole document -- because a validator has no
    way to say which field it was unhappy about. That is accurate and useless: the two
    checks that matter most here, `check_references_resolve` and
    `check_ordering_is_consistent`, both knew the exact path and had nowhere to put it,
    so every such diagnostic read `at <root>`.

    pydantic keeps the exception object it caught, under `ctx["error"]`, so a subclass
    carrying extra attributes survives validation intact and can be recovered on the
    other side. That is the whole trick.

    A plain `ValueError` so that a validator raising one behaves exactly as before for
    anybody not looking for the extra attributes. It deliberately does *not* inherit
    `ScenetError`: it never escapes validation as itself -- pydantic catches it and
    re-raises its own `ValidationError` -- so putting it in that hierarchy would promise
    a `except ScenetError` clause could catch it, which it cannot.

    Attributes:
        rule: Identifier from the catalogue in
            :mod:`scenet.diagnostics <scenet.diagnostics>`. Stable across releases,
            because a `ruleId` that moves breaks every alert that referenced it.
        loc: Path to the offending value, in pydantic's `loc` form -- string keys and
            integer indices, as in `("script", 0, "say", "by")`.
    """

    def __init__(self, message: str, *, rule: str, loc: tuple[str | int, ...] = ()) -> None:
        """Build the violation.

        Args:
            message: What is wrong, phrased for whoever wrote the document.
            rule: Catalogue identifier for the rule that was broken.
            loc: Path to the offending value. Empty means the document as a whole.
        """
        self.rule = rule
        self.loc = loc
        super().__init__(message)


class SourceError(ScenetError, ValueError):
    """A document that could not be understood.

    Raised whenever the input is at fault: malformed YAML, an unknown predicate, a
    reference to a panel that does not exist, a negative panel size. The message names
    the location and the reason, and is written to be shown directly to whoever wrote
    the document -- no traceback required.

    Also a `ValueError`, since that is what a malformed value has always been.

    Attributes:
        source: Path the document was read from, or `None` for a string compiled in
            memory. Prefixed to the message when present, so a diagnostic never loses
            the file it came from.
        detail: The message without that prefix, for a report that names the file
            separately -- a finding's location does, and the path as typed could be
            absolute.

    Example:
        >>> from scenet import SourceError, compile_source
        >>> try:
        ...     compile_source("panel: {size: [0, 100]}")
        ... except SourceError as exc:
        ...     print(exc.detail.splitlines()[0])
        invalid panel:

    See Also:
        :exc:`PanelSyntaxError <scenet.errors.PanelSyntaxError>`, which most document faults are.
        :exc:`SolverError <scenet.errors.SolverError>`, for a document that is valid and impossible.
    """

    def __init__(self, message: str, *, source: Path | None = None) -> None:
        """Build the error, prefixing the source path when there is one.

        Args:
            message: What went wrong, phrased for the person who wrote the document.
            source: Path the document came from, if it was read from disk.
        """
        self.source = source
        self.detail = message
        super().__init__(f"{source}: {message}" if source else message)


class SolverError(ScenetError, ValueError):
    r"""A document that is valid but cannot be laid out.

    The distinction from :exc:`SourceError <scenet.errors.SourceError>` matters: nothing is
    misspelled and nothing is missing, but the panel as described has no solution --
    a cast with nowhere left to stand, or a balloon with no legal position. The fix is
    an editorial change to the panel, not a correction to its syntax.

    Also a `ValueError`.

    Example:
        >>> from scenet import SolverError, compile_source
        >>> try:
        ...     compile_source(
        ...         "lettering: {size: 400}\ncast: {a: {reference: alice}}\n"
        ...         "script: [{say: {by: a, text: Hello.}}]"
        ...     )
        ... except SolverError as exc:
        ...     print(type(exc).__name__)
        BalloonPlacementError

    See Also:
        :exc:`LayoutError <scenet.errors.LayoutError>`, :exc:`BalloonPlacementError
        <scenet.errors.BalloonPlacementError>` and :exc:`SfxPlacementError
        <scenet.errors.SfxPlacementError>`, its three kinds.
    """


class AssetError(ScenetError):
    """A puppet or a font that is missing, unreadable or self-inconsistent.

    Not itself a `ValueError`: a puppet the library does not hold is a
    :exc:`UnknownPuppetError`, a `KeyError`, and an `except ValueError` written for bad
    values should not catch a lookup miss. A file that is there and wrong is a
    :exc:`MalformedAssetError`, which is a `ValueError`.

    Example:
        >>> from scenet import AssetError, compile_source
        >>> try:
        ...     compile_source("cast: {a: {reference: nobody}}")
        ... except AssetError as exc:
        ...     print(type(exc).__name__)
        UnknownPuppetError

    See Also:
        :exc:`UnknownPuppetError <scenet.errors.UnknownPuppetError>`, for a puppet not there.
        :exc:`MalformedAssetError <scenet.errors.MalformedAssetError>`, for a file that is wrong.
    """


class MalformedAssetError(AssetError, ValueError):
    """A puppet or a font file that is there, and is not what it says it is.

    Raised for a puppet file that is not YAML, not a mapping, or not a well-formed puppet
    -- an out-of-order landmark, a skeleton that is not a tree; for a folder of puppets
    that declares one name twice; and for a font file that cannot be measured, because it
    is not a TrueType or OpenType font or has no Unicode character map.

    Also a `ValueError`, as each of those was before it had a name: a malformed puppet was
    pydantic's `ValidationError`, and a font with no character map a plain `ValueError`.

    Example:
        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> from scenet import MalformedAssetError, load_puppet
        >>> with TemporaryDirectory() as folder:
        ...     path = Path(folder) / "x.puppet.yaml"
        ...     _ = path.write_text("name: x", encoding="utf-8")
        ...     try:
        ...         load_puppet(path)
        ...     except MalformedAssetError as exc:
        ...         print(exc.detail.splitlines()[0])
        invalid puppet:

    Attributes:
        source: The file at fault, or `None` for bytes read from no file.
        detail: The message without the path, for a report that names the file separately.

    See Also:
        :func:`load_puppet <scenet.assets.contract.load_puppet>`, which raises it.
        :exc:`PanelSyntaxError <scenet.errors.PanelSyntaxError>`, what a malformed file a
        *document* names is instead: the fault is then the document's.
    """

    def __init__(self, message: str, *, source: Path | None = None) -> None:
        """Build the error, prefixing the file's path when there is one.

        Args:
            message: What is wrong with the file.
            source: The file, if it was read from disk.
        """
        self.source = source
        self.detail = message
        super().__init__(f"{source}: {message}" if source else message)


class FileReadError(ScenetError, OSError):
    """A file a call names that cannot be read: a document, a puppet, a font.

    Raised by the functions that take a path -- `compile_file`, `load_panel`,
    `load_puppet` and the rest -- when the system refuses to read it. A file a *document*
    names, beside it, is the document's fault instead: a
    :exc:`PanelSyntaxError <scenet.errors.PanelSyntaxError>` that says where it was named.

    Also an `OSError`, carrying what the system said: `errno`, `strerror` and `filename`
    are those of the system's own error, which is kept as `__cause__`. A file that is not
    there at all is a :exc:`MissingFileError`, which is also a `FileNotFoundError`.

    Example:
        >>> from pathlib import Path
        >>> from scenet import FileReadError, compile_file
        >>> try:
        ...     compile_file(Path("no-such.panel.yaml"))
        ... except FileReadError as exc:
        ...     print(exc.filename, "--", exc.strerror)
        no-such.panel.yaml -- No such file or directory

    See Also:
        :exc:`MissingFileError <scenet.errors.MissingFileError>`, for a file that is not there.
    """

    @staticmethod
    def of(error: OSError) -> "FileReadError":
        """The Scenet error for one the system raised, keeping what it said.

        Args:
            error: What reading the file raised.

        Returns:
            A :exc:`MissingFileError` for a file that is not there, and a
            :exc:`FileReadError` for any other reason.
        """
        kind = MissingFileError if isinstance(error, FileNotFoundError) else FileReadError
        if error.errno is None:
            return kind(str(error))
        return kind(error.errno, error.strerror, error.filename)


class MissingFileError(FileReadError, FileNotFoundError):
    """A file a call names that is not there.

    Also a `FileNotFoundError`, which is what reading it raised before, so an
    `except FileNotFoundError` around a compile keeps working.

    Example:
        >>> from pathlib import Path
        >>> from scenet import MissingFileError, load_panel
        >>> try:
        ...     load_panel(Path("no-such.panel.yaml"))
        ... except FileNotFoundError as exc:
        ...     print(isinstance(exc, MissingFileError), exc.filename)
        True no-such.panel.yaml

    See Also:
        :exc:`FileReadError <scenet.errors.FileReadError>`, for any other reason a file is unread.
    """


class RenderError(ScenetError, ValueError):
    """A renderer that was not handed what the drawing needs.

    The Core is fine; the call is not. Raised when:

    - the Core was lettered in a font of the document's own, and that font was not
      handed back as `fonts=` -- drawing its lettering in another face would draw text
      that does not fit the balloons measured for it;
    - a supplied picture is to be embedded or printed, and its bytes were not handed
      over as `embed=` or `images=`;
    - a page places a panel that was not given;
    - there is nothing to draw: no panels for a strip, no pages for a spread;
    - panels or pages read in two directions are laid side by side;
    - a picture is one the print PDF cannot carry: a lossless or 12-bit JPEG, or a PNG
      whose data is cut short.

    Also a `ValueError`, as each of these was before it had a name.

    Example:
        >>> from scenet import RenderError, render_strip
        >>> try:
        ...     render_strip([])
        ... except RenderError as exc:
        ...     print(exc)
        a strip needs at least one panel

    See Also:
        :attr:`Book.fonts <scenet.pipeline.Book.fonts>` and
        :attr:`Book.images <scenet.pipeline.Book.images>`, what a renderer is handed back.
    """


class UnknownActorError(ScenetError, KeyError):
    """A Panel Core asked for an actor or a speaker it does not hold.

    Raised by :meth:`PanelCore.actor <scenet.core.PanelCore.actor>` and
    :meth:`PanelCore.speaker <scenet.core.PanelCore.speaker>`. Also a `KeyError`, as a
    lookup miss has always been.

    Note:
        `KeyError` stringifies as `repr(args[0])`, so `str(exc)` comes out quoted.
        Read `exc.args[0]` for the bare message.

    Example:
        >>> from scenet import UnknownActorError, compile_source
        >>> core = compile_source("cast: {a: {reference: alice}}").core
        >>> try:
        ...     core.actor("b")
        ... except UnknownActorError as exc:
        ...     print(exc.args[0])
        no actor 'b' in panel

    See Also:
        :attr:`PanelCore.actors <scenet.core.PanelCore.actors>`, every actor a panel holds.
    """


class PanelSyntaxError(SourceError):
    """A panel document that could not be parsed or validated.

    Carries the source path when one is known, so the message reads
    `path/to/duel.panel.yaml: invalid panel: ...` rather than losing the file it came
    from.

    Attributes:
        rule: Identifier from the catalogue in
            :data:`RULES <scenet.diagnostics.RULES>`, when the frontend knows which rule
            was broken. Most surface faults reach `scenet check` as `invalid-field`,
            which is honest for a value pydantic rejected; but a check the frontend
            performs itself -- a place that does not exist, a setting that names one and
            lists masses too -- knows exactly what it found, and saying so is the whole
            point of having a rule catalogue.
        loc: Path to the offending value, from the top of the document, in pydantic's
            `loc` form: in a scene, it starts with `panels` and the panel's name. Empty
            means the document as a whole. When validation found several faults, the
            message lists each, and `rule` and `loc` are the first's.

    Example:
        >>> from scenet import PanelSyntaxError, compile_source
        >>> try:
        ...     compile_source("panel: {size: [0, 100]}")
        ... except PanelSyntaxError as exc:
        ...     print(exc)
        invalid panel:
          at panel: panel size must be positive

    See Also:
        :data:`RULES <scenet.diagnostics.RULES>`, the catalogue `rule` is from.
        :exc:`ScriptSyntaxError <scenet.errors.ScriptSyntaxError>`, the same for a comic script.
    """

    def __init__(
        self,
        message: str,
        *,
        source: Path | None = None,
        rule: str | None = None,
        loc: tuple[str | int, ...] = (),
    ) -> None:
        """Build the error, keeping the rule and location as data as well as prose.

        Args:
            message: What went wrong, phrased for whoever wrote the document.
            source: Path the document came from, if it was read from disk.
            rule: Catalogue identifier, when the frontend knows which rule was broken.
            loc: Path to the offending value within the panel.
        """
        self.rule = rule
        self.loc = loc
        super().__init__(message, source=source)


class ScriptSyntaxError(PanelSyntaxError):
    """A comic script that could not be parsed.

    A subclass of :exc:`PanelSyntaxError <scenet.errors.PanelSyntaxError>` rather than a
    sibling, because both frontends produce the same IR and a caller handling "bad
    input" should not have to care which syntax it was written in.

    Attributes:
        line: One-based line the fault is on, when the parser knows it. The comic-script
            frontend is line-oriented, so it usually does -- but it had only ever put
            the number into the message text, which is fine to read and useless to an
            editor drawing a squiggle. Structured diagnostics need it as a number.
            There is no column: a script line is prose, and pointing at a character
            within it would imply a precision the parser does not have.

    Example:
        >>> from scenet import ScriptSyntaxError, compile_script
        >>> try:
        ...     compile_script("No panel heading anywhere.")
        ... except ScriptSyntaxError as exc:
        ...     print(exc.line, exc.rule)
        None None

    See Also:
        :func:`parse_script <scenet.frontends.script_front.parse_script>`, which raises it.
    """

    def __init__(
        self,
        message: str,
        *,
        source: Path | None = None,
        line: int | None = None,
        rule: str | None = None,
    ) -> None:
        """Build the error, keeping the line number as data as well as prose.

        Args:
            message: What went wrong, phrased for whoever wrote the script.
            source: Path the script came from, if it was read from disk.
            line: One-based line the fault is on, if known.
            rule: Catalogue identifier, when the parser knows which rule was broken.
        """
        self.line = line
        super().__init__(message, source=source, rule=rule)


class CompositionError(SourceError):
    """A `panels:` document whose `over:` inheritance cannot be resolved.

    Raised for a panel inheriting from one that does not exist, and for a cycle --
    `a` over `b` over `a` -- which has no fixed point to resolve to.

    Example:
        >>> from scenet import CompositionError, compile_scene
        >>> try:
        ...     compile_scene("panels: {a: {over: b}, b: {over: a}}")
        ... except CompositionError as exc:
        ...     print(exc)
        'over' chain is cyclic: a -> b -> a

    Attributes:
        loc: Path to the `over:` at fault, such as `("panels", "b", "over")`, so a
            finding can point at the key rather than the whole `panels:` block.

    See Also:
        :func:`compile_scene <scenet.pipeline.compile_scene>`, which resolves `over:`.
    """

    def __init__(
        self, message: str, *, source: Path | None = None, loc: tuple[str | int, ...] = ()
    ) -> None:
        """Build the error, keeping where it is as data as well as prose.

        Args:
            message: What went wrong.
            source: Path the document came from, if it was read from disk.
            loc: Path to the `over:` at fault.
        """
        self.loc = loc
        super().__init__(message, source=source)


class CoreSyntaxError(SourceError):
    """A Panel Core or Page Core document that does not read back.

    Raised by :meth:`PanelCore.from_json <scenet.core.PanelCore.from_json>` and
    :meth:`PageCore.from_json <scenet.core.PageCore.from_json>` for text that is not
    JSON, or JSON that is not a Core of that kind. The message names each field at fault.

    Also a `ValueError`, as both of those were: `json.JSONDecodeError` and pydantic's
    `ValidationError`.

    Example:
        >>> from scenet import CoreSyntaxError, PanelCore
        >>> try:
        ...     PanelCore.from_json('{"width": 100}')
        ... except CoreSyntaxError as exc:
        ...     print(exc)
        invalid Panel Core:
          at height: Field required

    See Also:
        :meth:`PanelCore.to_json <scenet.core.PanelCore.to_json>`, what reads back.
    """


class LayoutError(SolverError):
    r"""A panel whose required constraints cannot all be satisfied.

    Actor placement runs a Cassowary solver in which non-overlap and declared
    left-to-right ordering are *required* constraints. If those genuinely conflict --
    two actors each required to be left of the other -- there is no solution and this
    is raised. Panel bounds are deliberately not required, so a merely crowded panel
    lets figures bleed off the edge instead of failing.

    Example:
        >>> from scenet import LayoutError, compile_source
        >>> try:
        ...     compile_source(
        ...         "cast: {a: {reference: alice}, b: {reference: bob}}\n"
        ...         "staging: [a in_front_of b, b in_front_of a]"
        ...     )
        ... except LayoutError as exc:
        ...     print(exc)
        depth ordering is cyclic around 'a'

    See Also:
        :class:`Relation <scenet.ir.Relation>`, the staging a layout must satisfy.
    """


class BalloonPlacementError(SolverError):
    r"""No legal position exists for a balloon or a caption.

    Every candidate position was rejected: it covered a face, left the panel,
    overlapped a box already placed, or would have broken reading order. Usually this
    means too many words for the panel size -- widen the panel, shorten the line, or
    split it across two panels.

    Captions raise this too. They obey the same hard rules and are placed in the same
    pass, so the failure is the same failure; the name is kept because the rule id
    `balloon-placement` is stable across releases.

    Example:
        >>> from scenet import BalloonPlacementError, compile_source
        >>> try:
        ...     compile_source(
        ...         "lettering: {size: 400}\ncast: {a: {reference: alice}}\n"
        ...         "script: [{say: {by: a, text: Hello.}}]"
        ...     )
        ... except BalloonPlacementError as exc:
        ...     print(type(exc).__name__)
        BalloonPlacementError

    See Also:
        :exc:`SfxPlacementError <scenet.errors.SfxPlacementError>`, the same for a sound effect.
    """


class SfxPlacementError(SolverError):
    """No legal position exists for a sound effect.

    Every candidate covered a face, left the panel, lay under an inset or over another
    sound effect. Usually the effect is too big for the panel: make it `small`, shorten
    it, or give the panel more room. Rule `sfx-placement`.

    Example:
        >>> from scenet import SfxPlacementError, SolverError
        >>> issubclass(SfxPlacementError, SolverError)
        True

    See Also:
        :class:`SfxEvent <scenet.ir.SfxEvent>`, whose `size` is usually the fix.
    """


class UnknownPuppetError(AssetError, KeyError):
    """A cast member referencing a puppet the library does not contain.

    Also a `KeyError`, because that is what a lookup miss has always been, and because
    the library is a mapping in all but name.

    Note:
        `KeyError` stringifies as `repr(args[0])`, so `str(exc)` comes out quoted.
        Read `exc.args[0]` for the bare message -- which is what the CLI does.

    Example:
        >>> from scenet import UnknownPuppetError, compile_source
        >>> try:
        ...     compile_source("cast: {a: {reference: nobody}}")
        ... except UnknownPuppetError as exc:
        ...     print(exc.args[0])
        unknown character 'nobody'; the library has ['alice', 'bob']

    See Also:
        :meth:`PuppetLibrary.names <scenet.assets.contract.PuppetLibrary.names>`, the puppets
        a library holds.
    """


class UnknownPoseError(AssetError, KeyError):
    """A cast member's `pose` naming one its puppet does not declare.

    Also a `KeyError`, for the same reason as
    :exc:`UnknownPuppetError <scenet.errors.UnknownPuppetError>`: a pose lookup has
    always failed this way, and `PuppetSpec.pose_angles`'s documented `Raises: KeyError`
    stays true. `except KeyError` keeps working; a caller that wants the rule and
    location this now carries catches `UnknownPoseError` (or `AssetError`) instead.

    Note:
        `KeyError` stringifies as `repr(args[0])`, so `str(exc)` comes out quoted.
        Read `exc.args[0]` for the bare message.

    Example:
        >>> from scenet import UnknownPoseError, compile_source
        >>> try:
        ...     compile_source("cast: {a: {reference: alice, pose: cartwheel}}")
        ... except UnknownPoseError as exc:
        ...     print(type(exc).__name__)
        UnknownPoseError

    See Also:
        :meth:`PuppetSpec.pose_angles <scenet.assets.contract.PuppetSpec.pose_angles>`, which
        raises it.
    """


class UnknownExpressionError(AssetError, KeyError):
    """A cast member's `expression` naming one its puppet does not declare.

    The counterpart of :exc:`UnknownPoseError <scenet.errors.UnknownPoseError>` for
    `PuppetSpec.expression_states`, and deliberately identical in shape -- an
    expression is selected by name exactly as a pose is.

    Note:
        `KeyError` stringifies as `repr(args[0])`, so `str(exc)` comes out quoted.
        Read `exc.args[0]` for the bare message.

    Example:
        >>> from scenet import UnknownExpressionError, compile_source
        >>> try:
        ...     compile_source("cast: {a: {reference: alice, expression: smug}}")
        ... except UnknownExpressionError as exc:
        ...     print(type(exc).__name__)
        UnknownExpressionError

    See Also:
        :meth:`PuppetSpec.expression_states
        <scenet.assets.contract.PuppetSpec.expression_states>`, which raises it.
    """
