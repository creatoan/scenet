# Add your own character

A character in Scenet is not a picture. It is a skeleton plus parametric limbs, so a pose
is a set of joint angles rather than a drawing — which avoids the combinatorial explosion
of one image per pose per expression per facing direction.

That skeleton is declared in a `*.puppet.yaml` file. Scenet ships two, `alice` and `bob`.
This page walks through a third, `pip`, which the gallery keeps beside its examples, and then
through casting it: in a document, on the command line, in the playground, over MCP and from
Python.

## The file

`examples/gallery/puppets/pip.puppet.yaml`, in full:

```{literalinclude} ../../examples/gallery/puppets/pip.puppet.yaml
:language: yaml
```

## Section by section

**`units_per_head`** sets the scale. Everything else is in native units where one head is
100, and the camera converts between those and panel units. Height in head-heights is
derived, not declared:

```python
from pathlib import Path

from scenet import default_library, load_puppet

pip = load_puppet(Path("examples/gallery/puppets/pip.puppet.yaml"))
assert pip.total_height == 500.0
assert pip.heads_tall == 5.0
assert default_library().get("alice").heads_tall == 7.5
```

**`landmarks`** are the crop lines a shot type names, measured downward from the top of the
head. All nine are required — not optional-with-defaults — because any shot type may crop
at any of them, so a puppet missing one is a puppet that cannot be framed at some
perfectly ordinary shot. `head_top` must be `0`, and the rest must increase downward.

**`joints`** form a tree, rooted at `root`, which sits at the landmark `root_landmark` names —
the waist, unless you say otherwise. A joint's pose angle rotates the bone arriving at it
*and* everything below it, which is the formulation that makes posing read naturally:
bending `elbow_r` swings the upper arm and carries the forearm and hand with it. Positive
angles swing toward screen left, before the figure is mirrored to face the other way.

**`parts`** are what gets drawn — a capsule between two joints, or a blob at one, which may
sit off its joint by an `offset`, as pip's knot of hair does. They are the only place
appearance enters. The solver sees them only as the outline around them, which staging
spaces characters by and a balloon pays to cover; never as a drawing.

**`anchors`** are named attachment points. Two are load-bearing: `mouth`, where a balloon
tail aims, and `eyes`, where a gaze starts. `head_top` and `feet` are where the figure begins
and ends. Add whatever else you find useful.

**`face`** is the disc no balloon may cover. A head is not a circle, but for layout purposes
it is close enough and vastly cheaper — every "would this cover someone's face?" test
becomes one distance comparison. Its `features` are what is drawn inside it: brows, eyes, a
nose, a mouth, each riding a joint at an offset, with a size. Declare the ones your character
has, in pairs where they come in pairs. See [faces](../reference/asset_contract.md#faces).

**`poses`** are named sets of joint angles. Joints you leave out keep their rest angle. A
cast member that names no pose gets `standing_neutral`, so declare one.

**`expressions`** are named states of the face's features — a brow raised, eyes wide, a mouth
open. A cast member that names none gets `neutral`, so a puppet that declares expressions
must declare that one. The states each feature can take are in the
[asset contract](../reference/asset_contract.md#the-expression-vocabulary-is-a-drawing-convention).

## Cast it in a document

A cast member names a puppet file by its path, relative to the folder the document is in —
exactly as a document names a [font](../reference/language.md#font) or a
[picture](../reference/language.md#an-image-behind-the-cast):

```yaml
cast:
  alice: {reference: alice, at: left_third}
  pip:   {reference: puppets/pip.puppet.yaml, pose: waving, expression: happy}
```

- **A reference that ends in `.puppet.yaml` is a file**; any other is the name of a shipped
  puppet. A path is never a name, so `reference: alice` is always the shipped alice, whatever
  sits beside the document.
- **The path is read as a font's is**: relative to the document's folder, wherever `scenet` was
  run from, with `/` between folders. An absolute path is refused, so a document and its
  puppets travel together. `puppets/` is only a convention; `../puppets/pip.puppet.yaml` reads
  a folder of characters several documents share.
- **Only what the cast names is read.** A file beside the document that nobody casts changes
  nothing, and a file several members name is read once.
- **The pose and expression are the puppet's own**: `pip` waves and throws its arms up, and
  cannot point, because its file declares no `pointing`. `scenet check` lists the ones it does.
- **Panel Core records the reference as written**, `puppets/pip.puppet.yaml`, and the `name:`
  inside the file is what a message calls the puppet.

The gallery's `69-a-puppet-of-your-own.scene.yaml` casts pip beside alice, in every pose and
every expression it has: [open it in the playground](https://creatoan.github.io/scenet/playground/#example=69-a-puppet-of-your-own.scene.yaml).

### On the command line

Nothing to add: `scenet check` and `scenet build` read the puppet beside the document, as they
read its fonts and pictures, and `scenet build --watch` rebuilds when it changes.

```bash
scenet check examples/gallery/69-a-puppet-of-your-own.scene.yaml
scenet build examples/gallery/69-a-puppet-of-your-own.scene.yaml -o out/
```

A puppet file is not itself a document: `scenet check puppets/pip.puppet.yaml` is refused. It is
checked through a document that casts it.

### In the playground

**Puppet…** adds a `.puppet.yaml` file to the document's `puppets/` folder for as long as the
tab is open, and says the `reference:` to write. The gallery's `pip` is there already, for any
document to cast.

### Over MCP

Send the file in `files`, by the path the document writes, as a picture is sent. `validate`,
`compile` and `render` read it from there, and `list_puppets` given the same `files` lists it
after the shipped puppets, with its poses and expressions. See the [MCP server](../reference/mcp.md).

### From Python

A document compiled from text names its puppet the same way, with the file handed over by the
path it writes — which is what the playground and the MCP server do:

```python
from scenet import compile_source
from scenet.assets.contract import DEFAULT_LIBRARY_PATH

mine = (DEFAULT_LIBRARY_PATH / "bob.puppet.yaml").read_bytes()
result = compile_source(
    "cast: {a: {reference: puppets/mine.puppet.yaml}}",
    base={"puppets/mine.puppet.yaml": mine},
)
assert result.core.actors[0].reference == "puppets/mine.puppet.yaml"
```

A library of your own, looked up by name, still works too — one file at a time, a whole
directory, or a mapping built by hand:

```python
from scenet import PuppetLibrary, compile_source, load_puppet
from scenet.assets.contract import DEFAULT_LIBRARY_PATH

alice = load_puppet(DEFAULT_LIBRARY_PATH / "alice.puppet.yaml")
assert alice.name == "alice"

library = PuppetLibrary.from_directory(DEFAULT_LIBRARY_PATH)
assert library.names() == ("alice", "bob")

result = compile_source("cast: {a: {reference: alice}}", library=library)
assert result.core.actors[0].reference == "alice"
```

{meth}`from_directory <scenet.assets.contract.PuppetLibrary.from_directory>` reads every
`*.puppet.yaml` in a directory, and there the `name:` inside each file, not its filename, is
what a cast member's `reference` matches.

## Validation catches the mistakes you will actually make

Puppet files are validated exhaustively when they are read, because a puppet that is subtly
wrong produces a figure that is subtly wrong with nothing to point at:

| Mistake | Caught as |
|---|---|
| A landmark missing | "is missing landmarks [...]" |
| Landmarks out of order | "must increase downward from head_top to feet" |
| `head_top` not zero | "head_top must be 0, it is the origin" |
| The root joint not declared | "is not defined" |
| The root joint with a parent | "must have no parent" |
| A joint naming a parent that does not exist | "names unknown parent" |
| A joint cycle | "sits in a cycle" |
| A part, anchor, feature or pose naming a joint that does not exist | "references unknown joint" |
| `gaze.origin` not among the anchors | "is not a declared anchor" |
| One of a pair of features without the other | "is declared without its pair" |
| Expressions with no features to move | "declares expressions but no face features" |
| Expressions without `neutral` | "declares expressions but not 'neutral'" |
| A part written with the keys of both a bone and a blob, or of neither | "a part is a bone, ... or a blob" |
| A key misspelt, or written twice | "not a key a puppet has here", "appears twice" |
| Two files in one directory declaring the same `name:` | "duplicate puppet name" |

The cycle and orphan checks are not pedantry. Forward kinematics accumulates each joint's
transform from its parent's, so a cycle would not terminate and an orphan would leave a
limb with no defined position.

In a document, each of these is the finding `puppet-file`, as is a path that is absolute or
names no file. Checked as a file, `scenet check` reports it in the puppet file, at the key that
is wrong — the file to open to fix it. Checked as text, in the playground or over MCP, it is
reported on the line naming the puppet, with the puppet file's line in the message.

```python
import pydantic
import pytest

from scenet import PuppetSpec

with pytest.raises(pydantic.ValidationError, match="missing landmarks"):
    PuppetSpec.model_validate(
        {
            "name": "incomplete",
            "units_per_head": 100,
            "landmarks": {"head_top": 0, "feet": 700},
            "joints": {"root": {"parent": None, "offset": [0, 0]}},
            "face": {"joint": "root", "radius": 10},
        }
    )
```

## Make them different from each other

The two shipped puppets have deliberately different builds — the same 7.5 heads, of a head
4% larger for bob, with broader shoulders and heavier limbs. Pip is five heads tall. That is a
testing decision as much as an artistic one: a bug in camera scaling cannot hide behind
figures that happen to share a proportion, and neither can a bug in ground-sharing, which
aligns feet rather than heads.

If you add characters, make them differ. Identical puppets are a blindfold.

## What is not modelled

No hands beyond the end of a capsule, no clothing, no props, and no hair beyond a blob like
pip's knot. A face is a disc with brows, eyes, a nose and a mouth on it, and its expressions are
states of those, from a closed vocabulary. The asset contract is the *geometric* contract —
enough for the solver to place things and for the emitter to draw a legible figure. Real
artwork would slot in behind the same contract without the solver noticing, which is the
reason the boundary is drawn where it is.
