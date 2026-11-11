# Right to left

Manga, and comics in Arabic, Hebrew and Persian, are read from the top right. One key says
so, and it changes what reading decides, and nothing else.

## What you will make

![A page of 8 panels. Long shot. A street at night, in the rain. Hana, right, pointing, looking at Ken; Ken, left. Caption: Shinjuku. Ten past midnight. Hana: You came. Ken: You called. Medium close-up. A street at night, in the rain. Ken, centre. Ken, whispering: Is anybody else coming? Close-up. A street at night, in the rain. Hana, centre. Hana: Only us. Close-up. A street at night, in the rain. Ken, centre, surprised. Ken: Then why the umbrella? Full shot. A street at night, in the rain. Hana, centre; Ken, centre. Sound effect: KRAK. Hana: Because it is raining. Ken: It always is, here. Long shot. A street at night, in the rain. Ken, centre, sad. Caption: 00:10. Medium shot. A street at night, in the rain. Hana, centre. Mother, off panel: Hana? Where are you? Hana: Nearly home. Medium shot. A street at night, in the rain. Ken, centre, arms crossed. Ken: Go. I will wait.](../images/gallery/36-right-to-left.page-1.svg)

A manga page at night in the rain, read from the top right: Hana and Ken meet, a stack of
two close-ups beside a tall street panel with a clock set into its corner, and a last tier
that ends at the bottom left.

## One key for the whole document

[`direction`](../reference/language/direction.md) is `ltr`, the default, or `rtl`. It is the
whole document's, written once, beside `panels:`:

```{code-block} yaml
:caption: manga.scene.yaml

# A manga page, read from the top right.
#
# `direction: rtl` is the whole document's, written once beside `panels:`. The panels are
# written in reading order, as on any page, and read right to left: `arrival` is top right,
# the stack beside the tall street is read down before across, and the last tier ends at
# the bottom left. In each panel the balloons are read the same way -- never above and right
# of one before -- and the caption, given no zone, sits where reading starts.
#
# Nothing in the picture is mirrored: Hana stands where `at:` puts her and faces the way
# `facing:` says, the clock is in the corner its `at:` names, and the sound sits where the
# sound is. 37-left-to-right.scene.yaml is this page read left to right, figure for figure.

direction: rtl
page: {size: [1500, 2250], margin: 75, gutter: 30, tier_gutter: 45}
setting: {place: street, time: night, weather: rain}

pages:
  - tiers:
      - panels: [{use: arrival, width: 2}, door]
      - height: 1.4
        columns:
          - {panels: [asks, answers]}
          - width: 1.2
            panels:
              - use: street
                insets: [{use: clock, at: bottom_left, size: 0.4}]
      - panels: [phone, wait]

panels:
  arrival:
    camera: {shot: long_shot}
    cast:
      hana: {reference: alice, pose: pointing, at: right_third, facing: left}
      ken: {reference: bob, at: left_third}
    staging: [ken left_of hana, hana looking_at ken]
    script:
      - caption: {text: "Shinjuku. Ten past midnight."}
      - say: {by: hana, text: "You came."}
      - say: {by: ken, text: "You called."}

  door:
    camera: {shot: medium_close_up}
    cast:
      ken: {reference: bob, at: center}
    script:
      - say: {by: ken, text: "Is anybody else coming?", kind: whisper}

  asks:
    camera: {shot: close_up}
    cast:
      hana: {reference: alice, at: center, facing: left}
    script:
      - say: {by: hana, text: "Only us."}

  answers:
    camera: {shot: close_up}
    cast:
      ken: {reference: bob, expression: surprise, at: center}
    script:
      - say: {by: ken, text: "Then why the umbrella?"}

  street:
    camera: {shot: full_shot}
    cast:
      hana: {reference: alice, at: right_third, facing: left}
      ken: {reference: bob, at: left_third}
    staging: [ken left_of hana]
    script:
      - sfx: {text: KRAK, size: medium, prefer: top_center}
      - say: {by: hana, text: "Because it is raining."}
      - say: {by: ken, text: "It always is, here."}

  clock:
    camera: {shot: long_shot}
    cast:
      ken: {reference: bob, expression: sad, at: right_third}
    script:
      - caption: {text: "00:10"}

  phone:
    camera: {shot: medium_shot}
    cast:
      hana: {reference: alice, at: center, facing: left}
    script:
      - say: {by: mother, text: "Hana? Where are you?", off_panel: true}
      - say: {by: hana, text: "Nearly home."}

  wait:
    camera: {shot: medium_shot}
    cast:
      ken: {reference: bob, pose: arms_crossed, at: center}
    script:
      - say: {by: ken, text: "Go. I will wait."}
```

```bash
scenet build manga.scene.yaml
```

Here is the same page with `direction: ltr`, figure for figure:

```{code-block} yaml
:caption: western.scene.yaml

# The manga page of 36-right-to-left.scene.yaml, read left to right.
#
# The same document with `direction: ltr`, which is also what a page with no `direction`
# reads as. Put the two side by side: every panel draws the same figures, staged the same
# way, at the same size -- only where each panel sits on the page, and where its lettering
# sits in it, follows the direction.

direction: ltr
page: {size: [1500, 2250], margin: 75, gutter: 30, tier_gutter: 45}
setting: {place: street, time: night, weather: rain}

pages:
  - tiers:
      - panels: [{use: arrival, width: 2}, door]
      - height: 1.4
        columns:
          - {panels: [asks, answers]}
          - width: 1.2
            panels:
              - use: street
                insets: [{use: clock, at: bottom_left, size: 0.4}]
      - panels: [phone, wait]

panels:
  arrival:
    camera: {shot: long_shot}
    cast:
      hana: {reference: alice, pose: pointing, at: right_third, facing: left}
      ken: {reference: bob, at: left_third}
    staging: [ken left_of hana, hana looking_at ken]
    script:
      - caption: {text: "Shinjuku. Ten past midnight."}
      - say: {by: hana, text: "You came."}
      - say: {by: ken, text: "You called."}

  door:
    camera: {shot: medium_close_up}
    cast:
      ken: {reference: bob, at: center}
    script:
      - say: {by: ken, text: "Is anybody else coming?", kind: whisper}

  asks:
    camera: {shot: close_up}
    cast:
      hana: {reference: alice, at: center, facing: left}
    script:
      - say: {by: hana, text: "Only us."}

  answers:
    camera: {shot: close_up}
    cast:
      ken: {reference: bob, expression: surprise, at: center}
    script:
      - say: {by: ken, text: "Then why the umbrella?"}

  street:
    camera: {shot: full_shot}
    cast:
      hana: {reference: alice, at: right_third, facing: left}
      ken: {reference: bob, at: left_third}
    staging: [ken left_of hana]
    script:
      - sfx: {text: KRAK, size: medium, prefer: top_center}
      - say: {by: hana, text: "Because it is raining."}
      - say: {by: ken, text: "It always is, here."}

  clock:
    camera: {shot: long_shot}
    cast:
      ken: {reference: bob, expression: sad, at: right_third}
    script:
      - caption: {text: "00:10"}

  phone:
    camera: {shot: medium_shot}
    cast:
      hana: {reference: alice, at: center, facing: left}
    script:
      - say: {by: mother, text: "Hana? Where are you?", off_panel: true}
      - say: {by: hana, text: "Nearly home."}

  wait:
    camera: {shot: medium_shot}
    cast:
      ken: {reference: bob, pose: arms_crossed, at: center}
    script:
      - say: {by: ken, text: "Go. I will wait."}
```

![A page of 8 panels. Long shot. A street at night, in the rain. Ken, left; Hana, right, pointing, looking at Ken. Caption: Shinjuku. Ten past midnight. Hana: You came. Ken: You called. Medium close-up. A street at night, in the rain. Ken, centre. Ken, whispering: Is anybody else coming? Close-up. A street at night, in the rain. Hana, centre. Hana: Only us. Close-up. A street at night, in the rain. Ken, centre, surprised. Ken: Then why the umbrella? Full shot. A street at night, in the rain. Ken, centre; Hana, centre. Sound effect: KRAK. Hana: Because it is raining. Ken: It always is, here. Long shot. A street at night, in the rain. Ken, centre, sad. Caption: 00:10. Medium shot. A street at night, in the rain. Hana, centre. Mother, off panel: Hana? Where are you? Hana: Nearly home. Medium shot. A street at night, in the rain. Ken, centre, arms crossed. Ken: Go. I will wait.](../images/gallery/37-left-to-right.page-1.svg)

## What the compiler decided

**Reading moves; the picture does not.** Under `rtl`:

- a page's tiers are read from the right: `arrival` is at the top right, and the last tier
  ends at the bottom left;
- a stack of columns is read down, then right to left;
- in each panel, balloons are read from the right: a balloon may never sit above and to the
  *right* of one before it;
- a caption given no zone sits where reading starts, the top right;
- a voice from off panel with `off_panel: true` and no side is put high on the side reading
  starts from, and its tail takes the nearer side of the frame.

Nothing in the picture is mirrored. Hana stands where `at` puts her and faces the way
`facing` says; the clock is in the corner its `at` names; the sound sits where the sound
is. A side you name, `top_left` or `off_panel: left`, is a side of the panel, whichever way
it is read.

**A document is read one way.** A page read two ways has no order a reader could follow, so
`direction` may not be a panel's own: a panel under `panels:` that writes one is
[`panel-direction`](../reference/diagnostics.md#panel-direction):

```{scenet-example}
:gives: panel-direction

cast:
  hana: {reference: alice}
panels:
  first: {}
  second: {direction: rtl}
```

A comic script writes `direction: rtl` in its front matter, as [the manga
script](https://creatoan.github.io/scenet/playground/#example=64-a-manga-script.script) of
chapter 9 does.

## Try it

- [Right to left](https://creatoan.github.io/scenet/playground/#example=36-right-to-left.scene.yaml):
  the page you built. Change `direction: rtl` to `direction: ltr`, and compare it with the
  next one.
- [The same page, left to right](https://creatoan.github.io/scenet/playground/#example=37-left-to-right.scene.yaml):
  give the street's caption `prefer: top_left`, and see it stay there whichever way the page
  is read.

## Check it

```bash
scenet check manga.scene.yaml western.scene.yaml
```

```text
manga.scene.yaml: ok
western.scene.yaml: ok
```

## What you learned

- `direction: rtl` reads a whole document from the top right: pages, columns and balloons.
- It decides reading and nothing else: no figure, side or corner is mirrored.
- It is the document's, never one panel's.

## Where to go next

- The last chapter, [What Scenet tells you, and publishing](what_scenet_tells_you.md).
- The [`direction`](../reference/language/direction.md#direction) card, and [A manga,
  right to left](../howto/write_a_comic_script.md#a-manga-right-to-left) in the comic script
  guide.
