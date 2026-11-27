# MCP server

`scenet mcp` serves the compiler over the [Model Context Protocol](https://modelcontextprotocol.io/),
targeting revision [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28). It is
the one way of driving Scenet from a model that closes the loop: the model writes a document,
validates it, reads findings that name the rule, the line and the fix, corrects its own output,
and renders it — with no person copying error text from a terminal into a chat window.

Starting it, transports and exit status are in the [command-line reference](cli.md#scenet-mcp);
connecting a client is in [driving Scenet from a model](../howto/drive_from_a_model.md). This
page is the tools.

## Tools

Five, deliberately, and a sixth, `build`, only when the server was started with `--output`. Each
extra tool is more for a model to read before it can choose one.

| Tool | Takes | Returns |
|---|---|---|
| `get_spec` | `section` (optional) | The spec pack, one part at a time, as Markdown |
| `list_puppets` | `files`, and with `--root` `paths` and `folder` (all optional) | Every shipped character, then every puppet file sent, with each pose and expression it declares |
| `validate` | `source`, `syntax`, `deep`, `files`, and with `--root` `folder` | `{valid, findings}`, every finding at once; `valid` when none is an error |
| `compile` | `source`, `syntax`, `files`, and with `--root` `folder` | Each panel's notes and [Panel Core](panel_core.md), then each page's [Page Core](panel_core.md#page-core) |
| `render` | `source`, `syntax`, `live_text`, `aria`, `files`, `mono`, `conditioning`, and with `--root` `folder` | A summary, then one SVG per panel, then one per page, then each panel's exports for image models when asked |
| `build` | `source`, `name`, `syntax`, `files`, `pdf`, `strip`, `core`, `conditioning`, `live_text`, `mono`, `aria`, `embed_images`, and with `--root` `folder` | Each file written into the output folder: its path, `file://` URI, media type, size and SHA-256, never its contents; then the notes. Listed only with `--output` |

The five are annotated **read-only, idempotent and closed-world**: none writes a file, reaches
the network, or answers differently on a second call. A client can run them without asking.
`build` is annotated `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true` and
`openWorldHint: false`: it adds files and never replaces one with other contents, and a second
identical call changes nothing. `render` never writes, with or without `--output`.

### Arguments

`source`
: The whole document, **as text**. Not a path: a remote client shares no file system with the
  server, and one calling convention for both transports is one less thing to get wrong.

`files`
: The files the document names — a [picture behind the cast](language/setting.md#settingimage),
  a [lettering face](language/lettering.md#lettering), a [puppet of its own](language/cast.md#castidreference)
  — by the path it writes, each as base64: `{"art/p01.png": "iVBORw0KGgo…"}`. They stand in for
  the document's folder, which the server never reads, and are read in memory, so nothing is
  written to the server's disk. A path is held to a document's own rules — relative, `/` between
  folders — and a value that is not base64 is a tool error naming it. Left out, a document that
  names a file gets `image-file`, `font-file` or `puppet-file`, as text with no folder does
  anywhere. A cast of [figures a picture draws](language/cast.md#castidfigure)
  also needs the picture's artwork contract, beside it and named after it —
  `{"art/p01.png": "…", "art/p01.art.yaml": "…"}`; without it the finding is `artwork-contract`,
  at the line naming the picture. Given to `list_puppets`, each `*.puppet.yaml` among them is
  listed after the shipped puppets, by its path — what `reference` writes — and one that is not a
  puppet is a tool error saying why. On a server started with `--root`, `files` is one way to send
  a file and the folder is the other, and the two are exclusive in one call: see
  [Folders](#folders).

`folder`, `paths`
: Only on a server started with `--root`; the schemas of a server without it do not have them,
  and a call that sends one is refused. See [Folders](#folders).

`name`
: Only on `build`: what the files are called, an [identifier](language/identifiers.md) that is not a
  name Windows keeps for a device, such as `con` or `nul`. See [The build tool](#the-build-tool).

`syntax`
: `yaml` (default) for a `*.panel.yaml` or `*.scene.yaml` document — a top-level `panels:` key
  is what makes it a scene, so there is no third value — or `script` for a comic script.

`section`
: One of `preamble`, `language`, `shot-types`, `comic-script`, `characters`, `diagnostics`,
  `schema`, `gallery`. Omitted, `get_spec` returns the preamble — what Scenet is, the
  check-and-fix loop, the mistakes generators make most — and a list of the other parts.

`deep`
: Also run the solver, as `scenet check --deep` does, to catch `layout` and
  `balloon-placement` failures the cheap pass cannot see.

`live_text`
: Emit selectable `<text>` instead of glyph outlines, as `scenet build --live-text` does. About
  a third the size, which matters inside a model's context, but it depends on the viewer having
  a matching font.

`aria`
: `true` (default): each panel is an image a screen reader can read, named with what it shows and
  then everything said in it, in reading order, as `scenet build` writes it — which also gives a
  model reading the SVG back the panel's words. `false` leaves that out, as `--no-aria` does.

`mono`
: `true` draws every value as its grey and ignores a palette's colour, as `scenet build --mono`
  does: byte for byte what the same document draws with `palette: mono`. `false` (default) draws
  each colour the palette gave.

### Findings

`validate` returns every finding, in source order:

| Field | |
|---|---|
| `rule` | Stable rule id, such as `scenet/unknown-actor` — the [same catalogue](diagnostics.md) `scenet check` reports |
| `level` | `error`, which stops the document compiling, or `note`, a house limit such as a balloon over the words a publisher asks for, which does not |
| `message` | What is wrong, naming the offending construct |
| `fix` | What to do about it |
| `help_uri` | Where the rule is explained: its [entry](diagnostics.md), with a document that gives it and the same document fixed |
| `where` | Path to the offending value, such as `script.0.say.by`; empty for the whole document |
| `line`, `column`, `end_line`, `end_column` | 1-based |

A document whose only findings are notes is `valid`: it compiles as it is. Weigh each note,
and fix it if the panel should read better.

`compile` and `render` refuse a document that does not compile with a **tool error**, whose
text lists the same findings with the same fixes, errors only. A solver failure is located as well as a
syntax one: only a failure pays for the deep check that locates it, so a document that compiles
is compiled once.

The findings travel in two forms: as structured content for clients that read it, and as text
for the many hosts that show a model only a result's text.

### Rendering

`render` returns a short text summary — how many panels, and the compiler's notes — then one
embedded resource per panel, `scenet://panels/NAME.svg`, of type `image/svg+xml`. A document
with `pages:` gets one more per page after them, `scenet://pages/N.svg`. The SVG is
**byte-identical** to what `scenet build --embed-images` writes for the same document: a picture
it is drawn over is written into it as a `data:` URI, since whoever reads the SVG has no folder to
find a linked one in. A document with no picture is byte-identical to plain `scenet build`.

With `conditioning: true`, each panel's [exports for image
models](../howto/export_for_image_models.md) follow the pages, five per panel and exactly as
`scenet build --conditioning` writes them: `scenet://panels/NAME.pose.json`, `.boxes.json` and
`.semantics.json` as `application/json`, `.depth.svg` and `.mask.svg` as `image/svg+xml`. A
parameter rather than a sixth tool, which keeps the server at five.

It is never sent as an image content block. Hosts forward image blocks to the model, and model
APIs that accept images do not accept SVG, so an image block would fail the whole turn instead
of showing a picture. There is no PNG either: rasterising would put a renderer in the runtime
dependencies for one tool.

## Instructions

On connecting, the server sends instructions that many hosts hand straight to the model. They
say what to do rather than what the server is: read `get_spec` first, cast only what
`list_puppets` lists, validate until clean, and pass text rather than paths — with the bytes
of any picture, font or puppet file the document names in `files`, and of the artwork contract
beside a picture whose figures the cast names. A puppet file of the document's own needs no tool
either: `list_puppets` given the same `files` describes it. Figures have no tool of their own,
which keeps the server at five: their names are the contract's, and `get_spec`'s characters part
says where they come from.

## Bounds and transport security

Each tool call runs in a worker process of its own and is stopped — the process is killed, so
the work stops too — once it has run for `scenet mcp --timeout` seconds, 60 by default, or once
its client cancels it. The call is answered with an error that says so, and the server goes on
serving; the next call has a fresh worker, and a worker's start is not counted in any call's
time. A call that fails to compile is explained by the same worker, under the same clock: the
cheap check first, and the deep one only when the cheap one finds nothing. At most four calls
run at once; a further one waits for a free worker. `build_server()` runs calls in process
unless given `timeout=`.

Over Streamable HTTP the server:

- keeps no session, as revision 2026-07-28 removed protocol-level sessions: a request needs no
  `Mcp-Session-Id`;
- listens on a loopback address unless `--allow-remote` says otherwise;
- answers only a `Host` that names it, and refuses any other with 421;
- answers only an `Origin` of its own — `http://localhost`, `http://127.0.0.1` or
  `http://[::1]` at its own port — or one `--allow-origin` names, and refuses any other with
  403, as the specification requires of every server, so that no web page reaches it by DNS
  rebinding. A request with no `Origin`, which no browser sends, is answered;
- refuses a request body over 16 MiB with 413, before reading it.

It authenticates nobody and encrypts nothing. Expose it beyond the machine only behind something
that does both: a reverse proxy on the same machine reaches it on `127.0.0.1` and needs no
`--allow-remote`.

Started with neither `--root` nor `--output`, a document sent to the server, and the files it
names, are read in memory: a call opens no file but the package's own, and writes none, and a
path in either that climbs out of the files sent is refused like any other path that leaves its
root. `--root` and `--output`, which give a server on stdio a folder, are the only way that
changes; both are refused over Streamable HTTP, exit 2.

## Folders

A chat model can write a document and cannot write a 2 MB picture as base64, and cannot repeat a
page of SVG to hand it over. So a server started over stdio may be given two folders, once, on
its command line; whoever configures the client chooses them, and nothing a document or a model
says widens them:

```bash
scenet mcp --root ~/comics --output ~/comics/out
```

Each names an existing folder, or the command exits 2. It is resolved once, at start-up.

`--root DIR`
: The root of every document a call sends as text. Its files are read from `DIR/<folder>`, where
  `folder` is a new argument (default `.`): `art/p01.png` with `folder` set to `chapter-1` is
  `chapter-1/art/p01.png` under the root. `folder` is held to a document's path rules —
  relative, `/` between folders — and to the root. `..`, an absolute path and a symbolic link
  that leads out are refused, under the rule of the file named, before anything outside the root
  is opened; only regular files are read, each up to the limits of
  [every file a document names](language/limits.md). `files` and the disk are exclusive in one
  call: with `files` the mapping is the root, as without `--root`, and `files` with `folder` is
  refused, naming both. Nothing lists the folder: the model asks the user what a file is called.

`--output DIR`
: Lists the `build` tool, which writes there.

A server's instructions and its tools' descriptions say which of the two is active, so a model
knows whether it can name a file or write one. The `fix` of a finding about a picture, a font, a
puppet file or an artwork contract says which of `files` or the root applies, and names no
`scenet` command: with text alone, send the file in `files`; with `files` sent, the path must be
one of its keys; with a root, put the file at `<folder>/<path>` under the server's folder, or send
it in `files`.

## The build tool

`build` writes into the output folder what `scenet build -o OUTPUT/<name>.svg` writes, with the
same flags, under the same names — `<name>.svg`, `<name>.<panel>.svg`, `<name>.page-<n>.svg`, and
`<name>.pdf` with `pdf` — and byte for byte the same files. A picture the SVG links is copied
beside it, unless `embed_images` writes it into the SVG.

It returns no file's bytes. A short text block names each file by its path in the output folder
with its size; `structuredContent` carries each file's `path`, `uri` (a `file://` URI),
`mime_type`, `size` and `sha256`, then the `notes`; and every file is also a `resource_link`. The
server answers no `resources/read`: the host shares the disk.

### output-exists

`build` never replaces a file whose bytes differ. Every file is checked before any is written, and
one already there with other contents is a finding, `output-exists`, that names the file and says
to choose another `name`: nothing is written. A file already there with the same bytes counts as
written, so a second identical call succeeds and changes nothing. A model makes the call,
possibly at the request of a document it was handed, and the page it replaces might exist
nowhere else.

### Notes

What the compiler decided that the document did not ask for, and what print leaves out, come
back as `notes`: findings of level `note`, each naming its panel in `where`. A decision the
compiler names, such as `camera-retreated`, has that name as its rule; any other note's rule is
`scenet/build-note`.

## Keeping stdout clean

On the stdio transport, stdout *is* the protocol stream, and one stray line corrupts it. Nothing
in the server goes through the code `scenet build` uses to print `wrote` and `note:` lines; the
compiler's notes travel inside tool results instead. The SDK additionally points file descriptor
1 at stderr while it serves, which catches a stray `print` from a dependency. The test suite
drives a real stdio session against the installed command, so neither can regress quietly.

## From Python

The tools are plain functions, importable without starting a server:

```python
from scenet.mcp import list_puppets, validate

report = validate("""
cast:
  alice: {reference: alice}
script:
  - say: {by: bpb, text: Hello}
""")

assert not report.valid
finding = report.findings[0]
assert finding.rule == "scenet/unknown-actor"
assert finding.where == "script.0.say.by"
assert (finding.line, finding.column) == (5, 15)

assert [puppet.name for puppet in list_puppets().puppets] == ["alice", "bob"]
```

`build_server()` returns the configured server without running it, for a host that wants to
connect in process or mount it inside a server of its own.

## Publishing

[`server.json`](https://github.com/creatoan/scenet/blob/main/server.json) at the repository root
describes the server for the [official MCP registry](https://github.com/modelcontextprotocol/registry),
which holds metadata only and points at the package on PyPI. Ownership of the
`io.github.creatoan/scenet` namespace is proved by the `mcp-name` marker in the README, which
becomes the PyPI project description. Listing a release is done by a workflow; see
[releasing](../maintainer/releasing.md#listing-in-the-mcp-registry).
