# `description`

<!-- facts: description -->
What the panel shows, in words, for a reader who cannot see it. Carried into the SVG as its accessible name and never interpreted. Not inherited: a panel drawn `over:` another is a different picture. Left out, one is generated from the shot, the setting and the cast.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`. In a comic script: the panel's prose, or `@description:` |
| Type | text |
| Default | none |
| Since | 0.12 |
| Diagnostics | `invalid-field`, `unknown-key` |
| In the gallery | [A description](../../gallery.md#a-description) |
<!-- /facts -->

What the panel shows, in words, for a reader who cannot see it: one paragraph of prose. Runs of
whitespace, line breaks included, are read as one space.

![Late at night, Bob points at something off to the side, beaming, while Alice watches him, bored](../../images/gallery/45-a-description.svg)

**It is carried, never interpreted.** Nothing is drawn from it -- the rain comes from `setting`,
the exasperation from `expression` -- exactly as a comic script's prose is never read by the
compiler. What it is for is accessible output: it is the panel's accessible name, the first thing
a screen reader says about it, before what is said in it, in
[reading order](script.md#script).

In a [comic script](../../howto/write_a_comic_script.md#prose-is-never-interpreted) a panel's
prose is its description, unless an `@description:` directive says something else. Left out,
accessible output says what the panel holds -- the shot, the setting, and who is where, doing
what.

**It describes one panel**, so it is never inherited:

- written beside `panels:`, where every panel would inherit it, it is refused as `unknown-key`;
- a panel drawn `over:` another does not take its parent's. It is a different picture, and the
  parent's words would be wrong to exactly the reader who cannot see that they are.

An empty one is refused, since it would describe the panel with nothing; leave it out instead.
Like dialogue, it may not hold a character an SVG cannot hold.

```{scenet-example}
cast:
  alice: {reference: alice, at: left_third, expression: bored}
  bob: {reference: bob, at: right_third, facing: left, pose: pointing}
description: Bob points at something out of the frame. Alice has heard it all before.
```

**See also:** [Make accessible output](../../howto/make_accessible_output.md),
[`direction`](direction.md#direction), which orders who the generated description names first.
