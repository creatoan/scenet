# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the version is below `1.0.0`, minor releases may break things. That is what being
below 1.0 means.

## [Unreleased]

### Added

- **The gallery shows what the checker and the compiler tell you (#240).** A new group,
  *What Scenet tells you*, has an example for every note: `word-limit`, `panel-count`,
  `looks-like-dialogue` and `dropped-relation` from `scenet check`, and from the compiler a
  camera that retreats, a tail that bends around a face, a mouth a picture's fit crops away,
  marks cut off by the frame, an inset over a face, a slant through a face, and a regular face
  standing in for the italic and bold italic ones a document did not name (examples 53 to 62,
  and 10). Each says what to change to make its note go away, and ends with a commented line
  that, uncommented, is an error located on that line. The manifest declares the notes each
  example gives under `notes:`, and the tests hold every example to exactly those: eight older
  examples gave `camera-retreated` without anybody checking, and now say so.
- **Every compile note has a name.** `CompileResult.compile_notes` gives each note with what
  kind it is — `camera-retreated`, `curved-tail`, `cropped-mouth`, `cropped-marks`,
  `inset-covers-face`, `slant-cuts-face`, `italic-stand-in` or `bold-italic-stand-in` — as a
  `CompileNote`, exported beside `CompileResult`. `notes` still gives the sentences, word for
  word: match on the name, which stays when a sentence is reworded.
- **The playground lists what `scenet check` notes**, each under its rule and a click away
  from its line, as an error is, then what the compiler noted, under its name. A check's note
  was a squiggle in the editor and nothing more.
- **The gallery writes every construct of the language, and a test reads it against the
  schemas (#239).** Eleven examples, 42 to 52: a font of your own (Comic Neue, in
  `examples/gallery/fonts/` with its licence), a sound pulled toward a zone from its source,
  the five zones between the corners, a description, staging spelled out as subject, predicate
  and object, a mass in front of the cast, a document of two pages with an inset read after its
  panel, leaving somebody out with `null`, a look at a voice from off panel, puppets that become
  a picture's figures, and a JPEG. `scripts/make_gallery_photo.py` paints the JPEG and encodes it
  itself. The coverage test now walks each document beside the published panel and scene
  schemas, so a word in a comment no longer passes it: every property, enum value, form and
  signed number they offer must be written, as must the removals the docs teach, every pose and
  expression of every puppet, a second page, and both picture formats.

- **The playground's gallery is a guided tour (#237).** It opens on a new example,
  `38-tour.scene.yaml`: one page lettered over both gallery pictures in colour, with posed
  puppets, figures a picture draws, a locale caption, a thought, emanata, a sound effect and an
  inset. The menu groups the examples by theme, Previous and Next walk them in that order, and
  under the editor each says in a sentence what it shows, with a link to the page of the
  documentation that explains it. `#example=<file>` opens a gallery example by name, a link
  that does not go stale as a `#src=` share link does when the example changes.
- **The playground shows every output (#238).** Depth, Mask, Pose, Boxes and Semantics tabs
  show the exports for image models of every panel of any document, side by side under each
  panel's name, made only while one of them is open. A **Screen reader** tab lists what a
  screen reader is given: every image and group the SVG names, nested, with its words. A
  **Files** tab shows the files beside the document: the gallery's pictures and artwork
  contracts, and the fonts and pictures you add. An **Output** menu letters with live text, as
  `--live-text` does, and shows a document of several panels as its pages, a strip, or each
  panel on its own. A document of several panels downloads its exports as one ZIP, each file
  named as `scenet build --conditioning` names it.
- **`scenet.emit.preview` draws the pose and the boxes** to be looked at: each actor's skeleton
  in OpenPose's colours, and each box labelled with its phrase in its region's colour in the
  mask. `scenet.emit.export.conditioning_archive` puts every panel's exports in one ZIP, the
  same bytes on every run and every platform.
- **The gallery manifest gains `groups:`, `start:`, and `group:`, `summary:` and `doc:` on
  every entry**, and its titles are short names. Entries are only ever appended, as its header
  now says: a playground draft remembers its example by position. The spec pack prints each
  example's summary under its title.

### Changed

- **A note in the playground is styled as information**, neutral and marked ℹ, not as an
  orange warning: nothing is wrong when the compiler says what it decided.
- **The gallery's CI job drops the notes the manifest declares before code scanning**
  (`scripts/check_gallery.py`), so the examples that give a note on purpose open no alert. An
  error, or a note nobody declared, is still uploaded and still fails the job.

### Fixed

- **The how-to on debugging a layout named two of the compiler's notes**; there are eight,
  now each in a table with what to do about it.
- **The scene schema accepts a `null` wherever `settle` applies one** (#239): `camera: null` on
  a panel of figures over one with a camera, as the docs teach, was underlined in an editor and
  compiled. Any key a scene reaches through mappings may now be `null`; a list entry is still
  whole. The panel schema is unchanged.
- **A member left out with `null` keeps the look at them while heard from off panel** (#258).
  `cast: {carol: null}` dropped the panel's own `bob looking_at carol`, with a
  `dropped-relation` note, even while Carol spoke `off_panel` there, and her `off_panel: true`
  ended on the side nearer her balloon. As with a comic script's `CAROL (OP)`, Bob now turns
  toward her side and her line ends on the side she was written to stand on; every other
  relation that names her still goes. In a script, `@cast: {CAROL: null}` beside `CAROL (OP)`
  is no longer refused as drawing her.

**Upgrading from 0.12.0.**

- **The depth map of every panel with a ground, floor, water or ceiling changes once** (#227),
  and with it the bytes of its `.depth.svg`: regenerate golden depth maps of your own. Nothing
  else changes, Panel Core included.

### Added

- **The tinted ladder** (#244), the first step of the colour policy: the value ladder in
  colour, each value with the OKLab lightness of the grey on its rung, so that a panel drawn in
  it is, in monochrome, the panel drawn in greys. Each hour has a shadow hue at the foreground and
  an atmosphere hue at the sky, and the rungs move between them. `TINTED` in
  `scenet.solve.backdrop` is generated from those two ends by `scripts/make_palette.py`, and
  `scripts/setting_sheet.py --palette tinted` draws every place and weather in it.
- **`palette: mono | tinted`** (#244), what a panel is drawn in. `tinted` draws every value on the
  ladder (the masses of a setting, the veil and the rain) in its twin colour. `mono`, the default,
  is what every panel already was. It is written where `lettering` is: at the top of a panel, beside
  `panels:` for every panel, on one panel for that panel alone, or in a comic script's front matter
  or as `@palette:`. A panel may have its own, for a flashback in grey on a page in colour. Panel Core
  keeps every grey where it was and adds `colour` beside it (`fall_colour` for rain), with `palette`
  at the top, all left out in `mono`: no existing Core, SVG or export changes. Every decision is
  still made on the grey, so a tinted Core with its colours taken out is the mono one. The pose,
  boxes, depth and mask exports are the same in every palette, and the semantics names the palette
  when it is not `mono`. `Palette` is exported, and `colour_for` gives a grey's twin.
- **`scenet build --mono`** (#244) draws a tinted document as a black-and-white edition, without
  editing it: every value as its grey, and every panel, page and strip byte-identical to what the
  same document writes with `palette: mono`. `render`, `render_page`, `render_pages` and
  `render_strip` take `mono=True`, MCP `render` takes `mono`, and `PanelCore.as_mono()` gives the
  panel with its colours taken back out, which is the mono Core.
- **`tone: warm`** (#244), the yellow `locale` caption that #28 left out for want of a colour policy.
  Its value is the `day` row's atmosphere rung, `#eeeeee`, taken by index as `pale` and `ink` are,
  and it is lettered in ink. Under `palette: tinted` its box is drawn in that grey's twin, the pale
  yellow `#fef0a1`, which the ink reads on at 16:1. In `mono` it is the grey, which is what a
  black-and-white reprint does to a yellow caption. Panel Core records the yellow as the caption's
  `colour`, beside `fill`, and leaves it out in `mono`. `paper`, `pale` and `ink` stay neutral in
  every palette.
- **Colour in the gallery and the reference** (#244). Two gallery examples, *Every hour in colour*
  and *A flashback in grey*, join *A yellow caption*. The language reference has a `palette`
  section with both pages as pictures, and `warm` in the `tone` table. Panel Core's reference
  documents the colour keys, and the design decisions record why colour is a twin of value.

### Changed

- **`lightness` and `contrast_ratio` refuse a colour** (#244) with a `ValueError`, rather than
  answer for it with a formula that is exact only for a neutral grey. Every decision the compiler
  makes from a value is made on the grey.
- **A ground, floor or stretch of water recedes in the depth export** (#227), instead of standing
  as one flat grey that a depth model reads as a wall. Each is a straight vertical ramp from its own
  step at the horizon to the farthest figure's step at the bottom edge, white when every figure
  is; a ceiling is the same ramp running up to the top edge. A flat surface's inverse depth is
  linear in screen height, so the straight ramp is the shape perspective gives. The ramp is never
  darker than its plane's step, so the painter's order holds, and never paler than a figure
  standing on it. A ground in the foreground plane stays flat, and so does every other kind. Each
  ramped region's paint names its step as the fallback. A hand-edited Core with no horizon has
  each surface recede from its own far edge.

## [0.12.0] - 2026-10-29

**Upgrading from 0.11.1.**

- **A font path written with `\` between folders is refused**, on Windows as everywhere else:
  write `/`. So is one holding a control character, which used to crash `build` and `check`.
- **`conflicting-setting` covers a picture too**: an `image` beside a `place`, `masses` or a
  `horizon`. Its SARIF description and help say so; a place beside masses is reported exactly
  as before. A panel that inherits a place and names an image is refused the same way; it
  writes `place: null` beside the image.
- **A comic script's prose is now read**, as its panel's description. A line of it holding a
  control character an SVG cannot hold, which used to pass unnoticed, is reported at that
  line as `invalid-field`. `description` in a script's front matter is refused.
- **Every Panel Core gains `description`, and each balloon, caption and sound effect a
  `label`.** Nothing else in it moves, and `format_version` stays 1: a Core without them is
  still valid and writes back byte for byte, but golden Core files of your own will need
  regenerating once. 0.11 refuses the new keys.
- **Every Panel Core gains `camera`; each actor `joints`, `features` and, when it looks at
  somebody, `looking_at`; a backdrop of masses `time` and, for a named place, `place`** (#72).
  Nothing else in it moves, no SVG changes, and `format_version` stays 1: a Core without them is
  still valid and writes back byte for byte, but golden Core files of your own will need
  regenerating once. Every gallery Core was compared with its 0.11.1 golden and differs by these
  keys alone. A panel whose cast a picture draws has no `camera`, and 0.11 refuses the new keys.
- **A balloon over its own speaker's body costs what it always should have** when the actor id
  is not the puppet's name (`ALICE: {reference: alice}`, `carol: {reference: alice}`). Such a
  speaker was charged as a bystander, so balloons drifted away from them. Three gallery
  panels letter differently, each balloon now beside its speaker: regenerate golden Cores of
  your own that cast an actor under another name.
- **`CaptionEvent.prefer` is `None` when it was not written**, where it used to read `top_left`:
  an unwritten zone is where reading starts, which the solver decides from `direction`. A caption
  is placed exactly where it was. Code reading it from the Python API takes `None` as `top_left`
  for a left-to-right panel.
- **`CastMember.reference` may be `None`**, for a member that is a figure a picture draws, and
  `CompileResult.camera` is `None` for a panel whose cast is all figures. Code reading either
  from the Python API narrows them first; `PanelIR.puppets()` gives every puppet's reference.
  A member that names neither a puppet nor a figure is reported exactly as before.
- **Every SVG's bytes change once**, to carry what a screen reader reads: a `role` and a `<title>`
  per panel, and `aria-hidden` on a page's own shapes. Nothing is drawn
  differently and lettering stays outlines. `--no-aria` (`aria=False`) gives back exactly the
  SVG written before, for a pipeline that post-processes it; debug overlays are unchanged.

### Added

- **Export a panel's staging for image models** (#72): `scenet build --conditioning` writes five
  files beside each panel's SVG — the pose as OpenPose COCO-18 JSON, a phrase and a box per
  figure as GLIGEN takes them, a depth map (stepped grey planes in painter's order, white near),
  an instance mask under the panel's own ids, where a character keeps its colour across panels
  unless another in the same panel has the same hue, and the semantics: camera, setting, cast
  with each character's mask colour, and lettering, as structure and never as a prompt. No model runs in Scenet: each is one more
  emitter reading Panel Core, text, JSON or SVG, byte-identical like the rest, and nothing is
  rasterised. The pose names left and right as OpenPose does, by the subject's side; a point
  outside the panel, an ear, or a joint a puppet does not name is `0, 0, 0`. Figures a picture
  draws have boxes and masks and no pose; a picture is the far plane; a panel read right to left
  exports the same pose, boxes, depth and mask. `render_conditioning` and `Conditioning` join
  `scenet.__all__`; MCP `render` takes `conditioning` (still five tools); the playground offers
  the five downloads for a one-panel document. See the how-to, "Export a panel's staging for
  image models".
- **`direction: ltr | rtl`, which way a comic is read** (#68): `rtl` for manga, read from the
  top right. It is the comic's progression, not its text's, and EPUB's word for it. Written once
  for the whole document — at the top of a panel, beside `panels:`, or in a comic script's front
  matter — and inherited by every panel; a panel's own, and a script's `@direction:`, are the new
  rule `panel-direction`. The editor's schema offers it. Panel Core and Page Core record it when it
  is `rtl`; a left-to-right Core is byte-identical and `format_version` stays 1.
- **A panel read right to left is lettered from the top right.** A balloon or caption may never sit
  above and right of one before it; a caption with no `prefer`, and a voice from off panel with no
  side named, start top right; every tiebreak between equal placements is mirrored, so the mirror
  image of a panel is lettered as the exact mirror of the original; and a generated description
  names the cast from the right. Nothing in the picture moves: figures, gaze, tails and sound
  effects are byte-identical, and `prefer:`, `at:` and named sides keep meaning places on the panel.
  The debug overlay says "read right to left".
- **Pages and strips read right to left.** Under `direction: rtl` a tier's first panel, or first
  column, is at its right; each frame is the one the tier reversed would have, so every panel
  keeps its size and its art, an inset keeps its corner and a slant leans as written. The pages of
  a document side by side (`render_pages`, the playground) and a strip start at the right, and every
  one is still written in reading order. A strip or a row of pages read two ways is refused.
- **Two gallery pages**, the same manga page read right to left and left to right.
- **`setting: {image: ..., fit: cover | contain}`**: a picture drawn elsewhere, behind the
  cast (#70). It is a backdrop of its own, so it is written instead of a `place` or
  `masses`, never beside them or beside a `horizon` (`conflicting-setting`); a `fit` with
  no image is `invalid-field`. A panel that inherits a place writes `place: null` beside
  its image, and the editor's schema now accepts that `null`.
- **The picture is read from its PNG or JPEG header**, beside the document as a font is, and
  only its size is taken. `scenet check` reports a picture that is absolute, missing, not a PNG
  or JPEG, or turned by its EXIF orientation as the new rule `image-file`, without the solver.
  Text compiled with no folder may be handed the files it names instead: `base` takes a
  mapping from the path the document writes to the file's bytes, for fonts as for pictures.
- **The picture is placed, and Panel Core records it.** Centred, filling the panel (`cover`)
  or shown whole inside it (`contain`), never stretched. `backdrop.image` holds the path as
  written, the media type, a digest of the bytes, the pixel size, the fit in SVG's words and
  the rectangle it is drawn in; over a picture `backdrop.horizon` is left out. A Core of masses
  is byte-identical, and `format_version` stays 1. The picture costs a balloon nothing and does
  not move the camera, and a generated description names no place and no hour over it — only
  the weather drawn on top.
- **The picture is drawn**, as an `<image>` on the paper, under every figure and the weather,
  in the rectangle Panel Core placed it in. It is linked by `xlink:href` — Inkscape does not
  load plain `href` — to the path exactly as written, which resolves when the SVG is beside
  the document; `scenet build --embed-images` (`embed=` on every renderer) writes its bytes in
  as a `data:` URI instead, and `build` says so in a note when a link will not resolve. The
  debug overlay shows where it was placed. A new how-to, *Letter over your own art*, and a
  gallery example drawn over a picture the repository paints itself, under its own licence.
- **The MCP server's `validate`, `compile` and `render` take `files`**: the files a document
  names, by the path it writes, as base64. They stand in for the document's folder, read in
  memory, so a model can letter over a picture — or in a font — it sends; `render` embeds
  the picture. Still five tools.
- **The playground's Image… button** adds a `.png` or `.jpg` to the document's `art/` folder,
  for as long as the tab is open, and the preview and every download embed it. The VS Code
  preview embeds pictures too, since it is not drawn beside the document.
- **An artwork contract** declares the figures a supplied picture draws (#71): beside
  `art/p01.png`, `art/p01.art.yaml` gives each figure's `face` (a disc lettering may not
  cover), `mouth` (where a tail ends) and `body`, and `keep_out` regions lettering should stay
  off, all in the picture's own pixels, with the `size` they were measured on.
  `scenet schema --artwork` emits its JSON Schema, which the VS Code extension associates with
  `*.art.yaml` and the documentation site publishes beside the others. Panel Core records what a
  contract declares, mapped into the panel through the picture's fit: `figures`, beside
  `actors`, and the picture's `keep_out`. Both are left out when empty, so every Core reads and
  writes as before and `format_version` stays 1; the debug overlay draws each figure's face,
  mouth and body, and each keep-out.
- **Figures a picture draws, in the cast** (#71): `cast: {ana: {figure: ana}}` in place of
  `reference:`. The panel's picture's artwork contract says where each face, mouth and body is,
  and lettering is placed by the same rules as around a puppet: never over a declared face —
  anybody's in the picture, cast or not — tails aimed at the mouth, bodies and keep-out regions a
  cost. The camera and staging do not run. A cast figure a panel's picture does not draw is not in
  that panel. Four new rules, each from the cheap pass: `unknown-figure`, `artwork-contract`
  (reported in the contract when the document is checked as a file), `conflicting-cast` (a puppet
  and a figure at once, a puppet's key on a figure, a mixed cast, one figure played twice) and
  `figure-staging` (staging naming a figure, a camera over figures). A `cover` crop that cuts a
  speaking figure's mouth out of the panel ends its tail on the frame, with a note. `scenet check`
  and `build` refuse a `*.art.yaml` given as a document. The panel and scene schemas accept
  `figure`.
- **A gallery example of figures a picture draws**, `35-figures.scene.yaml`: a station
  platform painted by `scripts/make_gallery_figures.py`, with its artwork contract written from
  the same constants, lettered under `cover` and `contain`. Two of its three people are cast,
  the third is kept clear of all the same, and its timetable board is a keep-out.
- **Contracts travel with their picture.** The playground's Image… button adds a picture's
  `.art.yaml` beside it, cleaned to the same name so the two pair; the MCP server takes it in
  `files`, its instructions and `get_spec`'s characters part say so, and the spec pack prints
  the gallery's contract. Still five tools. A how-to, *Letter the people in your own art*.
- **A panel's `description`**: what it shows, in words, for a reader who cannot see it.
  Written as `description:` in YAML; in a comic script, the panel's prose is it — its lines
  one paragraph, Markdown's markers taken off — unless an `@description:` directive, kept
  exactly as written, says something else. It is carried and never interpreted, for
  accessible output to read (#76). It describes one panel, so it is never inherited: beside
  `panels:` or in a script's front matter it is refused as `unknown-key`, and a panel drawn
  `over:` another does not take its parent's.
- **Panel Core carries the words a panel is read in**, built in the pipeline so the emitter
  copies them. `description` is the panel's own, or generated from what it holds — `Medium
  shot. A street at night, in the rain. Alice, left, pointing, angry, looking at Bob; Bob,
  right, arms crossed, sweating.` — and every balloon, caption and sound effect has a
  `label`: who says it, how, and the words, `Bob, whispering: I know.` Read in `order`, they
  are the panel's text as its reader takes it. Generated text is templated English.
- **A screen reader can read the panel** (#76). Each panel is one image, `role="img"`, named
  by one `<title>`: the description, then every balloon, caption and sound effect in reading
  order — in the name, since a description alone is often not spoken, and nowhere else, since
  NVDA read a `<desc>` a second time. It needs no id, so panels inlined together in one page
  cannot name each other. A strip or a page is a named `role="group"` of its panels, in reading order.
  `scenet build --no-aria`, `aria=False` on every renderer and `aria: false` on the MCP server's
  `render` leave it all out. Checked with NVDA 2026.2 and Edge 155, and against Edge's UI Automation
  tree; results, and how to check with VoiceOver, are in the new how-to, *Make a panel a
  screen reader can read*.

### Changed

- **A page's SVG writes its panels in reading order**, insets included, since document order is
  what a screen reader follows. An inset used to be painted after every other panel to stay on
  top; now its parent is cut around the inset's ring instead, so an inset `read: before` its
  parent comes first and is still on top. The page looks the same, to within anti-aliasing along
  the rings; only a page with insets changes, and only its bytes.
- **The strip and the page place a panel's body**, built for them, instead of cutting it out of
  the panel's serialised SVG, which made the panel's first two lines something they silently
  depended on. Byte for byte the same.

### Fixed

- **A backdrop of more than ten masses is drawn back to front.** Mass ids are numbered back
  to front, and the painter's sort compared them as text, so `m10` was drawn before `m2`: ten
  walls and a window in one plane painted the window, one rung paler, out under the walls. Masses
  in one plane are now drawn in the order Panel Core lists them. No gallery panel has more than
  ten, and none changes.
- **A speaker is forgiven a balloon over their own body whatever the actor is called.** The
  placer half-weights the speaker's silhouette, and looked the speaker up by the puppet's name
  while the silhouettes are keyed by actor id. An actor called anything but its puppet, which
  every comic script's capitals are, was charged as a bystander: in the gallery's comic script
  a line moved to the far corner of the panel behind a tail bent outside it.
- **A font path with a backslash is refused on every system**, as `font-file`. Windows read
  `fonts\Comic.ttf` as a folder and a file, and every other system as one file name, so the same
  document lettered in its font on one machine and was refused on the next. Write `/` between
  folders.
- **A control character in a font path is a finding, not a crash.** `lettering: {font:
  "fonts/a\0.ttf"}` reached the file system, whose `ValueError` was not one the compiler
  reports, so `scenet build` and `scenet check` both ended in a traceback. Any control
  character in a declared path is now `font-file`, naming the character.
- **Mutation testing runs again.** `mutation.yml` installed only the `mutation` group, and the
  documentation site's tests need `docs`, so mutmut's clean run failed and no mutant was tried.
  It now installs every group, as CI's test jobs do.
- **The VS Code preview draws each figure with its own clip.** It inlines every SVG a build
  wrote into one page, and a page has one set of ids, so a second panel in a slanted tier was
  clipped by the first one's outline, and page 2's panels by page 1's frames. Each figure's
  ids, and every reference to one, now carry a prefix of their own.

## [0.11.1] - 2026-10-18

**The documentation site documents the release you install, and shows off its playground;
and two comic-script fixes.** The site's root now serves the latest release, `main` moves under
`/dev/`, and each minor version keeps its own path; the playground says which version it runs,
and the home page shows its example compiled, with a button to open it there. A full stop
now ends a PAGE heading, and no line of a comic script can stall the compiler.

**Upgrading from 0.11.0.** The language, the command line and the Python API are unchanged,
and so is every YAML document's output. A comic script changes only where a PAGE heading
ends in a full stop, as in `PAGE 7.` or `PAGE TWENTY ONE.`: see Fixed.

### Added

- **The documentation site documents what you install.** Its root, and every address
  already in use there — the documentation, the playground, `schemas/panel.schema.json`,
  `scenet-spec.md`, `llms.txt` — now serves the latest release, not unreleased `main`.
  `main` moves to [`/dev/`](https://creatoan.github.io/scenet/dev/), and each minor version
  from 0.8 stays online under its own path, such as
  [`/v0.10/`](https://creatoan.github.io/scenet/v0.10/), its playground running that
  release's compiler. A version switcher in the navbar keeps the page you are on. `/dev/` and
  older versions carry a banner linking to the same page in the latest. Pin a schema or the
  spec pack to a release by putting its version in the path:
  `…/scenet/v0.11/schemas/panel.schema.json` (#171).
- **Each release attaches its built site** as `scenet-X.Y.Z-site.zip`, built from the wheel
  it publishes, before PyPI. The site serves every version from these, unchanged. Releases
  0.8.0 to 0.11.0 have theirs backfilled.
- **The playground says which version it runs**, with the same version switcher as the
  documentation, keeping a shared document across the switch. On `main`'s and on an old
  release's it says so, with a link to the latest. Playgrounds built before this change,
  those of 0.11.0 and earlier, carry no switcher.
- **The documentation's home page shows its example compiled** — the file `scenet build`
  writes for it, kept current with the golden files — and a button opens that example in the
  playground. The navbar names the playground beside the sections, and every link to it
  opens the playground of the version being read.
- **Dependencies and code are watched by GitHub's own security tooling.** Dependabot alerts
  and security updates cover the dependency graph, which GitHub builds from `uv.lock` and both
  `package-lock.json` files, transitive dependencies included. A pull request adding a
  dependency with a high or critical vulnerability fails dependency review. CodeQL analyses
  the Python, the TypeScript and the workflows on every pull request, on `main` and weekly.
  Secret scanning rejects a push that contains a credential. See `SECURITY.md`.

### Changed

- **Every pull request checks the package as a release would.** CI's new Package job builds
  the sdist and the wheel, runs `twine check --strict` on them, smoke-tests the wheel from an
  empty directory, and builds the wheel again from the sdist alone, comparing the two. The
  smoke test is now one script, `scripts/smoke_wheel.py`, that the release runs too.
  Nothing is published: TestPyPI stays a manual rehearsal.

### Fixed

- **A full stop ends a PAGE heading, as it ends a PANEL one.** `Page 4B.` named its page
  `4B.` and `PAGE 7.` a page called `7.`; `PAGE TWENTY ONE.` and `PLANCHE 3.` were not
  read as headings at all, since `ONE.` and `3.` are not numbers, so their panels ran on
  into the page before. They are pages `4B`, `7`, `21` and `3` now. A full stop inside a
  label, as in `PAGE 3.5`, stays.

### Security

- **A comic script cannot stall the compiler with one crafted line.** The PAGE heading
  pattern backtracked exponentially on a line like `PAGE !-!-!-…(`: fifty characters took
  seconds, and each two more took four times as long. Found by CodeQL, which led to the
  rest: the PAGE, SFX, caption and cue-with-its-line patterns each let two parts take the
  same run of space, so a long gap was quadratic or cubic -- a caption line of sixty
  thousand tabs took twenty seconds, an SFX line with a note three minutes. Every line
  is now read in time linear in its length, so `scenet build`, `scenet check` (which the
  editor runs on open and save), the MCP server and the playground cannot be hung by a
  script. The patterns read every script as before, with one exception at the edge: in
  `PAGE A - .` the full stop now ends the heading, as it already did in `PAGE A .`,
  rather than ending the label.
- **The playground's DOMPurify is 3.4.17**, past two advisories affecting versions up to
  3.4.15 (GHSA-6688-9rhm-gjv2, GHSA-p98j-92pf-mc4p). It reaches the playground through
  monaco-editor, which pins an older version, so the override that lifts it is raised by
  hand: Dependabot's security update cannot do it.

## [0.11.0] - 2026-10-17

**Lettering, sound effects, and comic scripts as publishers write them.** A stressed word is
lettered in bold italic, every pair is kerned, the type size can be set, and an author can
letter in their own face. Sound effects are lettered into the picture in a display face. A comic
script may be written as Dark Horse publishes its format, or in French, with captions that carry
speech, voices from off panel, small type, and its PAGE headings laid out as pages; `scenet
check` gains notes, the first of them a publisher's word limits.

**Upgrading from 0.10.**

- **Every example's lettering shifts slightly.** Kerning makes most balloons and captions up to
  about 1.5% narrower, and where two positions had scored nearly equal a balloon may sit
  somewhere else. Golden files of your own will need regenerating once.
- **A few comic-script lines mean something new**, each listed under Changed: prose before the
  first heading is a title page, `PANEL ONE` is panel `1`, `Panel 1. A description.` is a
  heading, an all-caps `NAME: text` with NAME in the cast is dialogue, a bare `CAPTION` starts a
  caption, and `CAP`, `CAPTION` and `SFX` are reserved.
- **A comic script with PAGE headings now writes its pages**, and the panels on them are
  compiled at the size of their frames and lettered at the page's one size, so they look
  different; the front matter's `panel: {size}` now sizes only panels on no page.
- **`scenet check` can print notes** -- `file:line:column: note: rule: message` -- and exits 0
  when there are only notes. The MCP server's findings gain `level`, and `validate` calls a
  document with only notes valid.

### Added

- **`scenet check` reports notes as well as errors.** A note is a house limit rather than a
  contradiction: the document still builds, so a note never fails the check. The first is
  Dark Horse's word limit, `word-limit`: a balloon or caption over about 25 words, or a
  panel over about 50, in YAML and in comic scripts alike. Words are counted as lettered,
  so `--` and emphasis underscores add none, and sound effects are not counted.
  - In text, a note reads `file:line:column: note: rule: message`; an error's line is
    unchanged.
  - In SARIF, the level comes from the rule, in `defaultConfiguration` and in each result,
    so VS Code and the playground show a note as information.
  - `check` exits 1 only on an error, and prints `ok` for a document with only notes.
  - The MCP server's findings gain `level`, and `validate` calls a document valid when
    none is an error. (Part of #75)
- **Comic scripts in Dark Horse's published layout compile.** `PAGE ONE (five panels)` is a
  page heading whose count is checked against the panels under it, as the new
  `panel-count` note. `Panel 1. Alice and Bob on a corner.` is a panel heading with its
  description on the same line, and `Panel One` is panel `1`. A title page — the writer's
  name and address — may come before the first heading. Markdown's `## PANEL 2`,
  `**PANEL 2**` and horizontal rules are read as the headings and blank lines they mark.
  A cue with nothing said under it, and a name in capitals with a line under it on the
  title page, are `looks-like-dialogue` notes. `scenet build` prints these notes, and
  `Book.notes` carries them. (Part of #75)
- **Comic scripts read Dark Horse's lettering labels.** `CAP:` and `CAPTION` take their
  text from the line or the lines under them; Dark Horse's `CAP/ALICE` is a spoken
  caption by Alice, with the writer's quotation marks taken off so they are not doubled;
  `ALICE (V.O.)` is a voice over, lettered as a spoken caption. `ALICE: Hello.` is
  dialogue when Alice is in the panel's cast, and a `looks-like-dialogue` note otherwise.
  `(burst)` is a shout, several parentheticals are read together, and Blambot's numbered
  items, `1. ALICE:`, are read with their number set aside. (Part of #75)
- **`@over:` in comic scripts** writes a panel as a change to another, with the merge
  rules `over:` has in YAML: the panel inherits the other's directives, never its
  dialogue. `@over: 1` names panel 1 on the same page first, then the panel named `1`. A
  missing panel, a cycle or a panel over itself is one `composition` finding at the
  `@over:` line. (Part of #75)
- **Off-panel speech.** `say: {by: caller, text: "Open up!", off_panel: left}` is spoken by
  somebody nobody draws: the balloon's tail ends on the frame, on that side, or on the
  slanted outline of a slanted panel. `off_panel: true` lets the compiler take the nearer of
  left and right. The speaker is not in the cast, and one who is drawn cannot speak from off
  panel: the new error `off-panel-speaker`. Panel Core balloons gain `off_panel`, the side,
  written only when set, so no existing Core changes. (Part of #75)
- **`ALICE (OP)` in a comic script is off-panel speech**, as are `(OFF)`, `(O.S.)` and
  `(O.C.)`. Alice is left out of that panel's cast and of the staging that names her, each
  relation with a `dropped-relation` note, and her tail ends on the frame on the side she
  was written to stand, unless the cue names one, `(OP, right)`. A cue for somebody never
  cast, `PHONE (OP)`, works too. (Part of #75)
- **Small lettering.** `say: {..., size: small}` letters a line at three quarters of the
  dialogue size, in a balloon padded as the normal size would be: muttered, as Blambot
  describes it. A comic script's `(small)` and `(weak)` give it. (Part of #75)
- **French comic scripts.** `PLANCHE 1 (six cases)`, `CASE 2` and `VIGNETTE 2` are headings;
  `RÉCITATIF`, `CARTOUCHE` and `NARRATIF` are captions; `ONOMATOPÉE` is a sound effect;
  `LÉA : « Bonjour. »` is a cue and its line, with a no-break space before the colon. `(pensée)`
  is a thought, `(off)` and `(hors champ)` off-panel speech. `@shot:` and `@angle:` take the
  *échelle des plans* — `gros plan` is `big_close_up`, `plan rapproché épaule` is `close_up` —
  and *plongée*, *contre-plongée*. Both highlighters follow, and the gallery gains
  `33-planche.script`. (Part of #75)
- **A figure may look at somebody heard from off panel**: `bob looking_at carol`, where Carol
  speaks `off_panel: left`, turns Bob toward the left of the frame and aims his eyes out of it.
  With no side named, Carol is heard from the side Bob faces. In a comic script,
  `BOB looking_at ALICE` now survives `ALICE (OP)` instead of being dropped with a note.
  (Part of #75)
- **`null` leaves an inherited cast member out of a panel**: `cast: {bob: null}` in a scene's
  panel, under `over:` or over the scene's defaults, or `@cast: {BOB: null}` in a script. It
  follows JSON Merge Patch (RFC 7386), "If the value is null, remove". The staging relations
  that name him go too, each a `dropped-relation` note, and the JSON Schema accepts the `null`.
  (Part of #75)
- **French delivery words**, from the BnF's sheet on balloons: `(murmure)` and `(chuchoté)` are
  a whisper, `(cri)` and `(crié)` a shout, `(à voix basse)` small type. (Part of #75)
- **`compile_script`** compiles a comic script handed over as text, exactly as `scenet
  build` compiles a `.script` file. `scenet check --deep`, the MCP server and the
  playground now all go through it, rather than assembling a script each their own way.
  (Part of #75)

- **A stressed word is lettered in bold italic.** Write it between underscores, the way a
  script underlines it: `I _told_ you`. It works in dialogue and captions, in YAML and in
  comic scripts, and the word is measured in bold italic as well as drawn in it, so it
  widens its balloon by exactly as much as it is drawn wider. An underscore inside a word
  stays an underscore, and `\_` writes one anywhere. Emphasis that is opened and never
  closed is reported as `unbalanced-emphasis`, and a value starting with `*`, which YAML
  reads as an alias, now says to quote it. Panel Core gains `runs` beside `lines`, written
  only for a line with emphasis, so every existing panel compiles byte for byte as before.
  (Part of #74)

- The editor guide shows how to see `scenet check` findings in VS Code today: write them
  as SARIF and open the file with Microsoft's SARIF Viewer. (Part of #77)
- **The VS Code extension shows what `scenet check` finds**, as you open and save a panel,
  scene or comic script: an actor not in the cast, an ordering cycle, a pose the puppet
  lacks, which the schema cannot see. Each finding is underlined where it is and listed
  under Problems with its rule, linked to its explanation, and goes away when it is fixed.
  `scenet.checkDeep` adds `--deep`; `scenet.checkOnSave` turns it off. If `scenet` cannot
  be run, or crashes, a notification says so once rather than leaving the list empty.
  (Part of #77)
- The extension is now versioned with the compiler, starting at 0.10.0, so the `.vsix` on
  a release says which release it belongs to.
- **The VS Code extension highlights comic scripts**, as the playground does: headings,
  directives, captions, cues and their parentheticals, dialogue set apart from prose, and
  the front matter as YAML. Both highlighters are tested against one set of fixture
  scripts, which are themselves checked against the compiler's reading, so neither can
  drift from the other or from the format. (Closes #77)

- **Type size can be set**: `lettering: {size: N}` is the dialogue size in panel units,
  and captions keep their proportion to it. Set beside `panels:` it applies to every
  panel, so a whole page letters at one size you chose; on one panel, to that panel
  alone; in a comic script, in the front matter or an `@lettering:` directive. Left out,
  nothing changes. (Part of #74)
- **Letter in your own face.** `lettering: {font: fonts/Comic.ttf}`, or a file per face
  under `regular`, `italic` and `bold_italic`, sets the lettering in fonts the document
  names, read relative to the folder it is in -- never a system font, and never an
  absolute path. A face left out stands in from one given, and the compiler says so when
  that matters. Panel Core records each face by family, style and a digest of its bytes,
  never a path; the renderer is handed the fonts and refuses a panel whose fonts it was not
  given; `--live-text` names the family measured. A font that is missing, absolute or not
  a font is the new rule `font-file`, located at the face. The playground gains **Font…**
  to add a file for the session. Capitals stay as you type them, and Source Sans Pro stays
  the default; both are recorded. (Part of #74)
- **Scenet ships a display face for sound effects**: Bangers, by Vernon Adams, under the
  SIL Open Font License 1.1. No package carries it, so it is vendored inside the wheel with
  its licence beside it, recorded in `THIRD_PARTY_NOTICES.md`, and pinned by a test to the
  file in google/fonts. Nothing letters in it yet; sound effects will. (Part of #73)
- **Sound effects.** `- sfx: {text: BLAM, from: bob}` letters a sound into the picture in
  the display face, with no balloon: `small`, `medium` or `large`, turned by `rotate`, bent
  along an `arc`, and `hollow` for an open effect the art shows through. It is placed by
  candidates and cost near its source or in its `prefer:` zone, never covers a face, and
  is never given a coordinate. Balloons pay to cover it, as they pay for emanata, and no
  figure moves for it. It takes its number in the script's reading order without the
  geometric rule. Panel Core gains `sfx`, every letter already turned and placed; the
  debug overlay shows each one's footprint; `scenet check --deep` reports one with
  nowhere to go as `sfx-placement`; `lettering.font` can name a `display` face. Panels
  without one compile exactly as before. (Part of #73)
- **Sound effects in comic scripts**: `SFX: BLAM`, `SFX (BOB, large): KRAK` for its source
  and size, and Dark Horse's bare `SFX:` cue with the sound on the next line -- which used
  to be dropped as prose, or read as a character called SFX. An `SFX:` cue with nothing
  under it is reported rather than lost. The playground and the VS Code extension
  highlight them, and the playground colours an effect's `from:` as an actor. Sound
  effects are recorded in `docs/explanation/design_decisions.md` and `prior_art.md`.
  (Closes #73)
- **A comic script's PAGE headings lay its panels out on pages**, as a scene's `pages:`
  does. A page's panels go into tiers by a fixed rule — at most three tiers up to nine
  panels, an odd one alone in the middle tier — or by `@tiers: 2 1 2` written right after
  the heading. The front matter's `page:` sets the format; `pages:` there is an error, as
  is a `@tiers:` that does not add up or is written elsewhere, under `page-layout`.
  `scenet build` writes each page, with its Page Core and overlay. With it, every row of
  #75 is done: the spec pack, the Agent Skill and *Drive Scenet from a model* now say that
  Dark Horse's format and French scripts are read as written. (Closes #75)

### Changed

- **Comic scripts: what a few lines mean has changed** (Part of #75):
  - Prose before the first PANEL heading is a title page, not an error. A directive, a
    caption, a sound effect or a cast member's cue there is still one.
  - A panel numbered in words is named by its number: `PANEL ONE` is panel `1`, and
    `scenet build` writes `name.1.svg` for it rather than `name.ONE.svg`.
  - `Panel 1. A description.` is a heading; it was prose.
  - A line of three or more `-`, `*` or `_` ends a speech, as a blank line does; it was
    joined onto the speech.
  - An all-caps `NAME: text` with NAME in the cast is dialogue; it was prose. One in the
    middle of a speech starts a new balloon; it was joined onto the speech above.
  - A bare `CAPTION` line starts a caption whose text is under it; it was an error.
  - `CAP`, `CAPTION` and `SFX` are reserved, and cannot be a cast member's id.
  - A balloon's text in one pair of quotation marks is lettered without them.
  - A script with PAGE headings now writes its pages, `name.page-1.svg` and on, and the
    panels on them are compiled at the size of their frames and lettered at the page's
    one size, so they look different from before. The front matter's `panel: {size}`
    now sizes only panels that are on no page.
- **Lettering is kerned.** Pair adjustments are read from the font's GPOS `kern` feature,
  or a legacy `kern` table, and applied to measurement and to the glyph outlines alike, so
  what is measured is still exactly what is drawn. Every example's output changes once:
  most balloons and captions come out slightly narrower, by up to about 1.5% (a kern pair
  can loosen as well as tighten, so a few grow a little), and where two positions had
  scored nearly equal a balloon may sit somewhere else. `--live-text` relies on the
  renderer kerning as the compiler measured it, which browsers do by default. Checked pair
  by pair against HarfBuzz, which is a test dependency only. (Part of #74)
- The VS Code extension's comic-script grammar is generated from one definition of each
  kind of line, rather than hand-written with every heading spelled out in up to four
  places. Highlighting is unchanged. (Part of #75)

### Fixed

- **A `--` or `...` written apart from its word could be lettered alone on the last line**,
  or at the start of one: `the lamp is out --` broke before the dash. Blambot sets both with
  no space, so a dash or an ellipsis now stays with the word it is written against. The space
  is still lettered as written; no gallery example moves. (Part of #75)
- **A line between a PAGE heading and its first PANEL was filed into the panel before the
  page**: a speech there was spoken in the previous page's last panel. It now belongs to
  the page, and a speech there is an error, since it belongs to no panel. (Part of #75)
- **The playground took a YAML panel that opens with a `---` document marker for a comic
  script**, and a script written as Dark Horse asks, `Panel 1.`, for YAML. A script is now
  told by its fenced front matter or a panel heading in any of its forms. (Part of #75)
- **Spoken captions by two speakers were quoted as one run.** Consecutive `spoken`
  captions open a quote each and close only the last, but the run did not end when the
  speaker changed, so the first speaker's words were never closed. A change of `by` now
  ends the run. No shipped example moves. (Part of #75)
- **A comic-script directive written twice in one panel silently kept the second.**
  `@setting: {weather: rain}` and then `@setting: {place: docks}` lost the rain. The second
  is now `duplicate-key`, at its line, naming the first. An `@script:` directive, which the
  panel's cues used to overwrite without a word, is `duplicate-key` too. (Part of #75)
- **A fault in a comic-script panel kept neither its rule nor its line.** Everything
  validation found was reported as `invalid-field` at the PANEL heading: a speaker not in
  the cast, an unknown place, a bad `@shot:`. It now keeps its own rule (`unknown-actor`,
  `unknown-place`, ...) and points at the cue or directive that holds it. When a panel
  has several, the first in reading order is reported. (Part of #75)
- **A cue with an accented name lost its dialogue.** `HÉLÈNE` or `ZOË (whisper)` failed the
  cue pattern's A-to-Z capitals, so the cue and the line under it were filed as prose
  without a word. Any capital letter now starts a cue, in the compiler and in both
  highlighters. A script is also read composed (Unicode NFC), so a name a macOS editor
  stored as `E` and a separate accent matches the front matter's `É`. (Part of #75)
- **A comic script saved with a byte-order mark** was rejected for having content before
  the first PANEL heading: the mark hid the front matter. It is now ignored. (Part of #75)
- **Line numbers in a comic script's findings could be wrong** after a line holding a
  line separator, form feed or similar character, which Python splits a line at and an
  editor does not. Lines are now split at line feeds alone. (Part of #75)
- **The VS Code preview could not run `uv run scenet`**, the setting its README suggests:
  it ran the compiler from wherever VS Code runs extensions, its own install directory,
  where `uv` finds no project. It now runs from the document's workspace folder.
- **The VS Code extension could not run `scenet` from a path with a space in it**, such as
  one under `C:\Program Files`, though `scenet.executable` asks for an absolute path: the
  setting was split on every space. A part in double quotes now keeps its spaces.
- **A comic-script finding repeated its file in the message**, spelled as it was typed. Given
  an absolute path, `scenet check` wrote that path into its SARIF output, and the finding's
  fingerprint changed with the spelling. The location still names the file.
- **A SARIF fingerprint depended on how the file was named on the command line**, for every
  kind of document: `a.panel.yaml` and its absolute path gave two fingerprints for one
  result, so an editor and CI would have raised two alerts for one fault. It now uses the
  `uri` the result reports. A path given relative to the working directory, as CI gives
  it, keeps the fingerprint it had.
- **SARIF output did not say what a column counts.** SARIF 2.1.0 requires `columnKind` on a
  run with results, and without it an editor counting UTF-16 code units, as VS Code does,
  points one column further off past each emoji. It is now `unicodeCodePoints`.
- **A comic-script finding pointed at the first character of its line** in SARIF, which
  claimed a precision the parser does not have. Its region is now the whole line, so an
  editor or code scanning underlines the line.
- **The playground never coloured a comic script's `PAGE` and `PANEL` headings**, and the
  line after a cue with a parenthetical, such as `BOB (whisper)`, was not shown as dialogue.
  Monaco refused those three highlighting rules and dropped the lines without a word. The
  rules are fixed, and a test now runs them through Monaco's own lexer, where a refused rule
  fails.
- **The playground coloured a comic script by older rules than the compiler reads it by.**
  `Panel 1.`, `ALICE:` and `CAPTION: Later.` were shown as prose; a cue did not end the
  speech before it; and a `---` scene divider opened front matter that never closed,
  colouring the rest of the script as YAML. It now follows the script frontend line for
  line, and shared fixtures, checked against the frontend, hold it there.
- **Toggle Line Comment in a VS Code comic script wrote `//` lines**, which the format does
  not have: the compiler kept them as prose, or read them as dialogue under a cue. The
  extension no longer declares a comment syntax for scripts, as the playground never did.
- **`scenet check --format sarif` crashed on a caption that named a speaker it cannot
  have**, such as `by:` on a `locale` caption. Its rule, `caption-speaker`, had never been
  added to the catalogue, so writing the finding as SARIF, or returning it from the MCP
  server's `validate` tool, ended in a `KeyError`. The rule is now catalogued and
  documented, the finding points at `by:` rather than the whole caption, and a test holds
  every rule the compiler raises to the catalogue.

## [0.10.0] - 2026-10-10

**Pages.** A scene can now be laid out on pages -- tiers of panels, columns beside them,
insets set into corners and gutters that lean -- and `scenet build` writes each page beside
its panels. This release also closes more than twenty ways a document could lose something,
point at the wrong line, or end in a traceback, and the test suite now holds the compiler to
its promises with generated documents, golden outputs on every platform and weekly mutation
testing.

**Upgrading from 0.9.**

- **Some documents that compiled now refuse**, each for a fault that was losing something
  without a word: a key written twice in YAML, a panel named with an unquoted number, `.inf`
  or `.nan` anywhere, a control character in a line or an actor id, an inset that does not
  fit its panel, and two outputs that would be the same file.
- **Every panel with lettering renders slightly differently.** Glyphs are now drawn at the
  size they were measured, which at some sizes is 14% smaller than before; a strip's ids are
  prefixed by each panel's position; and `--strip` no longer writes a strip of one panel.
- **Some findings moved**: an unknown speaker is at `script.N.say.by`, a block-style key at
  its own line, a broken `over:` at the `over:`. Code that matched on the old paths, the MCP
  server's `where` included, needs updating.
- **A comic script that numbers its panels per page** now names them by page and panel
  (`2-1`), where before the later page overwrote the earlier one.

### Added

- **Pages.** A scene can lay its panels out with `pages:`: each page a list of tiers, each
  tier a list of panels, and a weight for each tier's height and each panel's width, shared
  out of what `page:`'s margin and gutters leave, the way CSS Grid shares a row. A panel on a
  page is compiled at its frame's size and nothing else changes about it, except that every
  panel on a page letters at one type size. (#66)
  - `scenet build` writes each page as `stem.page-<n>.svg`, with its Page Core and overlay
    under `--core` and `--debug`, and refuses a panel whose file would be a page's.
  - A new tier, **Page Core**, records where every frame is and the type height the page
    shares. `compile_book` returns the panels and the pages; `render_page` and
    `render_pages` draw them.
  - `scenet check` reports `scenet/page-layout` for a placement naming no panel, a panel
    placed twice, or no room left by the margin and gutters.
  - The published schema, the VS Code extension and the playground understand pages; the
    playground shows a document's pages side by side, and its Panel Core view holds the
    Page Cores. MCP `compile` returns each Page Core and `render` one SVG per page.
  - A gallery example, a how-to (*Compose a page*), and a prior-art entry on where the rules
    come from: Cohn's reading-order experiments, Peeters, Groensteen, CSS Grid.
- **Columns on a page**: a tall panel beside a stack. A tier can hold `columns:` in place of
  `panels:`, each column a stack of panels shared out by `height`, and a column of one panel
  spans the whole tier. A tier of columns is read down each column before across, as readers
  read a stack blocked by a tall panel. Two stacks side by side block nothing, readers go
  across them, and `scenet check` refuses them as `page-layout`. (Part of #67)
- **Insets**: a small panel set into a corner of another, drawn over it inside a ring of white.
  `insets:` on any placed panel takes a corner, a `size` (a fraction of the parent, at most a
  half) and `read: before` or `after`. Readers split about evenly over an inset, so its place
  in the reading order is written, never guessed: after its parent by default. (Part of #67)
  - The parent's art does not move. Its lettering keeps clear of every inset, as firmly as of
    a face, and its Panel Core records what it kept clear of as `exclusions`. A note says when
    an inset covers a face.
  - Page Core frames gain `inset_of` and `clearance`, and the page paints every inset over its
    parent whatever its reading order. Neither new field is written where it is unused, so
    every existing Core is byte-identical.
  - `scenet check` reports two insets that overlap as `page-layout`, located at the second.
  - The debug overlay draws what an inset covers. A gallery example, and a section of the
    *Compose a page* how-to.
- **Slanted tiers**: `slant` on a tier of panels leans every gutter in it, up to 30 degrees
  either way, for a beat that should not sit square. Neighbours share one cut, a gutter stays a
  gutter wide across it, and the tier's outer edges stay upright, so every frame is a convex
  four-sided shape. (Closes #67)
  - A slanted panel is staged in its bounding box and cropped to its `outline`, which its Panel
    Core and its Page Core frame record; its lettering stays inside the outline, a margin in. A
    note says when the cut runs through a face.
  - A rectangle writes no `outline`, so every existing Core and page is byte-identical.
  - `scenet check` refuses, as `page-layout`, a slant on a tier of columns, on a tier of one
    panel or on panels with insets, and one too steep to leave every panel some width.
- `scenet/duplicate-panel`, the finding for two panels in a script that would still share a
  name: `PANEL 1` twice on one page, or twice with no PAGE heading between them. It points at
  the heading that repeats. (#63)
- `scenet/duplicate-key`, the finding for a key written twice in one YAML mapping. It points
  at the second and names the line of the first. (#83)

- **Golden outputs, checked on every platform.** The gallery is built through `scenet build`
  in every CI job, Windows included, and the bytes on disk must match committed goldens: every
  Panel and Page Core in full, and a digest of every SVG. Two processes with different hash
  seeds, and a relative path against an absolute one, must write the same bytes, and no output
  may hold the path it came from. `scripts/update_golden.py` regenerates them. (#94)
- **Weekly mutation testing of the solver and the emitters.** `.github/workflows/mutation.yml`
  runs [mutmut](https://github.com/boxed/mutmut) over `solve/` and `emit/` every Monday and
  on demand, and reports every small edit to the code that no test notices, with the score in
  the job summary. A second job runs the property tests with fresh random seeds and 300
  examples each. Neither runs on pull requests or blocks a merge. mutmut is in its own
  `mutation` dependency group, so a plain `uv sync` does not install it. (#95)
- **The command-line reference is a tested contract.** Each command's options, choices,
  defaults and exit statuses, the frontends, and every behavioural sentence in
  `docs/reference/cli.md` are checked against the code in both directions, so neither can
  drift alone. Every rule has a document in `tests/rule_corpus/` that must produce exactly
  one finding of it. And the `scenet` commands in the documentation's shell examples now run
  in the test suite, as its Python examples already did. (#93)
- **Property-based tests for pages, scripts and broken documents.** Generated books are
  held to the documented reading order, worked out from the pages as written, to frames that
  stay inside the margins and clear of each other, and to sound SVG with ids unique across
  pages. Generated comic scripts lose no panel and no line. And a valid document given any
  one mistake from a catalogue of twenty-odd must get exactly one finding from `scenet
  check`, under the right rule and on the right line; arbitrary input must never get a
  traceback. The eight bugs they found are fixed above. (#92)
- **Property-based tests.** The checks a compiled panel must pass, which ran on five
  hand-written panels, now also run on panels Hypothesis generates: lettering inside the
  margin, off every face and in reading order against every earlier box; an SVG that
  parses, whose ids resolve and whose glyphs are drawn at their measured size; compiles
  that are byte-identical; Panel Core that round-trips; and `scenet check --deep` agreeing
  with the compiler. The examples are fixed, so a failure replays on every machine.
  `docs/maintainer/testing.md` explains the profiles and how to add a generator. (#91)

### Fixed

- **The same panel could compile to different bytes.** kiwisolver, which places the cast,
  keys its internal maps by object address, so the same layout solved twice could come back
  a few ulps apart. A coordinate derived from it that sat on a rounding boundary then
  printed as `247.95` in one compile and `247.96` in the next, in the same process. Solved
  positions are now snapped to a millionth of a unit as they leave the solver, far above
  that noise and far below anything the output shows. One gallery golden moves by 0.01 as a
  result. Found by the weekly Hypothesis exploration. (#117)
- **One mistake in a puppet part was reported six times.** A part is a bone (`from`, `to`,
  `width`) or a blob (`at`, `radius`), and a bone with a bad `width` was also tried as a blob,
  so pydantic listed five more errors about a blob nobody wrote, under paths naming its
  classes. A part is now checked only as the kind its keys say it is, at `parts.N.bone` or
  `parts.N.blob`, and a part with the keys of both kinds or of neither is one error that
  says what a part must be. The same fix #98 made for script entries. (#92)
- **A font with no character map raised `KeyError: 'cmap'`** from inside fontTools when
  passed as `metrics=`, instead of the `ValueError` that `FontMetrics` documents for a font
  it cannot measure text against. Found while triaging mutation testing. (#95)
- **`scenet build` could silently overwrite one output with another.** Only a panel named
  like a page was refused. A panel named `strip` replaced the strip, `x.debug` replaced panel
  `x`'s overlay, and two names differing only in case wrote one file on Windows and macOS.
  Every output is now planned before anything is written, and two that would be the same
  file, compared ignoring case, are a usage error: exit 2, nothing written. (Refs #93)
- **A panel name holding `/` or `\` made `scenet build` end in a traceback.** It is now a
  usage error, exit 2, saying why the name cannot be part of a file name. (Refs #93)
- **`--strip` wrote a strip of one panel** for a scene with a single panel, although the
  reference says it is ignored for one; only a document whose panel was called `panel`
  skipped it. A strip now needs more than one panel. (Refs #93)
- **An unknown speaker was located one step short of its `by:`.** The finding's path was
  `script.0.by`, which the document does not have -- a line is written `- say: {by: ...}` --
  so a script in block style was pointed at `- say:` rather than the `by:` line. The path is
  now `script.0.say.by`, as every other fault in a script entry has been since the verb picks
  the event, and the finding lands on the unknown name itself. The MCP server's `where` field
  for it changes the same way. (Refs #92)
- **Some findings pointed at the wrong line, or at no line at all.** A syntax error at the
  very end of a file -- a bracket never closed -- was put on the line after the last one,
  which an editor or code scanning cannot show. And a key whose value is a block, such as
  `panel:` with its fields beneath it, was located at the block's first field: a panel whose
  margin left no room pointed at `size:`, and a cast member missing `reference` at whatever
  key it did have. The first now sits at the end of the last line, the second at its key.
  (Refs #92)
- **A broken `over:` was located at the whole `panels:` block.** `scenet check` pointed a
  missing parent, a cycle or an `over:` that is not a name at the first line of `panels:`,
  wherever the fault was. It now points at the `over:` to change, and a missing parent's
  message names the panel that refers to it. (Refs #92)
- **A misspelled required key was reported twice.** `referense: alice` came back as an
  unknown key and as a missing `reference`, both at one place, for one mistake. When an
  unknown key closely matches a required key missing from the same mapping, `scenet check`
  and `build` now report one `scenet/unknown-key` finding, ending "did you mean
  'reference'?". An unrelated unknown key beside a missing one is still two findings. (Refs #92)
- **A staging sentence relating an actor to itself was filed under the wrong rule.**
  `alice left_of alice` came back from `scenet check` as `scenet/invalid-field`, although
  `scenet/reflexive-relation` exists for exactly this; the frontend rewrote the error and lost
  the rule. It is now reported as `reflexive-relation`, and `build` keeps the rule and location
  of every fault the frontend finds itself -- an unknown place too -- as `check` does. (Refs #92)
- **An inset could be drawn outside the panel it is set into.** An inset sits a gutter in
  from its corner, so in a panel narrower or shorter than that it landed over the next panel
  or the page margin, and `scenet check` said nothing. An inset that does not fit is now
  refused as `scenet/page-layout`, at the inset, saying what to change. (Refs #92)
- **A document nested a few hundred levels deep ended in a traceback.** PyYAML reads a
  document recursively, and Python's recursion limit is not a YAML error, so `scenet check`,
  `check --deep`, `build` and a comic script's front matter all ended in `RecursionError`.
  It is now reported as invalid YAML: "the document is nested too deeply to read". (Refs #92)
- **A control character in a panel wrote an SVG no XML parser accepts.** A `\x07` in a line
  of dialogue broke `--live-text` output, and one in an actor id broke the default output too,
  through its `id` attribute. XML cannot hold these characters even escaped, so a line, a
  caption or an actor id holding one is now refused as `scenet/invalid-field`, naming the
  character. Tab, line feed and carriage return are still accepted. (Refs #91)
- **A panel named with a number beside one named with a word crashed** `scenet check` and
  `scenet build` with a `TypeError` traceback. YAML reads an unquoted `1:` as a number and
  `null:` as nothing, and the names could not be sorted together. A panel's name is text, as
  a cast member's id already was, so each one that is not is now reported as
  `scenet/invalid-field` at the name, with the quoted spelling to use instead. (#92)
- **Lettering was drawn larger than it was measured.** Each glyph's scale, the font size over
  the font's units per em, was written to two decimal places like a coordinate. At size 35
  that is 0.035, written as 0.04, so every letter was drawn 14% larger than the width the
  balloon was sized for and its neighbours were spaced for. The scale is now written to six
  places, and a test holds every drawn glyph to its measured size. (#91)
- **An infinite or undefined number ended the interpreter.** `.inf` and `.nan` are valid YAML
  floats, and one in a panel's or a page's size, margin, height or width passed `scenet check`
  and then reached the solver, where kiwisolver stopped the process outright: no traceback,
  no message, no output. Every number a document, a puppet or a Panel Core holds must now be
  finite, and one that is not is reported as `scenet/invalid-field` at its key. (#91)
- **One mistake in a script entry was reported up to four times** by `scenet check`. A
  caption with `kind: narration` also came back as every reason it was not a `say`, all at
  the same place. The entry's verb now picks the event it is checked against, so the one
  real fault is reported, at the field it is in (`script.0.caption.kind`). A face mark in a
  hand-edited Panel Core is picked by its `mark` the same way. Entries built in Python
  without a verb are still accepted, and the published schema is unchanged.
- **`-o` naming a directory crashed** `scenet build`, `check` and `schema` with a traceback;
  `scenet build x.panel.yaml -o .` was enough. `build` now writes into a directory under the
  default name, as `cp` does. A directory is one that exists, or a path ending in `/`. `check`
  and `schema` write one file of their own, so they refuse a directory with a usage error.
- **`scenet check -o FILE` ignored `-o` in text format.** The findings went to the terminal
  and no file was written, although the reference said it wrote the report to the file. It
  now does, as it already did for SARIF. The file is empty when every document is valid.
- A mistake inside one tier of `pages:` was reported twice by `scenet check`. The second
  report said the list of tiers was empty, which it was not: pydantic also calls a tuple too
  short when one of its items fails. That echo is now dropped wherever pydantic's errors
  become findings.
- **Output was not byte-identical across platforms.** On Windows, every SVG, Core, overlay,
  strip and page that `scenet build` wrote had CRLF line endings, as did reports and schemas
  written with `-o` and `scenet schema` redirected from stdout. The same build on Linux
  wrote LF. Everything is now written as UTF-8 with LF everywhere. A SARIF report printed to
  a Windows console no longer fails on a character outside its code page. CI now runs the
  test suite on Windows as well, where a test checks the written bytes.
- **A comic script could lose panels and dialogue without saying so.** Three cases, none of
  which raised anything. (#63)
  - **Panel numbers that start again on each page** overwrote each other, so
    `PAGE ONE / PANEL 1 / PANEL 2 / PAGE TWO / PANEL 1` compiled two panels. Publishers' script
    formats number panels per page, so this is the common case. When numbers repeat, every
    panel is now named by its page too: `PANEL 1` under `PAGE TWO` is `2-1`, written to
    `name.2-1.svg`. Spelled-out pages are named by their number. A script that numbers
    straight through keeps its names.
  - **Dialogue wrapped onto a second line** lost that line. A speech now runs to the next blank
    line, joined with spaces. Prose written directly under dialogue with no blank line between
    them now joins the speech; a line that looks like a cue still starts a new one.
  - **`PANEL 1:`** named the panel `1:`, and `scenet build` wrote `name.1:.svg`, which Windows
    cannot hold. `PANEL 1:` and `PANEL 1.` both name panel `1` now.
- **`--strip` let figures spill out of their panels, and repeated every id.** A shot crops
  the body at the frame, and a panel on its own hides the rest behind its `viewBox`; in a
  strip nothing clipped, so bodies drew into the gutter. Each panel is now clipped to its
  frame, overlay included, so a panel looks the same in a strip as alone. And every id is
  unique: each panel's ids, and the references to them, are prefixed by its position (`p1-`,
  `p2-`), never by its name, which could not be kept safe inside `url(#...)`. The strip's
  output changes; a single panel's is byte-identical. `render` and `render_debug` take an
  `id_prefix` for this, empty by default. (#64)
- **Reference documents disagreed with the code in eight places**, now each true again and the
  first three held there by a test. (#65)
  - `shot_types.md`, the normative one, said `angle` moved the eye-line. It has always
    scaled headroom (×0.5, ×1.0, ×1.6), as the code, the IR and gallery 03 say.
  - The puppet example in `asset_contract.md` used fields the contract never had, so a
    puppet written from it would not load. It is now a complete puppet that does.
  - The rule table in `cli.md` lacked `unknown-place` and `conflicting-setting`.
  - The constraint table in `language.md` had panel bounds as required and ordering as
    strong; it is the other way round, on purpose.
  - `BalloonKind` said speech and whisper balloons were ellipses and thought balloons
    clouds; they are rounded rectangles and an ellipse.
  - The editor guide claimed highlighting for `.script` files, which the extension does
    not have (#77). The comic-script guide said rain was not a construct (it has been since
    0.6.0), and the status page still listed tinted captions as planned and pages as
    untracked.
- **A key written twice in YAML lost the first without a word.** PyYAML keeps the last of
  two equal keys, so `cast: {alice: …, alice: …}` compiled one character and `scenet check`
  called it `ok`; the same went for panels, settings and a puppet's poses. Every YAML Scenet
  reads (panels, scenes, a script's front matter and `@` directives, puppet files) now
  refuses a repeated key, as the YAML specification says it should. A merge key's override
  is still allowed. Documents that compiled with a silently dropped key now fail; that is
  the fix. A puppet file that is not valid YAML is now an `AssetError` naming the file,
  rather than PyYAML's bare error. (#83)

## [0.9.0] - 2026-10-03

A release for maintainers: Scenet can now be listed in the MCP registry from a workflow. The
language, the compiler and the `scenet mcp` server are unchanged from 0.8.0.

### Added

- **A workflow lists releases in the MCP registry.** `mcp-publisher login github` cannot publish
  under an organisation namespace, because the registry's GitHub App is not installed on the
  organisation and `io.github.creatoan/*` answers 403 whatever the role. The new
  `.github/workflows/registry.yml` logs in with the workflow's OIDC token instead, which proves the
  namespace through the repository and needs no secret. Run it by hand for an existing tag, or set
  the repository variable `MCP_REGISTRY_PUBLISH` to have `release.yml` call it after each release.
  It checks that `server.json` names the tag's version and that the version is on PyPI before it
  publishes, and pins `mcp-publisher` to a version and a SHA-256. (#60)

### Fixed

- **The release guide advised `mcp-publisher publish --dry-run`, which publishes.** `publish` has no
  such flag, so an unknown one is ignored and the listing happens. The guide now says to use
  `validate`, which checks the manifest against the live registry and changes nothing. (#60)

## [0.8.0] - 2026-10-02

Models can now be told how to write Scenet, and can check what they wrote: a spec pack, an
Agent Skill and an MCP server. A comic's marks — sweat, dizziness, oaths, dust — join the
language, and diagnostics in comic scripts and shared casts now point at the right line.

### Added

- **Emanata: what a comic draws around a character.** A cast member takes `marks:`, a list
  from Mort Walker's *Lexicon of Comicana*: `plewds` (sweat flying off the head), `squeans`
  (dizziness), `grawlixes` (an oath, as a spiral, a star, a bolt and a hash) and `briffits`
  (the dust of a hasty exit). A list rather than a second `expression:`, because they compose
  — a character can be angry *and* sweating. Every puppet gets every mark; nothing new is
  declared per puppet. At `long_shot` each mark collapses to a dot, and a figure too small to
  have a face has none. (#21)
- **Marks cost a balloon space, and never move anybody.** They are drawn outside the head,
  where balloons go, so each mark has a zone that balloons and captions pay to cover —
  weighted above covering a body, with no discount for the speaker. They stay out of the
  hull, so staging, the camera and every figure are exactly where they would be without them,
  and a crowded panel still compiles. The camera makes no room for them either, so a mark
  cropped by a tight shot is reported in the compile notes. The debug overlay draws the zones.
- `scripts/contact_sheet.py --marks` renders every mark across the shot ladder, and the
  gallery gains `23-emanata.scene.yaml`.
- **A way to tell a model how to write Scenet.** The **spec pack** puts the language
  reference, the shot types, the comic-script format, the shipped characters, every
  diagnostic rule, the JSON Schema and the whole gallery in one file, published at
  [`/scenet-spec.md`](https://creatoan.github.io/scenet/scenet-spec.md) beside an
  [`llms.txt`](https://creatoan.github.io/scenet/llms.txt). It is what to hand a chat app
  that cannot run code, such as NotebookLM, which can then write a comic script for you to
  compile. [`skills/scenet`](https://github.com/creatoan/scenet/tree/main/skills/scenet) is
  an [Agent Skill](https://agentskills.io/) for coding agents. All of it is generated from
  the compiler's own sources, and a test fails if a committed copy goes stale. (#11)
- **`scenet mcp`, an MCP server**, so a model can validate its own panel, read findings
  that name the rule, the line and the fix, and render the result with nobody relaying
  errors. Five read-only tools — `get_spec`, `list_puppets`, `validate`, `compile`,
  `render` — over stdio or Streamable HTTP, on protocol revision 2026-07-28. It needs the
  new optional extra: `pip install 'scenet[mcp]'`. A `server.json` describes it for the
  official MCP registry. (#11)
- [Driving Scenet from a model](https://creatoan.github.io/scenet/howto/drive_from_a_model.html),
  a how-to for each kind of client, and two entries in prior art: WordsEye, the ancestor of
  text-to-scene, and Gumin et al. 2025, the strongest argument against a declarative
  language, recorded for what it actually found. (#11)

### Changed

- **Panel Core actors gain `marks`, `emanata` and `emanata_zones`.** All default to empty, so
  `format_version` stays 1 and a Core document written before them still reads. Every actor
  now serialises the three keys, so a golden file captured against 0.7.0 will differ by them
  — and by nothing else: every example in the repository lays out byte-identically.

### Fixed

- **A comic script's line numbers counted from the end of its front matter**, not from the
  top of the file, so `scenet check` and the playground pointed several lines above the
  fault in any script with a cast block — which is nearly all of them.
- **A panel in a comic script that failed validation** — a misspelled `@shot:`, say — was
  reported at line 1 whichever panel it was. It is now reported at that panel's `PANEL`
  heading.
- **A bad name in a shared cast was reported once per panel**, every copy pointing at the
  panel rather than at the line that was wrong — in a comic script's front matter, all
  of them at line 1. A fault in a scene's defaults or a script's front matter is now
  reported once, where it is written. A panel's own mistakes still carry its name.
- **`scenet build` printed a traceback for a file with an unsupported extension**, and
  `scenet check` called the same file `ok`. Both now report it as a usage error, exit 2.
- **`scenet build foo.panel.yml` wrote `foo.panel.yml.svg`.** `.yml` is now named
  exactly as `.yaml` is: `foo.svg`.
- The command-line reference's `scenet check examples/gallery/*.yaml` examples failed,
  because the glob also matched the gallery's manifest. CI's gallery check now includes
  the gallery's comic script, which it had skipped.

## [0.7.0] - 2026-10-02

The playground became a place to work, the editor schema stopped rejecting valid
documents, and the project moved to the `creatoan` organisation.

### Added

- **The playground became a place to work, not just a demo.** The output zooms and pans —
  scroll or pinch about the pointer, drag, double-click for Fit or 100%, `+ - 0 1` and
  the arrows — and keeps the zoom while you edit. **Download** saves the panel as SVG or a
  2× PNG, the overlay, the Panel Core and the source, named as `scenet build` names them;
  `Ctrl+S` saves the source. Edits survive a reload, and **Share** copies a link that
  carries the whole document in its fragment, so no server is involved. A failed compile
  is reported by the same checker `scenet check` runs: each finding is a squiggle on its
  own line, and the list under the output jumps to it. Actors, staging relations and
  script verbs are coloured; Panel Core opens in a read-only editor with folding; the
  split between the panes can be dragged; the output can go full screen. The editor also
  shows the example at once instead of sitting empty while Python boots. (#45)
- `render_strip(..., debug=True)` lays out each panel's overlay where the strip puts the
  panel, so a scene has an overlay too. (#44)

### Changed

- **The project moved to [`creatoan/scenet`](https://github.com/creatoan/scenet).**
  GitHub redirects the repository, its issues and pull requests, and `git` remotes. The
  documentation and playground are now at
  [creatoan.github.io/scenet](https://creatoan.github.io/scenet/); **the old
  `azias.github.io/scenet` addresses do not redirect**, because GitHub Pages never does.
  If a YAML document names the schema, update its first line to:

  ```yaml
  # yaml-language-server: $schema=https://creatoan.github.io/scenet/schemas/panel.schema.json
  ```

### Fixed

- **The published JSON Schema rejected the syntax people write.** It described the IR,
  after the frontend has rewritten staging sentences, `- say:` wrappers, `place:` and
  partial scene overrides away — so 21 of the 22 gallery documents failed it, and the
  playground and the VS Code extension underlined lines that compiled. The new
  `scenet.schema` module puts each of those back; a test now validates every shipped
  example against the shipped schema. (#44)
- **The overlay wrote actor ids into SVG unescaped**, in an `id` attribute and in text
  labels. The playground puts that SVG into the page, so an actor id could close its
  attribute and add markup. Identifiers are now escaped as they already were in the
  panel itself. (#44)
- **`scenet check` reported a bad staging sentence or script entry against the whole
  document.** It now points at the entry — an unknown predicate, a malformed sentence,
  an unknown verb. (#44)

## [0.6.0] - 2026-08-27

Setting: a panel can now show where and when it happens — and a caption box can be
tinted to read against it.

### Added

- **The setting layer: a panel can show where and when it happens.** Every panel rendered
  figures on white; there was no `setting` block at all. Captions (0.4.0) shipped the
  cheap half of establishing place — a `locale` box can *say* `MIDNIGHT. THE DOCKS.` —
  and this is the expensive half.

  ```yaml
  setting:
    place: docks
    horizon: mid
    time: night
    weather: rain
  ```

- **Backdrops are described tonal masses, never drawn geometry.** Crisp architecture needs
  a vanishing point and this is deliberately a flat, orthographic compiler, so drawn
  buildings would fight the compiler's own model — soft masses have no perspective to get
  wrong. It is also how comics actually establish place: **notan** (Dow, *Composition*,
  1899) says place is read from the arrangement of masses rather than from rendered
  detail, and **aerial perspective** supplies the parametric rule — with distance, value
  contrast drops toward the atmosphere.
- **Twelve mass kinds, from COCO-Stuff supercategories** — `building`, `ground`, `plant`,
  `sky`, `solid`, `structural`, `water` outdoors, `ceiling`, `floor`, `furniture`, `wall`,
  `window` indoors. Taken from an existing taxonomy of *stuff* rather than invented, for
  the same reason the predicates came from Visual Genome. Not its leaf names: the real
  classes are `building-other` and `sky-other`, and nobody should have to type that.
- **Ten named places** — `alley`, `desert`, `docks`, `field`, `forest`, `mountain`,
  `office`, `room`, `shore`, `street` — each expanding into a mass list the author could
  have written themselves. That rule is what keeps a preset a library rather than a second
  opaque format, and it is enforced by a test. The expansion happens in the frontend, so
  the IR has no `place` field at all — the same treatment `alice left_of bob` gets.
- **`plane` reuses the existing painter's order** rather than introducing a second one.
  The three backdrop planes take negative depths; `foreground` takes one above the
  frontmost actor, so a foreground mass draws over the cast the way a silhouetted doorway
  does. Value follows from the plane and from nothing else, which is what keeps the notan
  reading literal.
- **`time` and `weather`.** `time` supplies the two ends of the value ladder rather than
  tinting a daytime panel, so `night` is a darker, narrower ladder — and the ladder stays
  monotonic in depth at every hour by construction. `weather` adds `fog` as a
  `feTurbulence` veil, and `rain` and `snow` as that veil plus falling marks.
- **`CoreBackdrop`** on Panel Core, carrying fully resolved numeric polygons and tone
  values — the same discipline as `capsules`, `blobs` and `face_marks`, so the emitter
  still makes no layout decision. Absent on a panel that says nothing about where it is,
  which is why this needed no `format_version` bump.
- **Masses are a soft cost for balloon placement, never an exclusion.** Balloons sit over
  backgrounds routinely; that is what a background is for. Covering one costs an order of
  magnitude less than covering a face, weighted so a foreground silhouette costs more than
  empty sky.
- **`scenet check` reports `unknown-place` and `conflicting-setting`**, each naming the
  field. A place and a mass list together is rejected rather than guessed at: a place *is*
  a mass list.
- **`scripts/setting_sheet.py`**, the calibration instrument — every place against every
  hour on one sheet, every weather on another. Whether three greys read as depth is not a
  question a test can answer, and four things moved because of what the first sheet showed.
- Gallery examples 19, 20 and 21, and a `docs/reference/language.md` section for the block.
- **Caption boxes can be tinted.** Captions shipped in 0.4.0 with four kinds and the
  typography that goes with them, and one value: `#ffffff`, hardcoded in the emitter. A
  `tone` key now chooses from a three-value palette.

  ```yaml
  - caption: {text: "Noon. Nothing for miles.", kind: locale, tone: ink}
  ```

  The failing case is the pale end, not the dark one. A caption box is opaque, so its
  lettering was never at risk — the text sits on the fill whatever is behind it. The
  *box* is what stops reading: against the ladder above, a white box on a noon sky is
  1.16:1, and only the stroke separates it at all.
- **The palette is rungs of the backdrop's own value ladder** — `paper` `#ffffff`, `pale`
  `#adadad`, `ink` `#090909`, the last two taken from the `day` row by index rather than
  restated, so lettering and backdrop cannot drift apart as either is tuned. `paper` is
  the default, so no existing panel moves. No free-form `fill:`, and no yellow: an open
  colour field would be this language's one open vocabulary, and the classic yellow
  `locale` box would be the first non-neutral value in the codebase.
- **`ink` inverts the lettering to paper** — reversed type — chosen by contrast in the
  solver and carried on `CoreCaption` as `fill` and `ink`. The same rule and the same
  reason as falling rain, and it leaves the emitter with no decision about which mark
  reads. Both fields are defaulted, so a Core document written before this still parses
  and no `format_version` bump was needed.
- **The lettering floor is enforced rather than asserted.** `contrast_ratio` in
  `solve/backdrop.py` measures WCAG relative luminance — the ladder is *spaced* in OKLab
  because that predicts even perceived steps, but legibility is *checked* against the
  published threshold. Every tone clears 4.5:1 against its own lettering, and every rung
  of every hour has at least one tone above 3:1 to sit on. This is the one visual rule in
  the compiler with an objective answer, so it is a test rather than a taste.
- Gallery example 22, a `tone` row and section in `docs/reference/language.md`, and
  `fill` / `ink` in `docs/reference/panel_core.md`.

- **`scenet check --deep`.** Runs the full compiler on any document that passes the
  cheap checks, to additionally catch `layout` and `balloon-placement` failures — the
  two rules in the catalogue that were in the catalogue but unreachable from `check`.
  Off by default: it costs a real compile, including font metrics, and `check` stays
  the cheap pass it is documented as unless asked otherwise.


### Changed

- **`long_shot` reframes noticeably wider, and `wide` with it** — headroom `0.14` → `0.28`,
  footroom `0.06` → `0.10`. `solve/camera.py` admitted the problem in a comment: with no
  environment to show, `long_shot` and `full_shot` crop at the same landmark and could
  differ only by a little headroom, so two rungs at the widest end of the ladder stayed
  degenerate. There is an environment now, so a long shot can mean what it says — the
  figure fills roughly two thirds of what a full shot does. **Every existing panel that
  asks for `long_shot` or `wide` renders smaller than it did.** The comment is gone and
  `docs/reference/shot_types.md` is updated.
- **`PanelSyntaxError` carries an optional `rule` and `loc`**, so a check the frontend
  performs itself can name a catalogue rule and a field instead of arriving as a generic
  `invalid-field`. Both default to nothing, so every existing raise is unchanged.
- **The determinism boundary is written down** in `docs/reference/language.md`: the
  contract is on the emitted SVG *text*, which stays byte-identical, and has never been on
  pixels. `feTurbulence` is reproducible by specification and browsers still agree only
  approximately on what to paint from it. Stated now, while adding the first feature that
  depends on it, rather than left for somebody to rediscover when a screenshot test flakes.
- `docs/explanation/prior_art.md`: shape grammars move from *future* to **load-bearing**,
  with the finding that no open-source Python CGA implementation exists — the reference one
  is commercial, inside Esri CityEngine — so the formalism is reused rather than a library.
  Notan, aerial perspective and COCO-Stuff are added as load-bearing; physically based sky
  models (Preetham, Hosek-Wilkie) are recorded as examined and rejected, since they solve a
  radiometric problem this compiler does not have.

- **`PuppetSpec.pose_angles` and `.expression_states` raise `UnknownPoseError` and
  `UnknownExpressionError`** on a name the puppet does not declare, rather than a bare
  `KeyError`. Both are also `KeyError` — following the precedent `UnknownPuppetError`
  already set — so `except KeyError` and the documented `Raises: KeyError` on both
  methods keep working unchanged.


### Fixed

- **`extreme_close_up` framed the forehead, not the eyes.** Its crop landmark (`eyes`)
  sits inside the face rather than at its edge, and the anchoring rule bottom-anchors
  every crop line — which put the eyes exactly on the panel's bottom edge and the rest
  of the eye region, and the whole face centre, below it. `extreme_close_up` now
  carries `footroom: 0.45`, the only lever that can move a crop line off the bottom
  edge; headroom cannot, because it shifts the figure down and shrinks it by exactly
  the same amount. `docs/reference/shot_types.md` explains why in the **Resolution**
  section, and the table now shows the footroom instead of `—`.
- **`scenet check` said nothing about an unknown `pose:` or `expression:`, then `scenet
  build` crashed with a bare `KeyError`.** The IR validates syntax and structure
  without knowing the puppet library exists, so `pose: smirking` passed every check and
  only failed once the solver tried to look it up. `check` now resolves every cast
  member's `reference`, `pose` and `expression` against the puppet library — reading it
  once per document, only when there is a cast to check — and reports `unknown-pose`,
  `unknown-expression` and (newly reachable from `check`) `unknown-puppet`, each with a
  `ruleId` and a location naming the field. This closes the `check`/`build` gap
  entirely rather than for two known bad field names: `--deep` (below) extends the same
  guarantee to `layout` and `balloon-placement`.


### Upgrading

Nothing was removed and no document stops compiling. Four things a caller should expect
to see move:

- **Every panel that asks for `long_shot` or `wide` renders smaller.** The two rungs at
  the wide end of the ladder were degenerate with no environment to show, and now that
  there is one they are not. This is the change most likely to be visible in your own
  panels.
- **`extreme_close_up` frames the eyes rather than the forehead.** Any panel using it
  renders differently, and correctly, for the first time.
- **Panel Core output has changed for any panel with a caption.** `CoreCaption` gained
  `fill` and `ink`, and `PanelCore` gained `backdrop`. All three are defaulted or
  optional, so a 0.5.0 document still parses and `format_version` did not move — but a
  golden file captured against 0.5.0 will differ.
- **Eleven names joined `scenet.__all__`** — `SettingSpec`, `Mass`, `MassKind`, `Plane`,
  `Spans`, `Horizon`, `TimeOfDay`, `Weather`, `PLACES`, `Place` and `CaptionTone`.
  Additions only; nothing was removed or renamed.

### Known limitations

- **A caption's tone is checked against the palette, not against the panel it lands in.**
  The contrast floors hold between every tone and every rung of the ladder, which is what
  makes them enforceable — but nothing warns you that *this* caption was placed over a
  foreground mass it barely separates from. The information is all present by the time
  the box is placed; the check is not written.
- **No yellow caption box.** The classic yellow `locale` box would be the first
  non-neutral value in the codebase, and the language has no colour policy to put it
  under yet. The three tones that shipped are neutral greys from an existing ladder.
- **A caption tone is per caption, with no panel-level default.** A letterer would set
  one once for a page; here you write it on each box that wants it.
- **A backdrop is tonal masses, and will not draw a specific building.** That is the
  design, not a gap — but it does mean `place: docks` gives you the docks in the way a
  thumbnail does, not in the way a background artist would.

## [0.5.0] - 2026-08-26

Faces: a character can now look like something.

### Added

- **Faces.** A character can now look angry, bored or asleep. `expression:` on a cast
  member selects one by name, exactly as `pose:` does — because a face is the same kind
  of thing as a body: a small closed set of arrangements a character can be in.
- **The odd part was that the face was already in the contract and simply never drawn.**
  The puppets declared `eyes` and `chin` landmarks and `eyes`/`mouth` anchors, `FaceSpec`
  reserved a disc no balloon may cover, and the emitter drew the head as one filled
  circle. This is the rendering that was missing, not new modelling.
- **Ten expressions, and they are a drawing convention.** `neutral`, `happy`, `laughing`,
  `coy`, `bored`, `scared`, `sad`, `angry`, `shouting`, `surprise` — Comic Chat's emotion
  wheel plus `surprise`, taken from a system that actually rendered faces for live
  conversations rather than from a psychology of emotion. They are the small closed set of
  faces comics draw, **not** a claim that a person feeling anger produces this face;
  Barrett et al. 2019 is recorded in `prior_art.md` so that claim is never reintroduced.
- **Feature points, named after MPEG-4 FDP groups** — brow, eye, nose, mouth — with a
  mapping to MediaPipe landmark indices in the asset contract. The groups are the reusable
  part; the standard's 66 displacements are a measurement, not a notation. No jaw: the head
  is a circle that does not deform, so a jaw group would have nothing to move.
- **`looking_at` finally shows on the face.** Pupils are aimed at whoever a character is
  looking at, using a vector computed after placement and stored as `CoreActor.gaze_aim`.
  The existing `gaze` was the head's forward direction — horizontal for every actor in
  every panel, since no pose rotates the head — so a pupil offset by it would have shown
  nothing that mirroring did not already show.
- **`CoreActor.face_marks`**, as sampled polylines and discs. Curves are sampled during
  compilation, so everything an expression does is a number in Panel Core and the emitter
  keeps making no decisions.
- **`scripts/contact_sheet.py`** renders every expression at every shot type onto one page.
  Whether a furrowed brow reads as anger at fourteen panel units is not a question a test
  can answer, and this is the instrument for answering it by looking.
- Two gallery examples: ten expressions across a scene, and a big close-up that is the
  first panel in the gallery to show a face at all.

### Changed

- **Level of detail.** Below a threshold face radius no features are drawn, because five
  of them inside a head a couple of dozen units across stop being a face and become a
  smudge. Panels large enough to show a face are unaffected.

### Upgrading

Nothing was removed and no document stops compiling. Two things a caller might notice:

- `CoreActor` gained `expression`, `gaze_aim` and `face_marks`. A panel whose puppets
  declare no features compiles exactly as before, but the shipped puppets now declare
  some — so **Core output for any panel using `alice` or `bob` has changed**, and a
  golden file captured against 0.4.0 will differ.
- `scenet.assets.contract` gained `Feature`, `FeatureSpec`, `ExpressionSpec` and the
  three state enums. They are puppet-authoring types and are not in `scenet.__all__`;
  `expression:` in a document is a plain name, as `pose:` is.

### Known limitations

- `extreme_close_up` frames the forehead rather than the eyes. The crop rule anchors a
  shot's landmark at the bottom of the frame, which is right for every rung except the
  tightest, where the landmark sits inside the thing being framed. Correct per
  `shot_types.md`, which is normative, and newly visible now that there is a face to
  look at.
- An unknown `expression:` is not reported by `scenet check` and fails the build with a
  bare `KeyError`, exactly as an unknown `pose:` has always done. Consistency was the
  deliberate choice; the fix belongs to the checker.

## [0.4.0] - 2026-08-26

Captions: a panel can now speak in its own voice.

### Added

- **Captions.** A panel can now state where and when it happens without a character having
  to explain it out loud, which is the thing writers are told not to do. `- caption: {text:
  "Midnight. The docks."}` in YAML, `CAPTION: Midnight. The docks.` in a comic script.
- **The four caption kinds are the letterers' own** — `locale`, `monologue`, `spoken` and
  `editorial`, from Blambot's *Comic Book Grammar & Tradition* rather than invented, as the
  predicates were taken from Visual Genome. Note for anyone who guessed otherwise:
  "narration" is not one of them.
- **Italic is a real face, not a skew.** The italic of the same family already shipped in a
  declared dependency, so the three italic kinds are *measured* in the face they are drawn
  in. A synthetic oblique would measure as the roman face and draw as neither, which is
  exactly the disagreement between solver and emitter the lettering tier exists to prevent.
- **Quotation marks are lettering, so the compiler applies them.** In a run of consecutive
  `spoken` captions each opens with a quote and only the last one closes — Blambot's rule,
  objective enough to test. They are added before measurement and carried through Panel Core
  in `lines`; marks added by the emitter would not fit the box drawn for them.
- **A caption may name an off-panel speaker.** `by` on a `spoken` caption is the one place
  in the language where an actor id is allowed not to resolve, and deliberately: somebody
  off panel is not in the cast, which is the whole point of saying they are off panel.
- **`PanelCore.captions`**, and a sixteenth gallery example.

### Changed

- **Balloons and captions are placed in one pass, sharing one reading order.** `order` now
  counts across both, so a caption written between two lines of dialogue takes the number
  between theirs. Placing every caption first would have been simpler and wrong — a caption
  written last would have imposed reading order on the balloons before it. Panels without
  captions are unaffected, which is why the Core format version did not move.

### Upgrading

Nothing was removed and no document stops compiling. A panel with no captions compiles to
byte-identical Core. Three things a caller might notice:

- `PanelCore` gained `captions`, and `CoreBalloon.order` is now a position in the panel's
  whole reading order rather than an index among balloons. They differ only once a panel
  has a caption in it, so anything reading `order` as "which balloon is this" wants
  `balloons.index(...)` instead.
- `scenet.__all__` gained `CaptionEvent` and `CaptionKind`.
- `solve.balloons.place_balloons` is now `place_script` and returns a `ScriptLayout`
  rather than a tuple of balloons. `scenet.solve` is internal and outside the versioning
  promise, but it is a name that existed and does not any more.

## [0.3.0] - 2026-08-26

Diagnostics a machine can read, and the deploy that had quietly been failing for a week.

### Added

- **`scenet check`** validates documents without compiling them, and exits non-zero if
  anything is wrong. It does not stop at the first fault: pydantic reports every field
  error at once, and several files are reported together, because whoever is fixing them
  — a person or an agent — wants the whole list rather than one round trip per mistake.
- **`--format sarif`** emits [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html),
  the OASIS standard GCC, Clang and MSVC emit and GitHub code scanning ingests directly.
  **This matters more than the published JSON Schema does**: the checks that catch what a
  generator actually gets wrong — every actor id resolving to a cast member, the
  `left_of`/`right_of` graph being acyclic — are `model_validator`s, and neither is
  expressible in JSON Schema at all. Structured diagnostics are what make a
  generate/validate/repair loop work.
- **A stable rule catalogue.** Every finding carries a `ruleId` such as
  `scenet/unknown-actor`, and those identifiers do not change across releases — a
  `ruleId` that moves silently closes every alert referencing the old one and opens a
  duplicate under the new one.
- **`scenet.diagnostics`** is a public module: `diagnose_source`, `diagnose_file` and
  `to_sarif` give the same findings without the process boundary.
- **CI checks the gallery** and uploads the result to code scanning, so a broken example
  becomes an annotation on the pull request that broke it.

### Fixed

- **Diagnostics now name the field rather than the document.** pydantic reports a
  model-level validator's location as `()` — the whole document — because a validator has
  no way to say which field it was unhappy about. The two checks that matter most both
  knew the exact path and had nowhere to put it, so an unknown speaker reported
  `at <root>`. It now reports `at script.0.by`, in the prose output as well as in SARIF.
- **The documentation site and playground had not deployed since `6a43750`.** The
  playground refuses a wheel older than the source it was built from — a guard that
  exists because a silently stale playground once cost an hour. Its freshness walk
  covered every file under `src/`, including `__pycache__`, and the Pages workflow builds
  the wheel *then* builds the documentation, where Sphinx `autodoc` imports `scenet` and
  the interpreter writes fresh bytecode. So every deploy compared the wheel against its
  own doc build and refused. `v0.2.0` shipped while this was broken.
- **The stale-wheel error now names the offending file.** "older than `src/`" pointed at a
  directory of four hundred files when the culprit was one nobody thinks about.
- **`scenet check` understands scene documents.** A `panels:` document validated as a
  single panel reported `panels` as an unknown key — a confident, wrong diagnostic on
  every valid scene file in the repository. Found while wiring the gallery into CI.

### Changed

- **`ScriptSyntaxError` carries its line as a number**, not only inside the message text,
  so comic scripts get positions too. Lines only: a script line is prose, and a column
  would imply a precision the parser does not have.
- **`RuleViolationError`** is a new exported error type. It is raised only inside pydantic
  validators and never escapes as itself, so it deliberately does not inherit
  `ScenetError` — that would promise an `except ScenetError` clause could catch it.
- **CI builds the playground assets**, so a break there fails a pull request instead of
  the Pages deploy after merge.

### Upgrading

Nothing was removed and no document stops compiling. Two things a caller might notice:

- Diagnostic messages for unresolved actor ids and ordering cycles now name a path
  instead of `<root>`. Anything asserting on the old `at <root>:` text will need updating.
- `scenet.errors.__all__` gained `RuleViolationError`.

## [0.2.0] - 2026-08-26

A correctness release for the shot ladder, and a pass over the things the project says
about itself. **Panels using `medium_full`, `long_shot`, `full_shot` or `wide` render
differently than they did in 0.1.0** — see below before upgrading.

### Fixed

- **Shots that show feet now actually show them.** The crop lands the `feet` *landmark* on
  the frame edge, but the drawing continues past it: the ankle sits exactly on that
  landmark and the shin is a round-capped stroke, so half its width fell below. At long
  shot that was nine panel units hanging outside a 560-unit panel — the one thing a long
  shot is defined by not doing. `ShotSpec` gains `footroom`, non-zero only for the shots
  that show feet. It is also right compositionally: a figure standing on the exact bottom
  edge reads as falling out of the panel rather than standing on anything.
- **`medium_full` and `cowboy` are no longer the same shot.** Both cropped at `mid_thigh`,
  so the ladder had nine rungs while claiming ten, and two adjacent panels in the gallery
  were identical for no reason a reader could see. Medium full — the three-quarter shot —
  cuts at the **knees**; the cowboy or American shot cuts at **mid-thigh**, a framing that
  comes from 1930s Westerns needing the holster in frame. Two tests asserted they were
  aliases, so the bug was pinned in place by its own test suite.
- **The normative shot-type table was wrong.** `docs/reference/shot_types.md` calls itself
  normative and claimed `long_shot` had a headroom of `0.60`; the code uses `0.14`. It also
  still listed `cowboy` as an alias. A test now parses that table and asserts every crop
  landmark and headroom matches the code — a specification nobody checks is a comment in a
  different file.
- **The language reference no longer says nothing works.** `docs/reference/language.md`
  opened by telling every reader — and every model retrieving it — that "at present,
  nothing compiles", which stopped being true at phase 1, while `status.md` two clicks
  away listed phases 0–6 as done and called itself authoritative. The more-read document
  was the wrong one.

### Changed

- **`wide` remains an exact synonym for `long_shot`**, and the gallery example now says so,
  so the two identical panels read as intentional rather than broken.
- **The playground moved above the fold** in `README.md` and `docs/index.md`, and the
  repository homepage points at it. It runs the real compiler under Pyodide and it was the
  last section of the landing page, below the licence in reading order.
- **`docs/explanation/status.md` gained a Planned section.** Its phase table stopped at 6,
  so everything in the tracker was invisible in the one document claiming to be
  authoritative. The tickets are listed without numbering them into phases, because that
  order is genuinely not decided.
- **`docs/index.md` names Diátaxis.** The four sections always followed it; saying so tells
  a contributor where a new page belongs.

### Upgrading

No document stops compiling and no API changed. What changed is geometry, so identical
input produces different SVG:

- `medium_full` crops at the knees rather than mid-thigh, drawing the figure smaller.
- `long_shot`, `wide` and `full_shot` reserve footroom, which reduces the space available
  to the figure and so its scale.

If you have committed `.core.json` or SVG output for panels using those shots, regenerate
it.

## [0.1.0] - 2026-08-23

First release. A comic panel goes in as a semantic description and comes out as SVG,
deterministically — constraint solving and computational geometry, with no generative
image model anywhere in the pipeline.

### The language

- **Panel documents** (`*.panel.yaml`): panel size and margin, camera shot and angle, a
  cast of characters with poses and anchors, staging relations written as sentences
  (`alice left_of bob`), and dialogue.
- **Sequences** (`*.scene.yaml`) with `over:` sparse override, borrowed from OpenUSD's
  composition arcs: a panel names a parent and states only what differs.
- **Comic script** (`*.script`), the format writers already use, with a YAML preamble for
  what a script has no way to say. Prose descriptions are preserved and never interpreted.

All three produce the same validated IR, so nothing downstream knows there is more than
one syntax.

### The compiler

- **Camera framing** from anatomical crop landmarks — the waist, the chest, the shoulders
  — rather than a fraction of panel height, so a shot type does not bake in one body and
  one pose. One camera and one scale per panel.
- **Actor placement** through a Cassowary solver, with priorities: non-overlap and declared
  ordering are required, panel bounds are strong, requested anchors are weak. A crowded
  panel lets a figure bleed off the edge rather than refusing to compile.
- **The camera retreats** when a cast will not fit across the frame, and says so, because a
  panel that is quietly not the shot you asked for is a panel you cannot debug.
- **Lettering** measured against real font metrics, with line breaking scored on the shape
  a letterer would choose. The font is a declared dependency, never a system lookup —
  determinism requires text to measure identically everywhere.
- **Balloon placement** by scored candidate search: a balloon may never cover a face, and
  reading order is a hard constraint checked against every predecessor rather than only
  the last one.
- **Tail routing** that stops at the face outline instead of the mouth anchor buried
  inside the head, and bends around an obstructing face when it must.

### Three tiers, all of them yours

```
*.panel.yaml  →  IR (scene graph)  →  Panel Core (.core.json)  →  SVG
```

Panel Core is a real, writable format rather than a hidden data structure: a layout can be
exported, read, diffed, hand-adjusted, and read back for emission.

### Tools

- `scenet build`, with `--core`, `--debug`, `--strip` and `--live-text`.
- `scenet schema`, generating the JSON Schema from the compiler's own models.
- A **browser playground** running the compiler unmodified under WebAssembly via Pyodide,
  with a Monaco editor fed that same schema, and fifteen worked examples. Entirely
  self-hosted: it makes no request to any other origin.
- A **VS Code extension** with schema-driven completion, validation and a live preview.

### The library

- `import scenet` exposes a curated public API: compiling, parsing, rendering, both
  intermediate tiers, the describing types, puppets and one error hierarchy rooted at
  `ScenetError`.
- Ships `py.typed`, so downstream type checkers read the annotations directly.

### Documentation

Structured on Diátaxis — tutorial, how-to, reference, explanation — and built with Sphinx.
**Every Python example is executed by the test suite**, so an example that omits an import
or has drifted out of step with the code fails the build.

### Security

- Identifiers and dialogue are escaped into their SVG attributes and elements. An actor id
  containing a quotation mark could previously close its own attribute, which is a
  scripting vector wherever the output is rendered inline.
- Dependency licenses are gated in CI against an explicit allowlist, checked against a
  runtime-only environment.
- Published to PyPI through Trusted Publishing with Sigstore attestations, so the
  repository holds no publishing credential of any kind.

### Known limitations

- Page composition — tiers, panels of varying size, the page-level reading path — is not
  built. `--strip` lays panels in a row and nothing more.
- There is no interpretation layer: a panel has no *style*, and figures render as
  wireframe puppets.
- Prose in a comic script is preserved but never interpreted. Describing rain does not
  produce rain.
- `long_shot` and `full_shot` crop at the same landmark, so with no environment to show
  they can differ only by headroom.

[Unreleased]: https://github.com/creatoan/scenet/compare/v0.12.0...HEAD
[0.12.0]: https://github.com/creatoan/scenet/compare/v0.11.1...v0.12.0
[0.11.1]: https://github.com/creatoan/scenet/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/creatoan/scenet/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/creatoan/scenet/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/creatoan/scenet/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/creatoan/scenet/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/creatoan/scenet/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/creatoan/scenet/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/creatoan/scenet/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/creatoan/scenet/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/creatoan/scenet/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/creatoan/scenet/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/creatoan/scenet/releases/tag/v0.1.0
