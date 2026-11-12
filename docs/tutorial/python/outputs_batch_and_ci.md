# Outputs, batch and CI

The last chapter puts Scenet to work on more than one document at a time: a build of a whole
folder that reports every failure and stops on none, golden files that catch a change in
what a document draws, a check in CI, and the MCP server's tools inside a program of your
own.

## What you will build

A build script for a folder of comics, which writes an SVG for every panel and says which
documents failed and why; a golden-file check that fails when a document draws anything
other than what it drew before; a CI step, run with `scenet check` and from Python as
SARIF; and a program that calls the tools a model calls, in process.

Save these three documents in a folder `comics/`. The third has a mistake on purpose:

```{code-block} yaml
:caption: comics/corner.panel.yaml

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

```{code-block} yaml
:caption: comics/rain.scene.yaml

panel: {size: [700, 500]}
cast:
  alice: {reference: alice}
panels:
  wide:
    camera: {shot: full_shot}
    script:
      - say: {by: alice, text: "Rain again."}
  close:
    over: wide
    camera: {shot: close_up}
```

```{scenet-example}
:gives: unknown-actor
:file: comics/typo.panel.yaml

cast:
  alice: {reference: alice}
script:
  - say: {by: alcie, text: "Who am I?"}
```

## Many documents

A build of a folder compiles each document on its own, so that one broken document does
not stop the rest, and reports the failures at the end.
[`compile_book_file`](../../reference/api/public/compile_book_file.md) reads any document,
choosing by its name, as `scenet build` does. One puppet library, read once, serves every
compile:

```python
from pathlib import Path

from scenet import ScenetError, compile_book_file, default_library, render

library = default_library()
dist = Path("dist")
dist.mkdir(exist_ok=True)

failed: dict[str, str] = {}
for document in sorted(Path("comics").iterdir()):
    try:
        book = compile_book_file(document, library=library)
    except ScenetError as exc:
        failed[document.name] = getattr(exc, "rule", None) or type(exc).__name__
        continue
    stem = document.name.split(".")[0]
    for name, result in book.panels.items():
        svg = render(result.core, fonts=result.fonts, embed=result.images)
        (dist / f"{stem}.{name}.svg").write_text(svg, encoding="utf-8")

print(sorted(path.name for path in dist.iterdir()))
print("failed:", failed)
```

```text
['corner.panel.svg', 'rain.close.svg', 'rain.wide.svg']
failed: {'typo.panel.yaml': 'unknown-actor'}
```

A build for CI ends with `sys.exit(1)` when anything failed. The rule an error names,
`unknown-actor` here, is the one `scenet check` reports, and has
an entry in [the diagnostics catalogue](../../reference/diagnostics.md#unknown-actor).

Compiles may run in parallel threads, sharing only caches of parsed fonts: hand the same
library to each. The results are the same whatever order the threads finish in, so sort
what you report:

```python
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scenet import compile_document, default_library

library = default_library()
documents = [path for path in sorted(Path("comics").iterdir()) if "typo" not in path.name]


def panels_of(path: Path) -> list[str]:
    return list(compile_document(path, library=library))


with ThreadPoolExecutor() as pool:
    compiled = dict(zip(documents, pool.map(panels_of, documents), strict=True))

for document, panels in compiled.items():
    print(document.name, panels)
```

```text
corner.panel.yaml ['panel']
rain.scene.yaml ['wide', 'close']
```

## Golden files

Scenet is deterministic: the same document draws the same bytes, on every machine and
every run. So the SVG a document drew when you last looked at it is a test of every
build after. Keep it beside the document, a golden file, and compare:

```python
from pathlib import Path

from scenet import compile_file, render


def matches_golden(document: Path, golden: Path, *, update: bool = False) -> bool:
    """Whether a panel draws what its golden file holds; writes it when asked to."""
    svg = render(compile_file(document).core)
    if update or not golden.exists():
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(svg, encoding="utf-8", newline="\n")
    return golden.read_text(encoding="utf-8") == svg


golden = Path("golden/corner.svg")
print("first run writes it:", matches_golden(Path("comics/corner.panel.yaml"), golden))
print("an unchanged document matches:", matches_golden(Path("comics/corner.panel.yaml"), golden))

changed = Path("comics/corner.panel.yaml").read_text(encoding="utf-8").replace("I know.", "I do.")
Path("changed.panel.yaml").write_text(changed, encoding="utf-8")
print("a changed one does not:", matches_golden(Path("changed.panel.yaml"), golden))
```

```text
first run writes it: True
an unchanged document matches: True
a changed one does not: False
```

In a test suite, the function is the body of a test, one per document, with an `--update`
option to write the goldens again after a change you meant. Write them with `newline="\n"`,
as here, so that a golden written on Windows is the same file as one written anywhere else.
A golden is a picture you can open: review a changed one by looking at it, then commit it.

## `scenet check` in CI

`scenet check` checks documents without drawing them, and exits 1 if any has an error.
That is a CI step in itself:

```bash
scenet check comics/corner.panel.yaml comics/rain.scene.yaml
scenet check comics/typo.panel.yaml  # exits 1
```

The first line prints `ok` for each document. The second prints the fault as
`file:line:column: rule: message`, `comics/typo.panel.yaml:4:15: unknown-actor: ...`, the
form an editor or a CI problem matcher reads, and exits 1, which fails the step.

[Build and check a comic in CI](../../howto/build_in_ci.md) is a complete GitHub Actions
workflow, which uploads every finding to code scanning as SARIF. The same SARIF is there
from Python, for a pipeline of your own: [`diagnose_file`](../../reference/api/errors.md#scenetdiagnostics)
finds every fault in a document without raising, and `to_sarif` reports them:

```python
import json
from pathlib import Path

from scenet.diagnostics import diagnose_file, to_sarif

found = [finding for path in sorted(Path("comics").iterdir()) for finding in diagnose_file(path)]
sarif = to_sarif(found)
Path("scenet.sarif").write_text(json.dumps(sarif, indent=2), encoding="utf-8")

(run,) = sarif["runs"]
for result in run["results"]:
    location = result["locations"][0]["physicalLocation"]
    print(result["ruleId"], location["artifactLocation"]["uri"], location["region"]["startLine"])
```

```text
scenet/unknown-actor comics/typo.panel.yaml 4
```

## The MCP server, inside your own tool

`scenet mcp` serves five tools to a model: `get_spec`, `list_puppets`, `validate`,
`compile` and `render`. Each is a plain function in [`scenet.mcp`](../../reference/api/mcp.md#scenetmcp),
which a program can call without a server, and which returns what a model would read. It
needs the extra:

```bash
pip install 'scenet[mcp]'
```

```python
from scenet.mcp import compile_panel, list_puppets, validate

report = validate("cast: {a: {reference: alice}}\nscript: [{say: {by: b, text: Hi.}}]")
print(report.valid, [(finding.rule, finding.line, finding.column) for finding in report.findings])

compiled = compile_panel("cast: {a: {reference: alice}}")
print([panel.name for panel in compiled.panels], sorted(compiled.panels[0].core)[:4])

print([puppet.name for puppet in list_puppets().puppets])
```

```text
False [('scenet/unknown-actor', 2, 21)]
['panel'] ['actors', 'backdrop', 'balloons', 'camera']
['alice', 'bob']
```

To serve them yourself, inside a server or an agent of your own,
[`build_server`](../../reference/api/mcp.md#scenetmcp) returns the server, configured and not
running. A client connects to it in process, as a model's would over stdio:

```python
import anyio
from mcp import Client

from scenet.mcp import build_server


async def main() -> None:
    async with Client(build_server()) as client:
        tools = await client.list_tools()
        print(sorted(tool.name for tool in tools.tools))
        result = await client.call_tool("validate", {"source": "cast: {a: {reference: nobody}}"})
        print(result.structured_content["valid"])


anyio.run(main)
```

```text
['compile', 'get_spec', 'list_puppets', 'render', 'validate']
False
```

[The MCP reference](../../reference/mcp.md) says what each tool takes and returns, and
[Drive Scenet from a model](../../howto/drive_from_a_model.md) connects a model to it.

## What you learned

- **A batch compiles each document on its own**, catches `ScenetError` for each, and
  reports the rules at the end. Compiles may run in threads, sharing one library.
- **A golden file is a test**, because the same document always draws the same bytes.
- **`scenet check` is a CI step**, and `diagnose_file` with `to_sarif` is the same check
  from Python.
- **The MCP tools are plain functions**, and `build_server` is the server, for a tool of
  your own.

## Where to go next

- [The Python reference](../../reference/api/index.md): every public name, what it raises,
  and the release it appeared in; and [the Guarantees page](../../reference/api/guarantees.md),
  for threads, files and timings.
- [Use Scenet as a library](../../howto/use_as_a_library.md), the same ground as a quick
  reference, and [Build and check a comic in CI](../../howto/build_in_ci.md).
- [The author's tour](../index.md), to write the documents your program compiles.
