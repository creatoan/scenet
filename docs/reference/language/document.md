# A document's own keys

Every document -- a panel, a scene, a comic script's front matter, a puppet file, an artwork
contract -- may say a few things of itself at its top: the language it is written in, the schema an
editor checks it with, and whatever a tool keeps about it. A panel and a scene may also say which
kind of document they are. None of these is a panel's: beside `panels:`, they are not defaults any
panel inherits, and on a panel under `panels:` each is `unknown-key`.

```{scenet-example}
scenet: 1
$schema: https://creatoan.github.io/scenet/schemas/scene.schema.json
kind: scene
meta: {title: The wait, written-by: Scenet contributors}
cast:
  alice: {reference: alice, at: left_third}
  bob: {reference: bob, at: right_third}
panels:
  wide: {}
  close: {over: wide, camera: {shot: close_up}}
```

And any key that starts with `x-` is an [extension](#extension-keys), which Scenet ignores wherever
it is written.

## `scenet`

<!-- facts: scenet -->
The language the document is written in: the major version of the Scenet language, an integer, which is not the version of the package. Left out, it is 1. A document written for a later language is refused, with nothing else said of it.

| | |
|---|---|
| Where | The top of any document: a `.panel.yaml`, a `.scene.yaml`, an artwork contract, a puppet file. In a comic script: the front matter only |
| Type | a whole number |
| Values | 1 |
| Default | none |
| Since | 0.14 |
| Diagnostics | [`invalid-field`](../diagnostics.md#invalid-field), [`language-version`](../diagnostics.md#language-version) |
<!-- /facts -->

The language is Scenet's own version number, separate from the version of the package: a release
that only adds to the language, or fixes the compiler, keeps it. It is written as a whole number,
never quoted: `scenet: '1'` is text, and `invalid-field`, as are `scenet: 1.5` and `scenet: true`.
JSON has one kind of number, so `scenet: 1.0` is the number 1 to a JSON Schema, and to Scenet too.
It is written in [the page's example](#a-documents-own-keys).

A document written for a later language than this Scenet reads is not one of this language with
mistakes in it. So nothing else in it is checked, and `scenet check` says one thing,
`language-version`:

```text
x.panel.yaml:1:9: language-version: written for Scenet language 2; this is language 1. Compile it with a later Scenet, one that reads language 2
```

## `$schema`

<!-- facts: $schema -->
The JSON Schema an editor checks the document with: a path or a URL. Scenet reads its own schema, whatever this says.

| | |
|---|---|
| Where | The top of any document: a `.panel.yaml`, a `.scene.yaml`, an artwork contract, a puppet file. In a comic script: the front matter only |
| Type | text |
| Default | none |
| Since | 0.14 |
| Diagnostics | [`invalid-field`](../diagnostics.md#invalid-field) |
<!-- /facts -->

An editor that reads JSON Schema, VS Code's YAML extension among them, takes `$schema` as the
schema to check the document with. The four Scenet publishes are in
[`editor/schemas/`](https://github.com/creatoan/scenet/tree/main/editor/schemas). Scenet itself
reads its own, whatever this names. It is written in [the page's example](#a-documents-own-keys).

## `meta`

<!-- facts: meta -->
What a tool keeps about the document: a mapping of anything, which Scenet reads nothing of yet. A later version of the language gives it a shape.

| | |
|---|---|
| Where | The top of any document: a `.panel.yaml`, a `.scene.yaml`, an artwork contract, a puppet file. In a comic script: the front matter only |
| Type | a mapping |
| Default | none |
| Since | 0.14 |
| Diagnostics | [`invalid-field`](../diagnostics.md#invalid-field), [`duplicate-key`](../diagnostics.md#duplicate-key) |
<!-- /facts -->

A mapping of anything: a title, an author, a tool's notes. Nothing reads it yet, and a later version
of the language will give it a shape, so keep to a mapping. Anything that is not a mapping is
`invalid-field`. It is written in [the page's example](#a-documents-own-keys).

## `kind`

<!-- facts: kind -->
Which kind of document it is: `panel`, or `scene` for one with `panels:`. A document is read by its shape whether it says or not, so one that says it is a scene and has no `panels:` is refused, as is the other way round. `book` is kept for a later version of the language.

| | |
|---|---|
| Where | A `.panel.yaml`; the top of a `.scene.yaml`. In a comic script: the front matter only, where it is `scene` |
| Type | a name |
| Values | `panel`, `scene`, `book` |
| Default | none |
| Since | 0.14 |
| Diagnostics | [`invalid-field`](../diagnostics.md#invalid-field), [`document-kind`](../diagnostics.md#document-kind), [`not-yet`](../diagnostics.md#not-yet) |
<!-- /facts -->

A document is read by its **shape**, whether it says its kind or not: one with `panels:` is a
scene, and one without is a panel. `kind` confirms it, so a document that says one thing and is
another is `document-kind`, at the `kind`: `kind: scene` with no `panels:`, or `kind: panel` with
them. A comic script is always a scene. `kind: book` is kept for a later version of the language,
which reads books, and is `not-yet`. It is written in [the page's example](#a-documents-own-keys).

## `include`

<!-- facts: include -->
Kept for a later version of the language, which will read one document into another. Refused until then.

| | |
|---|---|
| Where | A `.panel.yaml`; the top of a `.scene.yaml`. In a comic script: the front matter only |
| Type | nothing yet: only `null`, which is not writing it |
| Default | none |
| Since | 0.14 |
| Diagnostics | [`not-yet`](../diagnostics.md#not-yet) |
<!-- /facts -->

Kept for a later version of the language, which will read one document into another. Until then it
is `not-yet`, where it is written: a key that did nothing would lose what it holds without a word.
`include: null` is the key not written, as `null` is for any key. No document can write it yet,
so [the page's example](#a-documents-own-keys) does not.

## `defaults`

<!-- facts: defaults -->
Kept for a later version of the language. Refused until then: in a scene, a key written beside `panels:` is a default every panel inherits.

| | |
|---|---|
| Where | A `.panel.yaml`; the top of a `.scene.yaml`. In a comic script: the front matter only |
| Type | nothing yet: only `null`, which is not writing it |
| Default | none |
| Since | 0.14 |
| Diagnostics | [`not-yet`](../diagnostics.md#not-yet) |
<!-- /facts -->

Kept for a later version of the language, and `not-yet` until then. Today a default of a scene is
any key written beside `panels:`, which every panel inherits, as in [the page's example](#a-documents-own-keys).

## Extension keys

A key that starts with `x-`, in lower case, is an **extension**: a tool writes it to annotate a
document, and Scenet ignores it and everything under it. It may be written in any mapping of any
document -- at the top, in a panel, in a cast member, in a script entry, in a page -- and the JSON
Schemas take it everywhere too, holding anything.

```{scenet-example}
x-generator: storyboard-tool 3
cast:
  alice: {reference: alice, x-colour-note: red coat}
script:
  - say: {by: alice, text: Over here!}
    x-take: 2
```

`X-note`, in a capital, is no extension: it is a key like any other, and `unknown-key` unless the
language has it. In a comic script, a directive `@x-note: ...` is an extension too, and is neither a
directive nor the panel's prose.

So no [identifier](identifiers.md) starts with `x-`. Under `cast:` or `panels:`, a key that does is
an extension, never an actor or a panel: nothing can stage it, place it on a page, or be drawn
`over` it. Written as a value, `by: x-ray` is `invalid-identifier`. Any other mapping whose keys an
author chooses -- a puppet's poses, an artwork contract's figures -- is the same: an `x-` key there
is an extension, never a pose or a figure.
