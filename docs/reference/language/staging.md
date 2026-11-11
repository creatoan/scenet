# `staging`

<!-- facts: staging -->
How the cast stand to each other, as sentences: `alice left_of bob`. One relation each.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `@staging:` in a panel, or `staging:` in the front matter |
| Type | a list, each text or a mapping |
| Default | none |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `unknown-actor`, `ordering-cycle`, `reflexive-relation`, `figure-staging`, `dropped-relation`, `layout` |
| In the gallery | [Gaze steers balloons](../../gallery.md#gaze-steers-balloons), [Feet align, heads do not](../../gallery.md#feet-align-heads-do-not), [Depth and overlap](../../gallery.md#depth-and-overlap) |
<!-- /facts -->

A list of relations between {term}`actors <actor>`, each written as a sentence, `subject predicate
object`: `alice left_of bob`. This is a scene graph: the cast are nodes, these are the edges.
Predicates come from the spatial subset of the Visual Genome vocabulary rather than being invented
here, so a Scenet scene remains convertible to and from the scene-graph representations used
elsewhere in computer vision.

![Alice points at Bob and the two look at each other; their balloons keep clear of the space in front of their eyes](../../images/gallery/07-gaze.svg)

| Predicate | Effect | Strength |
|---|---|---|
| `left_of`, `right_of` | Fixes the order across the panel | Required |
| `in_front_of`, `behind` | Fixes the draw order, so the nearer figure covers the other | Required |
| `looking_at` | Turns the subject's {term}`gaze` toward the object -- who may be somebody heard [from off panel](script.md#sayoff_panel) | Required |
| `ground_shared_with` | Stands both on one ground line, so a short figure and a tall one stand on the same floor | Required |

Every actor a relation names must be in the cast (`unknown-actor`), except the object of a
`looking_at`, who may speak from off panel. A relation of an actor to itself means nothing and is
refused (`reflexive-relation`); `left_of` relations that loop are `ordering-cycle`. A
{term}`figure` a picture draws is never staged: a relation naming one is `figure-staging`.

In a scene, a panel shares the staging of the panel it is `over`, or of the scene's defaults. A
relation naming a member that panel leaves out with `null` is dropped from it, and a
`dropped-relation` note says so -- except `looking_at` somebody who now speaks from off panel,
which holds.

```{scenet-example}
cast:
  alice: {reference: alice}
  bob: {reference: bob, facing: left}
staging:
  - alice left_of bob
  - alice looking_at bob
  - bob looking_at alice
  - alice ground_shared_with bob
```

**See also:** [`cast.<id>.at`](cast.md#castidat), the weak wish a relation overrides;
[When constraints conflict](index.md#when-constraints-conflict).

## Why ordering must be explicit

`left_of` looks redundant next to `at: left_third`, but it is not. The layout engine is a **linear**
constraint solver, and "A and B must not overlap" is a *disjunction*: A is left of B, **or** B is
left of A. Linear solvers cannot express that choice.

So the language resolves it instead. By the time the solver runs, ordering is already decided, and
what reaches the solver is a linear system it can always solve. A `left_of` or `right_of` in
`staging` decides first. Where staging says nothing, figures stand in the order of their `at:`
anchors, and two at the same anchor by actor id, in code-point order, so `Bob` stands left of
`alice`. That is the same on every run, but seldom what was meant: when the order matters, state it
with `left_of`. This is the reason there is no unordered `beside` predicate, and why any future
construct must resolve its own ordering in the frontend.

## The mapping form

A relation is a sentence for people, and three keys for a program: `{subject: alice, predicate:
left_of, object: bob}` is the same relation as `alice left_of bob`, and the two forms mix in one
list. A program that writes Scenet -- a model, an exporter from a scene graph -- can write the
mapping without building a sentence and splitting it again. The three keys are the three words of
the sentence.

## `staging[].subject`

<!-- facts: staging[].subject -->
The actor id the relation is about.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `@staging[]:` in a panel, or `staging[]:` in the front matter |
| Type | text |
| Default | none: required |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `missing-field`, `unknown-actor`, `reflexive-relation` |
| In the gallery | [Staging, spelled out](../../gallery.md#staging-spelled-out) |
<!-- /facts -->

The actor the sentence is about: the one placed left of, in front of, or looking at, the other.

```{scenet-example}
cast:
  alice: {reference: alice}
  bob: {reference: bob, facing: left}
staging:
  - {subject: alice, predicate: left_of, object: bob}
```

**See also:** [`staging[].object`](#stagingobject).

## `staging[].predicate`

<!-- facts: staging[].predicate -->
How the subject stands to the object: `left_of`, `right_of`, `in_front_of`, `behind`, `looking_at` or `ground_shared_with`.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `@staging[]:` in a panel, or `staging[]:` in the front matter |
| Type | a name |
| Values | `left_of`, `right_of`, `in_front_of`, `behind`, `looking_at`, `ground_shared_with` |
| Default | none: required |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `missing-field`, `ordering-cycle` |
<!-- /facts -->

The relation itself, one of the six in the [table above](#staging). Each is required, and none
is reflexive. `right_of` is `left_of` the other way round, and `behind` is `in_front_of` the
other way round; write whichever reads as the panel does.

```{scenet-example}
cast:
  alice: {reference: alice}
  bob: {reference: bob}
staging:
  - {subject: bob, predicate: in_front_of, object: alice}
```

**See also:** [`staging[].subject`](#stagingsubject).

## `staging[].object`

<!-- facts: staging[].object -->
The other actor id. For `looking_at`, it may be somebody heard from off panel.

| | |
|---|---|
| Where | A `.panel.yaml`; a panel under `panels:`; beside `panels:`, for every panel. In a comic script: `@staging[]:` in a panel, or `staging[]:` in the front matter |
| Type | text |
| Default | none: required |
| Since | 0.1 |
| Diagnostics | `invalid-field`, `missing-field`, `unknown-actor`, `reflexive-relation` |
<!-- /facts -->

The other actor. For `looking_at`, the object may be somebody heard from off panel and drawn
nowhere: the subject turns toward the side of the frame the voice comes from.

```{scenet-example}
cast: {bob: {reference: bob, at: center}}
staging:
  - {subject: bob, predicate: looking_at, object: carol}
script:
  - say: {by: carol, text: "Over here!", off_panel: left}
```

**See also:** [`say.off_panel`](script.md#sayoff_panel).
