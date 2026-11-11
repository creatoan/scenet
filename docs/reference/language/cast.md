# `cast`

A mapping of actor id to properties. Ids are chosen by the author and referenced everywhere else.

![Four characters side by side in the four shipped poses: standing, arms crossed, pointing and hands on hips](../../images/gallery/11-poses.svg)

**In the gallery:** [Poses and facing](../../gallery.md#poses-and-facing), [Ten expressions](../../gallery.md#ten-expressions) and [A face](../../gallery.md#a-face).

| Key | Type | Meaning |
|---|---|---|
| `reference` | asset name, or a `.puppet.yaml` path | Which puppet to pull from the library, or a [puppet file of your own](#a-puppet-of-your-own), relative to the document |
| `figure` | figure name | Instead of `reference`: a figure the panel's picture draws, as its [artwork contract](../asset_contract.md#artwork-contracts) names it. See [Figures the picture draws](setting.md#figures-the-picture-draws) |
| `pose` | pose name | A named joint configuration declared by that puppet |
| `expression` | expression name | A named face declared by that puppet |
| `marks` | list of marks | Emanata drawn around the character: `plewds`, `squeans`, `grawlixes`, `briffits` |
| `at` | anchor | Horizontal placement preference |
| `facing` | `left`, `right` | Which way the figure is turned |

`at` accepts `left_third`, `center`, `right_third`, `left_edge`, `right_edge`. It is a
**preference, not a command** — see [conflicts](index.md#when-constraints-conflict).

`expression` is selected by name exactly as `pose` is, because a face is the same kind of thing as a
body: a small closed set of arrangements a character can be in. The shipped puppets declare ten —
`neutral`, `happy`, `laughing`, `coy`, `bored`, `scared`, `sad`, `angry`, `shouting`, `surprise` —
and it defaults to `neutral`. They are a **drawing convention**, the small closed set of faces comics
actually draw, and not a claim about what a person feeling anger looks like. What a face is made of,
and how to give your own puppet one, is in the [asset contract](../asset_contract.md#faces).

A character's pupils follow whoever they are `looking_at`. Nothing else about the face depends on the
rest of the panel, and nothing about the face changes the layout: to the solver a face is still one
disc that balloons may not cover.

## `marks`

```yaml
cast:
  alice: {reference: alice, expression: angry, marks: [grawlixes, plewds]}
```

![Alice and Bob in four panels with marks drawn round them: sweat, an oath, dizziness, and dust where one has gone](../../images/gallery/23-emanata.strip.svg)

**In the gallery:** [Emanata](../../gallery.md#emanata).

`marks` are what a comic draws *around* a character rather than on them. The vocabulary is Mort
Walker's, from *The Lexicon of Comicana*, and it is closed:

| Mark | What is drawn | What it says |
|---|---|---|
| `plewds` | Droplets flying off the head, mostly off the back | sweating: effort, heat, nerves |
| `squeans` | Little starbursts and circles in an arc over the head | dizzy, drunk, or sick |
| `grawlixes` | A spiral, a star, a bolt and a `#` over the head | swearing |
| `briffits` | Puffs of dust at the feet, behind the figure | gone, fast |

They are a **list**, not a second `expression:`, because they compose: a character can be angry *and*
sweating. Order does not matter, and a mark listed twice is an error. They need nothing from the
puppet — every mark is placed from the face circle, the facing and the feet — so every character can
have every mark. In a scene, `marks: []` under `over:` clears the ones a panel inherited, because
lists replace rather than merge.

Emanata are drawn **outside** the head, in the space balloons are placed in, so unlike a face they
matter to the layout — but only softly:

- **They never move anybody.** They stay out of the hull, so staging, the camera and every figure are
  exactly where they would be without them.
- **A balloon prefers not to cover them.** Each mark has a zone the solver reads as a cost, weighted
  above covering a body, with no forgiveness for the speaker. A crowded panel still compiles: a balloon
  covers a mark before it fails.
- **The camera makes no room for them.** It frames by body landmarks, so a tight shot — or the head of
  the tallest character, which the frame is fitted to — can crop marks over the head, and a shot that
  cuts at the waist leaves briffits below the frame. `scenet build` reports any mark that runs off the
  panel.

At a wide framing a plewd is a dot: below a head size, each mark collapses to a dot where it would
have been drawn, and a character too small to have a face has no marks at all. See the
[asset contract](../asset_contract.md#emanata).

An oath written in a balloon — `"@#$%!"` — is dialogue, and already works. `grawlixes` is the other
convention, the symbols over a head.

A cast member may instead be a figure the panel's picture draws, written `figure:`; see
[Figures the picture draws](setting.md#figures-the-picture-draws) for what applies to it and what does not.

## A puppet of your own

`alice` and `bob` are shipped. A character of your own is a `*.puppet.yaml` file — a skeleton, the
parts drawn on it, a face, and the poses and expressions it can take — and a cast member names it by
its path:

```{code-block} yaml
:caption: Part of a panel beside puppets/pip.puppet.yaml

cast:
  alice: {reference: alice}
  pip:   {reference: puppets/pip.puppet.yaml, pose: waving}
```

![A page of five panels: Pip, a puppet five heads tall from a file beside the document, beside Alice on the docks at dusk](../../images/gallery/69-a-puppet-of-your-own.page-1.svg)

**In the gallery:** [A puppet of your own](../../gallery.md#a-puppet-of-your-own).

- **A `reference` that ends in `.puppet.yaml` is a file**; any other names a shipped puppet. A path
  is never a name, so no file shadows `alice` or `bob`.
- **The path is read as a font's is**: relative to the folder the document is in, wherever `scenet`
  was run from, with `/` between folders, never absolute — so a document and its puppets travel
  together, and `../puppets/` reads a folder of characters several documents share. Text compiled
  with no file behind it names a puppet only when its caller says which folder it belongs to, or
  hands the file over with it.
- **Only what the cast names is read**, once however many members it draws.
- **`pose` and `expression` are the file's own** names, held to it exactly as a shipped puppet's are.
- **A puppet of another height shares the ground only when staging says so**, with
  `ground_shared_with`: framed alone, each figure's head is under the top of the panel.
- **Panel Core records the reference as written**, for the actor and for the camera composed on
  it. Nothing else of the file reaches the output but the figure drawn.

A file that is absolute, missing or not a puppet is `puppet-file`: in the puppet file, at the key
that is wrong, when the document is checked as a file, and on the line naming it otherwise. In the
[playground](https://creatoan.github.io/scenet/playground/), **Puppet…** adds a file to the
document's `puppets/` folder for as long as the tab is open; over MCP it is sent in `files`. What the
file holds is in [Add your own character](../../howto/add_your_own_character.md), and the gallery's
`69-a-puppet-of-your-own.scene.yaml` casts one.

`reference`, `pose` and `expression` are validated against the puppet library, not just against the
language's own grammar — a misspelled pose is a perfectly good string as far as the grammar is
concerned, so nothing at that level can tell `pointing` from `smirking`. `scenet check` resolves the
library and reports an unmatched name as `unknown-puppet`, `unknown-pose` or `unknown-expression`,
each naming the field and, for `pose` and `expression`, listing the names that puppet does declare.
A puppet file is read to resolve them the same way. See [`scenet check`](../cli.md#scenet-check).
