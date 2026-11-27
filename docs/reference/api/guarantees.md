# Guarantees

What the Python API promises beyond each function's own entry: what stays stable, what is
deterministic, what is safe to share between threads, which files a compile reads, and how
long it takes. What is safe with input from someone you do not trust is the
[security model](../../explanation/security_model.md).

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
  changes only as [the format](../panel_core.md) says: a minor version adds fields a reader may
  leave out, a field an old document lacks reads as its default, and anything else bumps the
  major of `CORE_FORMAT_VERSION`.
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
working directory, or a font installed on the machine. No absolute path reaches any output. Nor does a file name: a font is named by its own `name` table, or, with none, by the first twelve characters of the digest of its bytes, so the same font has the same family whichever document or earlier compile it came through.

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
| `_BY_CONTENT` in `scenet.lettering` | The fonts documents declared lately, by the digest of their bytes | 32 entries, the one used longest ago let go first (`scenet.lettering.FONT_CACHE_ENTRIES`); a face let go and read again is the same font, named and measured alike | Yes. Two threads that miss together each parse the font, and one entry wins. Both are the same font |
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
parallelism, use processes. A server compiling documents from many users holds at most 32
of the fonts they declare at once.

## Which files a compile reads

A document can name files beside it: a lettering font, a picture to letter over and its artwork contract, a puppet file. Where they are read from depends on `base=`, and on the function, and every one must stay inside the **root**:

| You pass | A file the document names is read from | It must stay inside |
|---|---|---|
| A path: `compile_file`, `compile_book_file`, or `source=` on a function that takes text | The document's folder | `root=`; else the nearest folder at or above the document's that holds a `scenet.toml`; else the document's folder |
| `base=Path(...)` | That folder | `root=`, or else that folder |
| `base={"fonts/a.ttf": b"..."}`, a mapping | That mapping, and never the disk | The mapping |
| Text, with neither | Nowhere: a document that names a file is refused | — |

A path that a document writes is relative: not absolute, without a backslash or a control character, and **it may not leave the root**. `../fonts/a.ttf` is read only when the root holds the folder above the document, and a symbolic link is followed only to a file inside it. A path that leaves is refused under the rule of the file it names (`font-file`, say), before anything outside the root is opened, so the refusal says nothing of what is there. Only a regular file is read: a folder, a device or a pipe is refused. A `root=` that does not hold the document is refused too.

`scenet build`, `scenet check` and `scenet build --watch` take `--root DIR`. To share a folder of fonts or puppets between documents, put an empty `scenet.toml` at the top of the project, or pass `--root` that folder; `--root /` reads anything your account can, as 0.13 did. A `scenet.toml` holds nothing yet: a key in it is refused, kept for a later version.

Each file is read up to a bound, and one larger is refused by its size before it is read: 8 MiB for a document, a puppet file or an artwork contract, 128 MiB for a picture, 64 MiB for a font. The bounds are {py:mod}`scenet.limits`. A PNG decoded for print is inflated no further than the size its header gives, and one whose data says otherwise is refused.

**To compile documents you do not trust, pass their files as a mapping**, or pass `root=` a folder that holds nothing but theirs; do not rely on the default root, which a `scenet.toml` above their folder widens. A mapping is how `scenet mcp` and the playground are sent files. The playground never reads a folder; `scenet mcp` reads a folder only when it was started with `--root`, and that folder is then the root. A picture's bytes reach the SVG under `embed=`, and the PDF; no message quotes the contents of a file the document names.

Every read file is recorded, and `compile_book_file(..., dependencies=set())` hands you the set; `scenet build --watch` rebuilds when one changes, or when a `scenet.toml` does.

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

What a document can ask for is bounded too: every size, count and length in the language has a
limit, listed in [the language's limits](../language/limits.md), and a document past one is the
finding `limit` before anything is compiled. `scenet.limits.Limits` holds them; a host may pass a
tighter one to `scenet.mcp.build_server(limits=...)`.
