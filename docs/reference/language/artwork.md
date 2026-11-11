# Artwork contracts

A supplied picture can draw its own people. Where each face, mouth and body is, the panel never
says -- it never writes a coordinate. The picture's **artwork contract** does: a file beside the
picture, named after it, `art/p01-street.art.yaml` beside `art/p01-street.png`, measured once in
the picture's own pixels and committed with it. A cast member names a figure it declares with
[`figure:`](cast.md#castidfigure). What the solver does with it is in the
[asset contract](../asset_contract.md#artwork-contracts); this page has a card for every key.

The contract is read only for a panel whose cast names a figure, and its geometry goes through the
picture's [`fit`](setting.md#settingfit), so a face is excluded exactly where the picture draws it,
under `cover` and `contain` alike. `scenet check` reads it without running the solver, and reports a
missing or malformed one as `artwork-contract`: in the contract itself, at the line of the fault,
when the document is checked as a file; at the line naming the picture when it is checked as text,
as in the playground or over MCP. `scenet build --debug` draws every face, mouth, body and keep-out
over the panel, which is how a contract is checked against its picture.

## An artwork contract

Every card below points here: the gallery's contract for `art/figures.png`, a station platform at
night with three people on it, and a panel that casts two of them.

```{literalinclude} ../../../examples/gallery/art/figures.art.yaml
:language: yaml
:caption: art/figures.art.yaml
```

```{scenet-example}
:beside: examples/gallery
:playground: 35-figures.scene.yaml

panel: {size: [900, 600]}
setting: {image: art/figures.png, time: night}
cast:
  ana: {figure: ana}
  ben: {figure: ben}
script:
  - say: {by: ana, text: "Is that ours?"}
  - say: {by: ben, text: "No."}
```

## `size`

<!-- facts: size -->
The picture's size in pixels, `[width, height]`, as it was measured. It must be the picture's own.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | `[number, number]` |
| Default | none: required |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

The picture's size in pixels, as the contract was measured against it. It must be the picture's
own: a contract measured on another size of the picture would put every face somewhere else, so a
mismatch is refused rather than scaled. See [the example](#an-artwork-contract).

## `figures`

<!-- facts: figures -->
Each figure the picture draws, by the name a cast member's `figure` gives it. Every face here is kept clear of lettering, cast or not.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | a mapping |
| Default | none |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

**Everybody the contract declares is in the picture.** A face nobody cast is as forbidden to
lettering as a speaker's, and a body as costly to cover: a crowd of five can be declared and two of
them cast. A figure a panel casts and the contract does not declare is `unknown-figure`, listing
the ones it does. See [the example](#an-artwork-contract).

## `figures.<name>.face`

<!-- facts: figures.<name>.face -->
The figure's face: a disc no balloon, caption or sound effect may cover.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | a mapping |
| Default | none: required |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

The face, as a disc. A contract declares no gaze, so nothing keeps a balloon out of a figure's line
of sight; the face is all lettering keeps clear of. See [the example](#an-artwork-contract).

## `figures.<name>.face.center`

<!-- facts: figures.<name>.face.center -->
The face's centre, `[x, y]` in the picture's pixels, from its top left.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | `[number, number]` |
| Default | none: required |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

The face's centre, in pixels from the picture's top left; it must lie on the picture. See
[the example](#an-artwork-contract).

## `figures.<name>.face.radius`

<!-- facts: figures.<name>.face.radius -->
How far the face reaches, in pixels. Generous is safer than tight: no lettering overlaps this disc, and a tail stops on its edge.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | a number |
| Values | above 0 |
| Default | none: required |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

Generous is safer than tight: no balloon may overlap the disc at all, and a tail stops on its edge.
A `cover` crop that pushes part of a face out of the panel keeps clear whatever part is in view. See
[the example](#an-artwork-contract).

## `figures.<name>.mouth`

<!-- facts: figures.<name>.mouth -->
Where the tail of a line the figure speaks ends, or the place a sound it makes comes from, in pixels. Left out, a tail aims at the face's centre.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | `[number, number]` |
| Default | none |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

Where a tail ends, and where a sound the figure makes comes from. A tail to a mouth that a `cover`
crop cuts away ends on the frame, aimed at it, and `scenet build` says so in a note. See
[the example](#an-artwork-contract).

## `figures.<name>.body`

<!-- facts: figures.<name>.body -->
The figure's silhouette, a polygon in pixels, which a balloon pays to cover: half as much over its own speaker.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | a list of `[number, number]` |
| Default | none |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

A polygon of at least three points, in pixels, simple -- no edge crossing another. Covering a
figure's body costs a balloon, and covering its own speaker's costs half, as with a puppet. See
[the example](#an-artwork-contract).

## `keep_out`

<!-- facts: keep_out -->
Regions lettering should stay off, each a polygon in pixels: a sign, a hand, what the panel is about. A cost, not a rule.

| | |
|---|---|
| Where | An artwork contract, the `.art.yaml` beside its picture. Not in a comic script |
| Type | a list of a list of `[number, number]` |
| Default | none |
| Since | 0.12 |
| Diagnostics | `artwork-contract` |
<!-- /facts -->

**Keep-out regions** are ground lettering pays to cover, weighted as emanata are -- a sign, a hand,
what the panel is about -- and never forbidden: a crowded panel covers one before it fails. Each is
a simple polygon on the picture. See [the example](#an-artwork-contract).
