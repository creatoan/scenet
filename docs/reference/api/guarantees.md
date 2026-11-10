# Guarantees

What the Python API promises beyond each function's own entry: what stays stable, what is
deterministic, what is safe to share between threads, which files a compile reads, and how
long it takes.

## Stability

Every name in `scenet.__all__` is public. Each one's entry gives the release it appeared in.

- **Public names follow semantic versioning.** Below 1.0, as the
  [CHANGELOG](https://github.com/creatoan/scenet/blob/main/CHANGELOG.md) says, a minor release
  may change one. When it does, the CHANGELOG says how.
- **Internal names are outside semantic versioning.** That means every name outside
  `__all__`, including the whole of a module such as `scenet.solve.balloons`. A minor release
  may rename, move or remove one without notice. They are documented, by module, under
  [Internals](index.md#internals).
- **The Panel Core types are returned, not exported.** `CoreActor`, `CoreBalloon`, `CoreFrame`
  and the rest are imported from `scenet.core`. Their fields are the Panel Core format's, which
  changes only as [the format](../panel_core.md) says: a field an old document lacks reads as
  it did, and anything else bumps `CORE_FORMAT_VERSION`.
- **An error keeps its class, and its built-in base.** `except ScenetError` catches every
  error a public function raises for bad input, a bad file or a call it cannot honour, and
  `except ValueError` keeps catching what it caught. See {py:mod}`scenet.errors` for the
  exceptions: a model you build yourself raises pydantic's `ValidationError`.

## Determinism

**The same input gives byte-identical output.** The same document, puppets and fonts, compiled
with the same release of Scenet, give the same Panel Core, SVG and PDF on every platform and
every run:

```python
from scenet import compile_source, render

source = "cast: {a: {reference: alice}}\nscript: [{say: {by: a, text: Same.}}]"
first, second = compile_source(source), compile_source(source)
assert first.core.to_json() == second.core.to_json()
assert render(first.core) == render(second.core)
```

Several things are never read: the clock, unseeded randomness, the order of a set, the
working directory, or a font installed on the machine. No absolute path reaches any output.

Determinism does not cover:

- **Another release.** A release may move a balloon. The CHANGELOG says when layout changes,
  and the golden files in the repository show by how much.
- **Pixels.** Two SVG renderers may rasterise the same file differently. What is promised is
  the file. Lettering is drawn as glyph outlines by default so that no renderer chooses a font.
- **Another puppet or font.** These are inputs like the document. A puppet file or a font with
  different bytes is a different input.

## Threads and caches

A compile keeps no global state between calls, except the caches below. Each is shared by
every thread in the process:

| Cache | What it holds | Bounded | Safe to share |
|---|---|---|---|
| `load_metrics`, an `lru_cache` in `scenet.solve.text` | The shipped fonts, parsed | 8 entries | Yes. Each entry is read only, apart from the cache inside it (below) |
| `_BY_CONTENT` in `scenet.lettering` | Each font a document declared, by the digest of its bytes | **No.** It grows with every distinct font, for the life of the process | Yes. Two threads that miss together each parse the font, and one entry wins. Both are the same font |
| Inside each `FontMetrics` | Kerning pairs and glyph outlines, read on first use | No; at most every pair and glyph of the font | Yes, under CPython's GIL: entries are only ever added, and two threads compute the same value |
| The PDF writer's and the turbulence `lru_cache`s, in `scenet.emit` | Fonts subset for print, and noise fields | 32 to 64 entries | Yes |

Some things are not cached, or not shared:

- **{py:func}`~scenet.assets.contract.default_library` caches nothing.** It reads the shipped
  puppet files again on every call. A program that compiles many panels should call it once,
  and pass the library to each compile as `library=`.
- **The set of files a compile read** is collected in a `ContextVar` in `scenet.paths`. Each
  thread, and each `asyncio` task, collects its own, so two compiles running at once never mix
  up their dependencies.

**So compiles may run in parallel threads.** Under CPython's GIL they take turns. For real
parallelism, use processes. A server compiling documents from many users holds one copy of
each distinct font they declare, until it restarts.

## Which files a compile reads

A document can name files beside it:

- a lettering font;
- a picture to letter over, and its artwork contract;
- a puppet file.

Where they are read from depends on `base=`, and on the function:

| You pass | A file the document names is read from |
|---|---|
| A path: `compile_file`, `compile_book_file`, or `source=` on a function that takes text | The document's folder |
| `base=Path(...)` | That folder |
| `base={"fonts/a.ttf": b"..."}`, a mapping | That mapping, and never the disk |
| Text, with neither | Nowhere. A document that names a file is refused |

A path that a document writes must be relative. It may not be absolute, hold a backslash or a
control character. **It may climb out of the folder with `..`**, on purpose: a shared
`../fonts/` or `../puppets/` folder serves several documents. Read against a folder,
`../../secret.png` therefore reaches outside it, and so does a symbolic link.

**To compile documents you do not trust, pass their files as a mapping.** Never pass a
folder. A mapping is how `scenet mcp` and the playground are sent files: they never read a
folder of their own. A picture's bytes reach the SVG under `embed=`, and the PDF. A file a
document named can also be quoted in an error message.

Every read file is recorded, and `compile_book_file(..., dependencies=set())` hands you the
set. `scenet build --watch` rebuilds when one of them changes.

## Performance

Measured on one core of a 2020s laptop:

| Work | Time |
|---|---|
| Importing `scenet` | Under a second: no optional extra is imported |
| Compiling a two-actor panel with one balloon | About 40 ms |
| Rendering it to SVG | About 7 ms |
| Compiling a five-panel page | About 0.1 s |

The first compile in a process is slower, because the shipped fonts and puppets are read. How
long a compile takes is driven by the balloon placement, which tries a fixed set of candidate
positions for each balloon. A panel with many lines of dialogue takes longer. A panel whose
balloons do not fit fails with `BalloonPlacementError`; it never searches without end.
