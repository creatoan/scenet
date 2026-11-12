# Glossary

The words the documentation uses, each in the sense Scenet gives it, and only in that sense. A
key card links a term here the first time it uses it. Where two words are close -- an actor and a
character, a scene and a sequence -- each entry says which is which.

```{glossary}
character
  Someone in the story, as a writer thinks of them: Alice, across every panel she is in. In a
  document, a character is an {term}`actor` in each panel, and is drawn as a {term}`puppet` or is a
  {term}`figure`. `alice` and `bob`, the puppets Scenet ships, are often called its characters; the
  reference calls them puppets.

actor
  Someone in a panel, by the id the author gives them under `cast:` -- `alice`, `guard_left`. Every
  other block names the cast by these ids. An actor is played by a {term}`puppet` or is a
  {term}`figure` a picture draws. See [`cast`](language/cast.md#cast).

cast member
  One entry of `cast:`: an {term}`actor`'s id, and who plays them. The actor is the person in the
  panel; the cast member is the entry that says who they are. A member is a {term}`puppet` or a
  {term}`figure`, never both, and a panel's cast is all one or the other.

puppet
  A character Scenet poses and draws: a skeleton in its own units, the parts drawn on it, nine
  landmarks, a face, and named poses and expressions. `alice` and `bob` ship with Scenet; one of
  your own is a `*.puppet.yaml` file. See [Puppet files](language/puppet.md).

figure
  Someone a supplied picture already draws, cast with `figure:`. Scenet letters a figure as it
  letters a puppet, from the picture's {term}`artwork contract`, and draws nothing of it. See
  [`cast.<id>.figure`](language/cast.md#castidfigure).

artwork contract
  The `*.art.yaml` file beside a supplied picture that says, in its pixels, where each figure's
  face, mouth and body is, and what lettering should stay off. See
  [Artwork contracts](language/artwork.md).

panel unit
  The unit every length in the language is in: a panel's size, a margin, a type size, a gutter. A
  panel unit is an SVG user unit, and printed, a tenth of a millimetre.

Panel Core
  The resolved, numeric form of a panel: every coordinate the compiler decided, as JSON. It is what
  the solver produces and the emitter draws, and what the golden tests hold. See
  [Panel Core](panel_core.md).

staging
  The relations between actors -- `alice left_of bob` -- which decide the order across the panel,
  who is in front, who looks at whom and who shares a floor. A scene graph: the cast are its nodes,
  the relations its edges. See [`staging`](language/staging.md#staging).

gaze
  The line of sight of a puppet, from its gaze origin toward whoever it is `looking_at`. Its pupils
  follow it, and balloons keep clear of the space in front of the eyes.

emanata
  What a comic draws *around* a character rather than on them -- sweat, dizziness, an oath, dust --
  in Mort Walker's word. Scenet's are the four {term}`marks`.

marks
  The four emanata a cast member can carry: `plewds`, `squeans`, `grawlixes` and `briffits`. See
  [`cast.<id>.marks`](language/cast.md#castidmarks). Not the module `scenet.emit.marks`, which lists
  everything a panel paints, for the emitters, and which the language never names.

scene
  A `*.scene.yaml` document: several panels in one file, written as a {term}`sequence`, laid out on
  {term}`page`s, or both. See [Scenes](language/scene.md).

sequence
  Panels read one after another, each saying only what changed from the one before with `over:`.
  It is how a scene writes its `panels:`, and a comic script's panels are one too. See
  [`over`](language/scene.md#over).

page
  Panels laid out on a sheet, in {term}`tier`s, as a scene's `pages:` writes them or a comic
  script's `PAGE` headings do. See [`pages`](language/page.md#pages).

book
  A scene compiled whole: every panel and every page of it, as `compile_book` returns them. The
  word is the Python API's; a document is never called a book.

retreat
  What the camera does when the cast cannot fit at the shot asked for: it steps back, keeping the
  shot's crop and widening the frame, and says so with the `camera-retreated` note. Panel Core
  records by how much as `camera.pullback`, the factor of the scale asked for, below 1 when it
  retreated. See [`camera.shot`](language/camera.md#camerashot).

mass
  One tonal shape of a backdrop: a kind of stuff -- `building`, `sky`, `wall` -- on a
  {term}`plane`, across a span of the panel. A place is a list of masses. See
  [`setting.masses`](language/setting.md#settingmasses).

plane
  How far back a mass sits: `foreground`, `near`, `mid` or `far`. The plane decides a mass's value,
  paler with distance, and its draw order; a `foreground` mass is drawn over the cast.

value ladder
  The greys a setting is drawn in, one per plane, from the foreground's to the atmosphere's, set by
  the hour. Colour, under `palette: tinted`, is drawn on the same rungs.

reading order
  The order a panel's words are read in: the script's order, which no balloon or caption may break
  by sitting above and to the left of the one before it -- above and to the right in a comic read
  right to left. It is also the order a page's panels are read in, and what a screen reader follows.

tier
  One row of a page: panels side by side, or columns of panels, read in turn. A page is tiers, top
  to bottom. See [`pages[].tiers`](language/page.md#pagestiers).

inset
  A small panel set into a corner of another and drawn over it, read before its parent or after it,
  as it says. See [`panels[].insets`](language/page.md#panelsinsets).

gutter
  The white between two panels: `gutter` between panels side by side, `tier_gutter` between tiers
  and between panels stacked in a column.

slant
  The lean of the gutters between a tier's panels, in degrees, which cuts its frames into four-sided
  shapes. See [`tiers[].slant`](language/page.md#tiersslant).

bleed
  Paper past the trim: the margin a printer cuts away. A page's `bleed` says how far its sheet runs
  past the trim; a panel that bleeds runs its frame out to that line, with no border there.

trim
  The size a printed page is cut to: `page.size`.
```
