# Scene documents

A `.scene.yaml` holds several panels. Each is written under `panels:`, by a name, with the keys a
`.panel.yaml` takes; and anything written beside `panels:` is a default every panel inherits. A
panel may also be written `over` another, and state only what differs from it. A scene may then lay
its panels out on [pages](page.md#page-and-pages).

![Three panels of Alice and Bob, the camera moving in from a full shot to a close-up as Bob answers her, each panel written as what changes from the one before](../../images/gallery/12-sequence.strip.svg)

What a panel is, then, is three layers, each over the one before: the scene's defaults, the panel it
is `over` (and that panel's own parent, as far as the chain goes), and the panel's own keys. A chain
that names a panel that does not exist, or comes back to where it started, is `composition`.

## How a panel inherits

Two rules, and they are worth knowing precisely, with a third that takes something away:

- **Mappings merge recursively.** Overriding one actor's pose leaves the rest of that actor, and
  every other actor, alone: `cast: {alice: {pose: arms_crossed}}` keeps Alice's `reference` and
  `at`.
- **Lists replace wholesale.** Give a panel its own `staging:` and you replace the parent's entirely
  -- there is no appending. A list has no keys to merge on, and guessing at identity by position
  would be worse than a clear rule. So `marks: []` clears the marks a member inherited.
- **`null` leaves something out**; see [below](#null-leaves-something-out).

Two keys do not follow the rules. A [`description`](description.md#description) says what one
picture shows, so it is never a default and never inherited: beside `panels:` it is `unknown-key`,
and a panel drawn `over` another writes its own or has one generated. And
[`direction`](direction.md#direction) is only ever the document's: on a panel it is
`panel-direction`, since a sequence is read one way throughout.

## `null` leaves something out

A `null` removes what a panel would have inherited, as JSON Merge Patch
([RFC 7386](https://www.rfc-editor.org/rfc/rfc7386)) has it -- "If the value is null, remove". It
reaches whatever lies beneath, the panel it is `over` and the scene's defaults alike, at any depth
reached through mappings: `camera: null`, `cast: {bob: null}`, `setting: {place: null}`.

A cast member who goes takes every staging relation that names them along, since none can hold in a
panel they are not in, and `scenet check` notes each one as `dropped-relation`. All but one, while
the member left out is heard from off panel: `bob looking_at carol` still holds when Carol speaks
`off_panel` in that panel. A `null` inside a list is left as it is: a list is replaced whole, never
merged into.

```{scenet-example}
cast:
  alice: {reference: alice, at: left_third}
  bob: {reference: bob, at: right_third}
staging: [alice left_of bob]
panels:
  both: {}
  alone:
    cast: {bob: null}
```

## `panels`

<!-- facts: panels -->
Panels in reading order. Each may inherit from another with `over`.

| | |
|---|---|
| Where | A `.scene.yaml`. In a comic script: the script's `PANEL` headings |
| Type | a mapping |
| Default | none |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `unknown-key`, `duplicate-key`, `composition` |
<!-- /facts -->

The panels, in reading order: the order they are written in is the order a strip draws them and a
screen reader reads them, unless pages lay them out. A name is text, as an actor id is, and is
written once: two panels of one name are `duplicate-key`. Everything a `.panel.yaml` takes may be
written under each, and `over` besides.

```{scenet-example}
panel: {size: [700, 500]}
cast: {alice: {reference: alice}}
panels:
  first: {camera: {shot: full_shot}}
  second: {camera: {shot: close_up}}
```

**See also:** [`pages`](page.md#pages), [Compile a sequence](../../howto/compile_a_sequence.md).

## `over`

<!-- facts: over -->
Name of a panel to inherit from. Only the differences need stating: mappings merge recursively and lists replace.

| | |
|---|---|
| Where | A panel under `panels:`. In a comic script: `@over:` in a panel |
| Type | text |
| Default | none |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `composition` |
| In the gallery | [A sequence](../../gallery.md#a-sequence) |
<!-- /facts -->

The keyword is borrowed from [OpenUSD's composition arcs](../../explanation/prior_art.md), where
`over` means exactly this: name a parent, then state the difference. A comic script writes it as an
`@over:` directive. The parent need not be earlier in the document, nor on a page: a panel may
exist only to be inherited from.

```{scenet-example}
panels:
  establishing:
    camera: {shot: full_shot}
    cast:
      alice: {reference: alice, at: left_third}
      bob: {reference: bob, at: right_third, facing: left}
    staging: [alice left_of bob]
  reaction:
    over: establishing
    camera: {shot: close_up}
```

**See also:** [How a panel inherits](#how-a-panel-inherits),
[One panel over another](../../howto/write_a_comic_script.md#one-panel-over-another).
