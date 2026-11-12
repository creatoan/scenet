# Read what it decided

An SVG is a picture: to find out where Bob's mouth is, you would have to parse it back.
The compiler's decisions are in the Panel Core, where every name you wrote survives
beside the numbers it resolved to. This chapter reads it, as objects and as JSON, edits
it, and draws it again.

## What you will build

A script that asks a compiled panel questions: how large the camera drew each figure,
where a speaker's mouth is, where each balloon sits and how its text was broken. It writes
the Core to a file, moves a balloon in the file, reads it back and draws it, and then
shows that compiling the same document twice gives the same bytes.

Save the umbrella panel, the [gallery's first example](../../gallery.md#two-characters), as
`talk.panel.yaml`, beside the scripts:

```{code-block} yaml
:caption: talk.panel.yaml

panel:
  size: [1000, 800]

camera:
  shot: medium_shot

cast:
  alice: {reference: alice, pose: pointing,     at: left_third}
  bob:   {reference: bob,   pose: arms_crossed, at: right_third, facing: left}

staging:
  - alice left_of bob
  - alice looking_at bob
  - alice ground_shared_with bob

script:
  - say: {by: alice, text: "You forgot your umbrella!", prefer: top_left}
  - say: {by: bob,   text: "I know."}
```

## The Core, as objects

A [`PanelCore`](../../reference/api/public/PanelCore.md) is a tree of frozen models. Its
`actors` are the cast, its `balloons` the lettering, its `camera` the shot as the compiler
resolved it; [the Panel Core types](../../reference/api/public/core-types.md) page has each
of them. [`actor`](../../reference/api/public/PanelCore.md) and `speaker` look a cast member up
by the id you gave it:

```python
from pathlib import Path

from scenet import compile_file

core = compile_file(Path("talk.panel.yaml")).core
print(core.width, core.height, core.camera.shot.value, "scale", core.camera.scale)

alice = core.actor("alice")
print(alice.reference, alice.pose, "at", alice.transform.x, "depth", alice.depth)
print("mouth", alice.anchors["mouth"])

for balloon in core.balloons:
    print(balloon.id, balloon.speaker, balloon.lines, balloon.box)
```

```text
1000.0 800.0 medium_shot scale 1.94
alice pointing at 96.87 depth 0
mouth (96.87, 225.31)
b0 alice ('You forgot', 'your umbrella!') x=243.39 y=229.25 width=203.22 height=100.8
b1 bob ('I know.',) x=496.66 y=170.22 width=113.93 height=65.8
```

Every length is in panel units, from the top left corner, `y` downwards. `lines` is the
text as the compiler broke it, measured in the font it is lettered in: a balloon's box is
the size its lines need.

## The Core, as JSON

[`to_json`](../../reference/api/public/PanelCore.md) writes the Core as JSON, with its keys
sorted, so that two Cores can be compared with `diff`;
[`from_json`](../../reference/api/public/PanelCore.md) reads it back, and checks it.
`scenet build --core` writes the same file beside the SVG. Its every field is in
[the Panel Core reference](../../reference/panel_core.md):

```python
import json
from pathlib import Path

from scenet import PanelCore, compile_file

core = compile_file(Path("talk.panel.yaml")).core
Path("talk.core.json").write_text(core.to_json(), encoding="utf-8")

document = json.loads(Path("talk.core.json").read_text(encoding="utf-8"))
print(sorted(document))
print(document["format_version"], document["balloons"][1]["lines"])

restored = PanelCore.from_json(Path("talk.core.json").read_text(encoding="utf-8"))
print(restored == core)
```

```text
['actors', 'backdrop', 'balloons', 'camera', 'captions', 'description', 'format_version', 'height', 'width']
1 ['I know.']
True
```

`format_version` is the Core format's own version. It changes when a release changes what
a field means, and `from_json` refuses a Core of another one rather than draw it wrong.

## Edit a Core, and draw it again

A renderer draws what the Core says, and makes no decision of its own. So a layout can
leave the compiler, be changed by hand or by another tool, and come back to be drawn
without going near its document. Here a script lowers Alice's balloon by 60 units, and
the root of its tail with it, in the JSON file:

```python
import json
from pathlib import Path

from scenet import PanelCore, compile_file, render

core = compile_file(Path("talk.panel.yaml")).core
document = json.loads(core.to_json())

balloon = document["balloons"][0]
balloon["box"]["y"] += 60
x, y = balloon["tail"]["start"]
balloon["tail"]["start"] = [x, y + 60]
Path("talk.core.json").write_text(json.dumps(document, indent=2), encoding="utf-8")

edited = PanelCore.from_json(Path("talk.core.json").read_text(encoding="utf-8"))
print(core.balloons[0].box.y, "->", edited.balloons[0].box.y)
Path("talk.svg").write_text(render(edited), encoding="utf-8")
print(render(edited) == render(core))
```

```text
229.25 -> 289.25
False
```

The models are frozen, so an edit in Python makes a new one with `model_copy`:

```python
from pathlib import Path

from scenet import compile_file

core = compile_file(Path("talk.panel.yaml")).core
bob = core.balloons[1]
louder = bob.model_copy(update={"font_size": bob.font_size * 1.25})
edited = core.model_copy(update={"balloons": (core.balloons[0], louder)})
print(bob.font_size, "->", edited.balloons[1].font_size)
```

```text
28.0 -> 35.0
```

Nothing checks an edit against the rules the compiler keeps: a balloon moved over a face
is drawn over it. Reading order, the clear face zones, a tail that reaches its mouth hold
for what the compiler decided, and for an edit only if you keep them.

## A page's Core

A page has a Core of its own, a [`PageCore`](../../reference/api/public/PageCore.md): the page's
size and where each panel's frame is on it. A panel on a page is compiled at its frame's
shape, so its Panel Core is the size of its frame. Save this as `page.scene.yaml`:

```{code-block} yaml
:caption: page.scene.yaml

page: {size: [1500, 1000], margin: 60, gutter: 30}
cast:
  alice: {reference: alice}
pages:
  - tiers:
      - panels: [{use: wide, width: 2}, close]
panels:
  wide:
    camera: {shot: full_shot}
  close:
    over: wide
    camera: {shot: close_up}
```

```python
from pathlib import Path

from scenet import PageCore, compile_book_file

book = compile_book_file(Path("page.scene.yaml"))
page = book.pages[0]
print(page.width, page.height)
for frame in page.frames:
    core = book.panels[frame.panel].core
    print(
        frame.panel,
        "at",
        (frame.x, frame.y),
        (frame.width, frame.height),
        "->",
        core.width,
        core.height,
    )

print(PageCore.from_json(page.to_json()) == page)
```

```text
1500.0 1000.0
wide at (60.0, 60.0) (900.0, 880.0) -> 900.0 880.0
close at (990.0, 60.0) (450.0, 880.0) -> 450.0 880.0
True
```

## Determinism

The same document always compiles to the same Core, and the same Core always draws the
same bytes: no clock, no randomness, no order that depends on the machine, no absolute
path. A compile on your laptop and one in CI agree to the byte:

```python
import hashlib
from pathlib import Path

from scenet import compile_file, render

first = render(compile_file(Path("talk.panel.yaml")).core)
second = render(compile_file(Path("talk.panel.yaml")).core)
print(first == second)

digest = hashlib.sha256(first.encode("utf-8")).hexdigest()
print(len(digest), digest == hashlib.sha256(second.encode("utf-8")).hexdigest())
```

```text
True
64 True
```

That is what makes a golden file a test: keep the SVG a document should draw, and compare
each build with it. [Outputs, batch and CI](outputs_batch_and_ci.md) does that.

## What you learned

- **The Core is the compiler's answer**, as plain frozen models: actors, balloons, captions,
  the camera, each under the names your document gave.
- **It round-trips through JSON**: `to_json` and `from_json`, sorted and checked, the file
  `scenet build --core` writes.
- **A renderer draws whatever Core it is given**, so an edited Core is drawn as edited, and
  keeping the compiler's rules is then yours to do.
- **A page has a Core too**: where each frame is, each panel compiled at its frame's shape.
- **Everything is deterministic**: the same input, the same bytes.

## Where to go next

- [Errors and notes](errors_and_notes.md): what the compiler says when it cannot do what a
  document asks, or does something it did not ask.
- [The Panel Core reference](../../reference/panel_core.md) has every field, and
  [the Core types](../../reference/api/public/core-types.md) every model.
- [The Guarantees page](../../reference/api/guarantees.md) says what determinism promises,
  and what it does not.
