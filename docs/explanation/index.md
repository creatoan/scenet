# About Scenet

Why Scenet exists, what it does today, what changed in each release, and why its design is the
way it is. None of this is needed to use Scenet; it is here because the decisions are the
interesting part, and because a decision whose reasoning is lost gets reversed by accident later.

| | |
|---|---|
| [Why Scenet](why.md) | A score for comics: what it is, who performs it, and what that buys |
| [What Scenet does today](status.md) | Every feature, with the release it arrived in |
| [What's new](whats_new.md) | The CHANGELOG, release by release |
| [Design decisions](design_decisions.md) | The load-bearing choices, by theme, and what each one costs |
| [Prior art](prior_art.md) | What already exists, what was taken from it, and what was deliberately not used |
| [Design notes](design_notes/index.md) | Records of decisions being made, kept as they were |

## The three tiers, and why there are three

```
*.panel.yaml  →  IR (scene graph)  →  Panel Core (.core.json)  →  SVG
  authored         validated            resolved, numeric          emitted
```

The frontend never computes a coordinate. The solver never touches artwork. The emitter
never makes a layout decision.

The middle tier is the unusual one, and it is borrowed from Vega-Lite, which compiles a
high-level grammar into a lower-level one before emitting anything drawable. Panel Core is
a real, writable format rather than a hidden data structure, which buys three things:

- **A layout can be inspected** without reading SVG.
- **A layout can be hand-adjusted** and fed back in, so the compiler is a starting point
  rather than an authority.
- **Golden-file tests mean something.** Core changes only when the layout genuinely
  changes; SVG text changes when an attribute is reordered.

## What is deliberately not here

- **No generative image model**, anywhere in the pipeline. Not as a fallback, not for
  "polish". The whole claim of the project is that the output is explicable. The
  [exports for image models](../howto/export_for_image_models.md) keep that true: each is one
  more emitter reading Panel Core, as deterministic as the SVG, and what a reader feeds them to
  afterwards is outside Scenet, as a tracing over the SVG would be.
- **No A\* for balloon tails.** A tail is a short tapered stroke; grid pathfinding produces
  a jointed path that looks nothing like one drawn by hand.
- **No natural-language interpretation of prose.** A comic script's descriptions are
  preserved and never parsed. Guessing at "a rainy street corner" would produce a compiler
  whose output you cannot predict, which is the thing this is not.
- **No TypeScript reimplementation of the compiler.** The browser playground runs the real
  Python under WebAssembly; [Use the playground](../howto/use_the_playground.md#the-compiler-it-runs)
  says how.

Each of these is argued in full in [design decisions](design_decisions.md) and
[prior art](prior_art.md).

```{toctree}
:hidden:
:maxdepth: 1

why
status
whats_new
design_decisions
prior_art
design_notes/index
```
