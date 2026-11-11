# Puppet files

A {term}`puppet` of your own is a `*.puppet.yaml` file: a skeleton in its own units, the parts
drawn on it, the landmarks a shot crops at, a face, and the poses and expressions it can take, by
name. A [cast member](cast.md#castidreference) names it by its path, relative to the document, and
the compiler reads only what that cast names. What the solver sees of it, and why, is in the
[asset contract](../asset_contract.md#skeletal-puppets); this page has a card for every key.

Every fault in a puppet file is `puppet-file`: at the key that is wrong, in the puppet file, when the
document naming it is checked as a file, and on the line naming it otherwise. Its schema is
`scenet schema --puppet`, which an editor associates with `*.puppet.yaml`; what no schema can say --
landmarks increasing downward, a skeleton that is a tree, every joint a part or a pose names
declared -- `scenet check` does.

## A puppet file

Every card below points here. This is Pip, the gallery's puppet, five heads tall; the panel after it
casts Pip beside Alice.

```{literalinclude} ../../../examples/gallery/puppets/pip.puppet.yaml
:language: yaml
:caption: puppets/pip.puppet.yaml
```

```{scenet-example}
:beside: examples/gallery
:playground: 69-a-puppet-of-your-own.scene.yaml

camera: {shot: full_shot}
cast:
  alice: {reference: alice, at: left_third}
  pip: {reference: puppets/pip.puppet.yaml, pose: arms_up, expression: happy, at: right_third, facing: left}
staging: [alice ground_shared_with pip]
```

## `name`

<!-- facts: name -->
The name a cast member's `reference` uses.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The name the puppet goes by in messages and in Panel Core. A cast member names a puppet file by its
path, not by this, so two files may share a name without either shadowing the other or a shipped
puppet. See [the example](#a-puppet-file).

## `units_per_head`

<!-- facts: units_per_head -->
How many of the puppet's own units one head height is.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a number |
| Values | above 0 |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The puppet's own unit, against the one measure every shot is defined in: a head height. Offsets,
widths and radii are in the puppet's units; landmarks are in heads. A figure is as tall as its
`feet` landmark says, in heads -- Pip is five, Alice seven and a half. See
[the example](#a-puppet-file).

## `landmarks`

<!-- facts: landmarks -->
Each vertical body landmark, as a distance down from the top of the head, in head units: the crop lines a shot type names.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The nine crop lines a shot names, each as a distance down from the top of the head, in heads:
`head_top`, `eyes`, `chin`, `shoulders`, `chest`, `waist`, `mid_thigh`, `knees` and `feet`. All nine
are required, because any shot may crop at any of them, and they must increase downward. What each
shot does with them is in [Shot types](../shot_types.md). See [the example](#a-puppet-file).

## `landmarks.head_top`

<!-- facts: landmarks.head_top -->
The origin every other landmark is measured down from.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | `0` |
| Values | `0` |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The origin every other landmark is measured down from, so it is `0`. See
[the example](#a-puppet-file).

## `joints`

<!-- facts: joints -->
The skeleton, by joint name.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The skeleton, by joint name: a tree rooted at [`root`](#root), every joint reaching it through its
parents. A joint's pose angle rotates the bone arriving at it *and* everything below it, which is
what makes posing read naturally: bending `elbow_l` swings the forearm and takes the hand with it.
See [the example](#a-puppet-file).

## `joints.<joint>.parent`

<!-- facts: joints.<joint>.parent -->
The joint it hangs from. Left out for the root.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | none |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint this one hangs from. The root has none, and every other joint must reach the root: a
cycle, or a joint that hangs from nothing, is refused. See [the example](#a-puppet-file).

## `joints.<joint>.offset`

<!-- facts: joints.<joint>.offset -->
Where it is from its parent in the rest pose, in the puppet's own units.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | `[number, number]` |
| Default | `[0, 0]` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Where the joint is from its parent in the rest pose, `[x, y]` in the puppet's units, with y
downward. See [the example](#a-puppet-file).

## `root`

<!-- facts: root -->
The joint every other one hangs from.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | `root` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint every other one hangs from. It must be declared, with no parent. See
[the example](#a-puppet-file).

## `root_landmark`

<!-- facts: root_landmark -->
The landmark the root joint sits at.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a name |
| Values | `head_top`, `eyes`, `chin`, `shoulders`, `chest`, `waist`, `mid_thigh`, `knees`, `feet` |
| Default | `waist` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The landmark the root joint physically sits at. The skeleton is built outward from the root, while
landmarks are measured downward from the top of the head; this is what bridges the two frames.
Declared rather than assumed, because a puppet may root itself somewhere other than the waist. See
[the example](#a-puppet-file).

## `parts`

<!-- facts: parts -->
The shapes the body is drawn from, back to front.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a list of mappings |
| Default | none |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

What is drawn, back to front: each part a **bone**, a capsule between two joints, or a **blob**, a
disc at one. A part's keys say which kind it is: `from` and `to` make a bone, `at` makes a blob. A
part is checked only as the kind it is written as, and one that uses the keys of both kinds, or of
neither, is a single error saying so. See [the example](#a-puppet-file).

## `parts[].from`

<!-- facts: parts[].from -->
The joint the bone starts at.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint a bone starts at. It must be declared. See [the example](#a-puppet-file).

## `parts[].to`

<!-- facts: parts[].to -->
The joint the bone ends at.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint a bone ends at. It must be declared. See [the example](#a-puppet-file).

## `parts[].width`

<!-- facts: parts[].width -->
How thick it is drawn, in the puppet's own units.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a number |
| Values | above 0 |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

How thick a bone is drawn, in the puppet's units, with round caps at both ends. See
[the example](#a-puppet-file).

## `parts[].at`

<!-- facts: parts[].at -->
The joint it is centred on.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint a blob is centred on -- the head, or the chest of a round torso. See
[the example](#a-puppet-file).

## `parts[].radius`

<!-- facts: parts[].radius -->
Its radius, in the puppet's own units.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a number |
| Values | above 0 |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

A blob's radius, in the puppet's units. See [the example](#a-puppet-file).

## `parts[].offset`

<!-- facts: parts[].offset -->
Where its centre is from that joint, in the puppet's own units.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | `[number, number]` |
| Default | `[0, 0]` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Where a blob's centre is from its joint, before posing. See [the example](#a-puppet-file).

## `anchors`

<!-- facts: anchors -->
Named attachment points, such as `mouth` and `eyes`, each on a joint.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | none |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Named points that ride along with a joint. They are how the solver addresses anatomy without
knowing anatomy: a balloon's tail ends at `mouth`, and the line of sight starts at the
[gaze](#gazeorigin) origin, conventionally `eyes`. See [the example](#a-puppet-file).

## `anchors.<anchor>.joint`

<!-- facts: anchors.<anchor>.joint -->
The joint it rides along with.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint the anchor rides along with, through every pose. It must be declared. See
[the example](#a-puppet-file).

## `anchors.<anchor>.offset`

<!-- facts: anchors.<anchor>.offset -->
Where it is from that joint, in the puppet's own units, before posing.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | `[number, number]` |
| Default | `[0, 0]` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Where the anchor is from its joint, before posing. See [the example](#a-puppet-file).

## `face`

<!-- facts: face -->
Where the face is, and what is drawn in it.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The disc no balloon, caption or sound effect may cover, and what is drawn inside it. A circle rather
than a polygon: faces are roughly round, the test is cheap, and a slightly generous face only puts a
balloon a little further away, which is never wrong. What a face is drawn from is in the
[asset contract](../asset_contract.md#faces). See [the example](#a-puppet-file).

## `face.joint`

<!-- facts: face.joint -->
The joint the face is centred on: the head, unless the puppet says otherwise.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | `head` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint the face is centred on. See [the example](#a-puppet-file).

## `face.offset`

<!-- facts: face.offset -->
Where the face's centre is from that joint, in the puppet's own units.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | `[number, number]` |
| Default | `[0, 0]` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Where the face's centre is from its joint, before posing. See [the example](#a-puppet-file).

## `face.radius`

<!-- facts: face.radius -->
The face's radius, in the puppet's own units: the circle no balloon covers.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a number |
| Values | above 0 |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The face's radius, in the puppet's units: the circle lettering may not overlap. See
[the example](#a-puppet-file).

## `face.features`

<!-- facts: face.features -->
What is drawn inside the face, by feature. Empty for a plain round head.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | none |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

What is drawn inside the face, by feature: `brow_l`, `brow_r`, `eye_l`, `eye_r`, `nose` and
`mouth`, named after MPEG-4's facial feature groups. Each is optional -- a stylised character may
have no eyebrows -- but a pair comes in pairs, since a face with one eyebrow is a typo far more often
than it is a character. Pupils are not declared: they are placed inside each eye toward whoever the
character is looking at. A puppet with no features is drawn as it was before faces existed, a
filled circle, and may declare no expressions. See [the example](#a-puppet-file).

## `face.features.<feature>.joint`

<!-- facts: face.features.<feature>.joint -->
The joint the feature rides, practically always `head`.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | `head` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The joint the feature rides, which is the head for practically every face. See
[the example](#a-puppet-file).

## `face.features.<feature>.offset`

<!-- facts: face.features.<feature>.offset -->
Where the feature is from that joint, in the puppet's own units, before posing.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | `[number, number]` |
| Default | `[0, 0]` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Where the feature is from its joint, before posing, mirrored with the puppet. See
[the example](#a-puppet-file).

## `face.features.<feature>.size`

<!-- facts: face.features.<feature>.size -->
How big the feature is drawn, in the puppet's own units: an eye's radius, a brow's or a mouth's half-width, a nose's length.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a number |
| Values | 0 or more |
| Default | `0` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

What the number means depends on the feature: an eye's radius, a brow's or a mouth's half-width, a
nose's length. Zero draws the feature as a bare point. See [the example](#a-puppet-file).

## `gaze`

<!-- facts: gaze -->
Where the puppet's line of sight starts.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | each key's own |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Where the puppet's line of sight starts. Its direction is not declared: it comes from staging, so a
`looking_at` relation is enough and nobody computes an angle. See [the example](#a-puppet-file).

## `gaze.origin`

<!-- facts: gaze.origin -->
The anchor the line of sight starts at, conventionally `eyes`. It must be declared.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | text |
| Default | `eyes` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

The anchor the line of sight starts at, which must be one of the puppet's [anchors](#anchors). See
[the example](#a-puppet-file).

## `poses`

<!-- facts: poses -->
Named poses, each a set of joint angles.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | none: required |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Named poses, each a mapping of joint to angle, in degrees, that a cast member selects with
[`pose`](cast.md#castidpose). A joint a pose leaves out keeps its rest angle. `standing_neutral` is
required of every puppet, since it is what a member gets when it names no pose, and every joint a
pose names must be declared. See [the example](#a-puppet-file).

## `expressions`

<!-- facts: expressions -->
Named expressions, each a state of brow, eyes and mouth.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a mapping |
| Default | none |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

Named expressions, each a state of the brows, the eyes and the mouth, that a cast member selects
with [`expression`](cast.md#castidexpression). An expression is to features what a pose is to
joints, but a face deforms rather than rotating about bones, which is why it is a set of states and
not of angles. A puppet that declares any declares `neutral`, which a member gets unasked, and has
face features for them to move. See [the example](#a-puppet-file).

## `expressions.<expression>.brow`

<!-- facts: expressions.<expression>.brow -->
The brows' state.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a name |
| Values | `neutral`, `raised`, `lowered`, `angled_in`, `angled_out` |
| Default | `neutral` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

What the eyebrows are doing. `angled_in` puts the inner ends down, the anger brow; `angled_out` puts
them up, the sad or frightened one. Inner and outer are taken against the face's centre rather than
the page, so both survive mirroring. See [the example](#a-puppet-file).

## `expressions.<expression>.eyes`

<!-- facts: expressions.<expression>.eyes -->
The eyes' state.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a name |
| Values | `open`, `wide`, `narrowed`, `half`, `closed` |
| Default | `open` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

How open the eyes are. `half` is the heavy-lidded eye of boredom, distinct from `narrowed`, the
squint of anger or suspicion: one droops, the other is tightened. See [the example](#a-puppet-file).

## `expressions.<expression>.mouth`

<!-- facts: expressions.<expression>.mouth -->
The mouth's state.

| | |
|---|---|
| Where | A puppet file, a `.puppet.yaml`. Not in a comic script |
| Type | a name |
| Values | `neutral`, `flat`, `smile`, `grin`, `frown`, `open`, `small` |
| Default | `neutral` |
| Since | 0.13 |
| Diagnostics | [`puppet-file`](../diagnostics.md#puppet-file) |
<!-- /facts -->

What the mouth is doing. `grin` is an open smile, `smile` a closed one, and `small` the reticent
little mouth that does most of the work in a coy face. See [the example](#a-puppet-file).
