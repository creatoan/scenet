# Why Scenet

Scenet began from an analogy, and it still explains the design better than any list of
features. This page says what the analogy is, who it leaves the drawing to, and what it buys.
For what Scenet does, see [What Scenet does today](status.md).

## A score for comics

Music has notation. A score says what is played -- pitch, duration, dynamics -- and leaves the
sound to whoever plays it. Pictures have had nothing of the kind. SVG says *how to draw*, not
*what is depicted*: it is closer to a recording than to a score.

Scenet writes the score. A panel description says who is in the panel, how the camera frames
them, how they stand to each other and what they say, in the order it is read; a sequence, a page
or a comic script says the same of many panels. The compiler resolves that into
[Panel Core](../reference/panel_core.md), every position and size decided, and it is the score
that is the source: kept in version control, reviewed, diffed, compiled again.

## Who performs it

A score is played by someone else, and Scenet's has three kinds of performer:

- **Scenet's own renderers**: the SVG it writes for the screen, and the
  [PDF for print](../howto/print_a_comic.md), with its trim, its bleed and its lettering on the
  black plate. Both draw Panel Core and decide nothing.
- **An artist's art.** Scenet [letters over a picture](../howto/letter_over_your_own_art.md)
  someone painted, around [the figures it draws](../howto/letter_the_figures_in_your_art.md), or
  poses [characters of their own](../howto/add_your_own_character.md).
- **An image model**, fed by [the exports](../howto/export_for_image_models.md): each panel's
  pose, boxes, depth, mask and semantics. Scenet never runs a model; what is done with the exports
  is outside it, as a tracing over the SVG would be.

The score decides what is there and where; the performer decides how it looks. That division is
why the solver never sees artwork, only a geometric contract, so that any of the three can draw
the same layout.

## The style is the performer's

The **style layer** is what a performer adds that no score says: the line, the hatching, the
colour beyond the {term}`value ladder`, how a face is drawn,
what a picture means beyond who stands where. Scenet's own renderers draw in one plain style, and
the compiler has no style layer and is not meant to grow one. Style belongs to whoever performs
the score: an artist, an image model, or a renderer someone else writes.

## What a score buys

- **The same score gives the same picture**, byte for byte, on every machine and in every
  release that keeps the format: see [Determinism](../reference/language/index.md#determinism).
  That is what makes a panel a durable file rather than a prompt, and golden tests meaningful.
- **Every decision can be explained.** The compiler says what it decided that was not asked for,
  as [notes](../reference/diagnostics.md); the [debug overlay](../howto/debug_a_layout.md) shows
  the geometry it worked against; and Panel Core can be read, edited and drawn again.
- **Mistakes can be checked by a machine**, and fixed by whoever made them: a person in an
  editor, or [a model](../howto/drive_from_a_model.md) reading its own errors.
- **Nothing is generated.** No image model is involved anywhere, and no prose is interpreted: a
  comic script's descriptions are kept, never parsed.

## Free to implement

Scenet is [0BSD](https://github.com/creatoan/scenet/blob/main/LICENSE), which imposes no
conditions at all. To be explicit about the language too: anyone may build their own compiler,
editor, renderer or tool for it, in any project, commercial or otherwise, without permission or
attribution. A notation is only worth having if it is not owned.

The choices behind all this are argued in [Design decisions](design_decisions.md), and what each
was taken from, or deliberately not, in [Prior art](prior_art.md).
