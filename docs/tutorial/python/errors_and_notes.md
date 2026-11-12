# Errors and notes

A compile ends in one of three ways. The document compiles; it compiles, and the compiler
says what it did that the document did not ask for, in a note; or it cannot compile, and
it raises. This chapter handles all three the way a program should: by kind and by code,
never by matching the words of a message, which a release may reword.

## What you will build

A function that tells your program's user whose fault a failure is: their document's, or
the layout's, or a missing file's. Then a report that says where in the document a fault
is, by line and column. Then a check that reads a compile's notes by their codes and
decides which of them your program will refuse.

## The `ScenetError` tree

Everything Scenet raises on purpose is a
[`ScenetError`](../../reference/api/public/errors.md). `except ScenetError` catches every
fault in a document, a layout, a file or a call to a renderer, and nothing else: a bug in
your own program is not swallowed with them. This script prints the tree:

```python
import scenet
from scenet import ScenetError


def show(kind: type, depth: int = 0) -> None:
    print("  " * depth + kind.__name__)
    for child in sorted(kind.__subclasses__(), key=lambda child: child.__name__):
        if child.__name__ in scenet.__all__:
            show(child, depth + 1)


show(ScenetError)
```

```text
ScenetError
  AssetError
    MalformedAssetError
    UnknownExpressionError
    UnknownPoseError
    UnknownPuppetError
  FileReadError
    MissingFileError
  RenderError
  SolverError
    BalloonPlacementError
    LayoutError
    SfxPlacementError
  SourceError
    CompositionError
    CoreSyntaxError
    PanelSyntaxError
      ScriptSyntaxError
  UnknownActorError
```

The middle of the tree answers the question you have when a compile fails, which is whose
fault it is:

- a [`SourceError`](../../reference/api/public/errors.md) is the document's: misspelled,
  missing or malformed. Whoever wrote it fixes it;
- a [`SolverError`](../../reference/api/public/errors.md) is a document that is valid and has
  no layout: a balloon with nowhere legal to sit, a cast with nowhere to stand. The fix is
  an editorial change;
- an [`AssetError`](../../reference/api/public/errors.md) is a puppet, a pose or an expression
  the library does not have, or a puppet or font file that is not one;
- a [`FileReadError`](../../reference/api/public/errors.md) is a file your program named that
  cannot be read, and a [`RenderError`](../../reference/api/public/errors.md) a renderer called
  without what it needs.

```python
from scenet import AssetError, ScenetError, SolverError, SourceError, compile_source


def whose_fault(text: str) -> str:
    try:
        compile_source(text)
    except SourceError as exc:
        return f"the document's: {type(exc).__name__}"
    except SolverError as exc:
        return f"the layout's: {type(exc).__name__}"
    except AssetError as exc:
        return f"a character's: {type(exc).__name__}"
    except ScenetError as exc:
        return f"something else: {type(exc).__name__}"
    return "nobody's: it compiled"


print(whose_fault("panel: {size: [0, 600]}"))
print(whose_fault("cast: {a: {reference: alice}}\nscript: [{say: {by: b, text: Hi.}}]"))
print(whose_fault("cast: {a: {reference: nobody}}"))
print(
    whose_fault(
        "lettering: {size: 400}\ncast: {a: {reference: alice}}\n"
        "script: [{say: {by: a, text: Hello.}}]"
    )
)
print(whose_fault("cast: {a: {reference: alice}}"))
```

```text
the document's: PanelSyntaxError
the document's: PanelSyntaxError
a character's: UnknownPuppetError
the layout's: BalloonPlacementError
nobody's: it compiled
```

Each error is also the built-in exception you would have reached for without the tree: a
`SourceError` is a `ValueError`, an `UnknownPuppetError` a `KeyError`, and a
`MissingFileError` a `FileNotFoundError`. A handler written for those keeps working:

```python
from pathlib import Path

from scenet import MissingFileError, compile_file, compile_source

try:
    compile_source("cast: {a: {reference: nobody}}")
except KeyError as exc:
    print(type(exc).__name__, "is a KeyError")

try:
    compile_file(Path("no-such.panel.yaml"))
except FileNotFoundError as exc:
    print(isinstance(exc, MissingFileError), exc.filename)
```

```text
UnknownPuppetError is a KeyError
True no-such.panel.yaml
```

A model you build yourself, a `PanelIR(...)`, raises pydantic's `ValidationError` instead,
as pydantic does. Each function's page in [the reference](../../reference/api/index.md) lists
exactly what it raises.

## Where the fault is

A [`PanelSyntaxError`](../../reference/api/public/errors.md) carries its fault as data as well
as prose. `rule` names the rule broken, the id `scenet check` reports; `loc` is the path to
the value at fault; `detail` is the message without the file's name. A comic script's
[`ScriptSyntaxError`](../../reference/api/public/errors.md) has the `line` too:

```python
from scenet import PanelSyntaxError, ScriptSyntaxError, compile_script, compile_source

try:
    compile_source("cast: {a: {reference: alice}}\nscript: [{say: {by: b, text: Hi.}}]")
except PanelSyntaxError as exc:
    print(exc.rule, exc.loc)

try:
    compile_script("PANEL 1\n@shot: wide_screen\nSomeone, somewhere.\n")
except ScriptSyntaxError as exc:
    print("line", exc.line, exc.rule)
```

```text
unknown-actor ('script', 0, 'say', 'by')
line 2 invalid-field
```

An exception stops at the first fault. To find every fault at once, with the line and
column of each, ask [`scenet.diagnostics`](../../reference/api/errors.md#scenetdiagnostics)
rather than the compiler: [`diagnose_source`](../../reference/api/errors.md#scenetdiagnostics)
checks a document the way `scenet check` does, and returns a
[`Diagnostic`](../../reference/api/errors.md#scenetdiagnostics) for each finding, without raising.
[`diagnose_file`](../../reference/api/errors.md#scenetdiagnostics) does the same for a file:

```python
from scenet.diagnostics import diagnose_source, help_uri

text = """panel: {size: [900, 600]}
camera: {shot: very_wide}
cast:
  alice: {reference: alice, at: middle}
"""

for finding in diagnose_source(text):
    assert finding.region is not None
    start = finding.region.start
    where = ".".join(str(step) for step in finding.path)
    print(f"{start.line}:{start.column}", finding.level, finding.rule, where)
    print("   ", help_uri(finding.rule))
```

```text
2:16 error invalid-field camera.shot
    https://creatoan.github.io/scenet/reference/diagnostics.html#invalid-field
4:33 error invalid-field cast.alice.at
    https://creatoan.github.io/scenet/reference/diagnostics.html#invalid-field
```

Lines and columns count from 1. [`help_uri`](../../reference/api/errors.md#scenetdiagnostics)
gives each rule's entry in [the diagnostics catalogue](../../reference/diagnostics.md), which
says why it happens and how to fix it: link to it from your program's own report.

## Notes, matched by their codes

A note is not an error. The compile succeeded, and did something the document did not
literally ask for: a camera that retreated so the cast would fit, a tail bent around a
face. [`compile_notes`](../../reference/api/public/CompileResult.md) holds a
[`CompileNote`](../../reference/api/public/CompileNote.md) for each, with its `rule`, a code
that does not change between releases, and its `message`, a sentence that may. Save this as
`behind.panel.yaml`:

```{code-block} yaml
:caption: behind.panel.yaml

panel: {size: [900, 600]}
camera: {shot: medium_close_up}
cast:
  bob: {reference: bob, at: center}
script:
  - say: {by: carol, text: "Behind you!", off_panel: left, prefer: top_right}
```

```python
from pathlib import Path

from scenet import compile_file

result = compile_file(Path("behind.panel.yaml"))
for note in result.compile_notes:
    print(note.rule, "--", note.message)

if any(note.rule == "curved-tail" for note in result.compile_notes):
    print("a tail bends: worth a second look")
```

```text
curved-tail -- balloon b0 needed a curved tail to clear a face
a tail bends: worth a second look
```

Your program decides what a note means to it. One that publishes may refuse a panel whose
mouth the camera cropped away and accept a bent tail; one that lays out a draft accepts
both. Decide by code, from the set the catalogue lists:

```python
from pathlib import Path

from scenet import compile_file
from scenet.diagnostics import COMPILE_NOTES

REFUSED = {"cropped-mouth", "cropped-marks", "inset-covers-face"}
assert REFUSED <= set(COMPILE_NOTES)

result = compile_file(Path("behind.panel.yaml"))
refused = [note.rule for note in result.compile_notes if note.rule in REFUSED]
print("refused" if refused else "accepted", sorted(COMPILE_NOTES))
```

```text
accepted ['bold-italic-stand-in', 'camera-retreated', 'cropped-marks', 'cropped-mouth', 'curved-tail', 'inset-covers-face', 'italic-stand-in', 'slant-cuts-face']
```

A [`Book`](../../reference/api/public/Book.md) has the notes of each of its panels, on each
panel's result, and `book.notes` for the notes about its pages.

## What you learned

- **Catch `ScenetError`** for everything a document, a layout, a file or a renderer can go
  wrong with; catch `SourceError`, `SolverError` or `AssetError` to tell your user whose
  fault it is. The built-in bases still work.
- **A fault carries its place as data**: `rule`, `loc` and `detail`, and a script's `line`.
  `diagnose_source` and `diagnose_file` find every fault at once, with lines and columns.
- **A note is a success with something to say.** Read `compile_notes` and match each by its
  `rule`, never by its message.

## Where to go next

- [Bring your own](bring_your_own.md): your own characters, fonts, pictures and files.
- [The diagnostics catalogue](../../reference/diagnostics.md) has an entry for every rule and
  note, with a document that gives it and the same document fixed.
- [The errors page](../../reference/api/public/errors.md) of the reference has every error, and
  [What Scenet tells you](../what_scenet_tells_you.md) is the same story, told to an author.
