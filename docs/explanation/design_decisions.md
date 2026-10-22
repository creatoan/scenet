# Solver and toolchain choices

Non-obvious decisions, with reasoning, so they can be revisited rather than rediscovered.

## Shot types are crop landmarks, not panel fractions

The tempting definition of a medium shot is "the figure fills about 60% of panel height". It is
wrong. A shot type names **where the frame cuts the body** — waist, chest, shoulders. What fraction
of the panel the figure then occupies is a *consequence*, and it differs for a child versus an
adult, or a seated versus a standing pose. Encoding the fraction bakes in one body and one pose.

See [shot_types.md](../reference/shot_types.md), which is normative.

## Notes report a house limit; errors a contradiction

Every finding was an error, and any finding failed `scenet check`. That was right while every
rule was a contradiction — an actor not in the cast, staging that loops — which no compile
can get past. Dark Horse's "approximately 25 words per balloon, and about 50 words per panel,
max" is a different kind of thing: a limit a letterer works to, which a panel can exceed and
still be drawn. Failing a check over it would make the check lie about whether the document
builds, and CI would key off the lie.

So a rule has a level. An **error** fails the check, and is exactly what stops `build`; the
seam between the two is tested as "no errors if and only if the build succeeds". A **note** is
reported with its rule and its place, as SARIF `note`, so an editor shows it as information,
and never fails anything. `--deep` runs on a document with notes, since notes do not stop the
compile it would run.

## Small and weak lettering are one size

Dark Horse names `(small)` and `(weak)` beside `(burst)`. Blambot defines small dialogue by its
effect — "a reduced font size is used when a character mutters something" — and the balloon stays
the size it would have been, so the line reads as said quietly rather than as a small balloon.
`say.size: small` is exactly that: type at three quarters of the panel's dialogue size, padded as
normal type would be. Blambot's script guide reads `(WEAK)` as "dialogue should be diminished", so
a weak line is small too. Comicraft also letters weak dialogue in an erratic hand; that is not
drawn, since no source fixes what the hand should be, and drawing an invented one would be worse
than drawing none.

## An off-panel speaker is not in the cast

Off-panel speech needs a speaker who is not drawn, and every speaker used to have to be in the cast
— which is the list of who *is* drawn. So `off_panel` lets `by` name anybody, and forbids naming a
cast member: somebody both drawn and off panel in one panel contradicts themselves, and is
`off-panel-speaker`. The tail ends on the frame (Blambot), never nowhere: a tailless balloon was
considered and set aside, since a balloon with no pointer has no attributed speaker. Panel Core
records the side the solver settled on, so a reader of the Core knows the tail's end is on the
frame and the speaker is not an actor; the field is left out when unset, and every Core written
before it is unchanged.

## Cassowary is linear, so the language must resolve disjunctions

Non-overlap between two actors is a disjunction — A left of B, **or** B left of A — and no linear
solver can express a choice. Rather than reaching for a mixed-integer solver, the DSL resolves
ordering at parse time, so the solver always receives a linear system.

This is a *language* constraint, not merely an implementation detail: it is why there is no
unordered `beside` predicate. Any future construct that reintroduces a disjunction must resolve it
in the frontend.

## Balloon placement: candidate scoring, not a grid sweep

Discretising the panel into a cost grid and scanning every cell is the obvious approach, and is both
slower and worse. Balloons belong in a small number of sensible positions relative to their speaker.
So candidates are generated map-labelling style — a ring of directions and radii around the
speaker's head, plus the panel corners — and scored. Fewer evaluations, more natural results.

## Emanata are a soft cost, not part of the hull

Plewds, squeans, grawlixes and briffits are drawn outside the head circle, which is exactly where
balloons go, so they had to mean something to the solver. There were three choices:

- **Enter the hull.** The simplest, and wrong. The hull is also what staging spaces characters by
  and what the camera fits, so a character who started sweating would stand further from everyone
  else, and the framing could retreat. A mark would move people the author never asked to move.
- **Forbid them outright, as a face is.** A face exclusion is affordable because a face is one small
  disc that tails already route around. Emanata ring the head and sit on the ground behind it; making
  all of that illegal turns a crowded panel into `BalloonPlacementError` over a drop of sweat.
- **A cost of their own.** Each mark has a zone, and a balloon or caption pays for the fraction of
  its box that covers one — the same normalisation as hull occlusion, weighted above it, because a
  balloon over a shoulder hides a shoulder and a balloon over a plewd deletes what the panel was
  saying. The speaker gets no discount: their balloon over their own sweat still hides it.

The third is what shipped. Its proof is in `tests/test_emanata.py`: every example in the repository,
recompiled with every mark on every cast member, puts every figure exactly where it was and still
compiles; and a panel without marks is byte-identical to one compiled before marks existed.

The cost of not moving anybody is that the camera makes no room either, so marks over the tallest
head can be cropped at a tight shot. That is reported as a note rather than silently drawn off the
page.

## Sound effects are picture: placed first, exempt from reading order, paid for by balloons

A sound effect is lettering treated as art, so three decisions follow from treating it as art.

- **Reading order.** Balloons and captions share one hard sequence. Dark Horse's format wants sound
  effects listed in it too, but a sound sits where the sound is, and holding it to above-and-left
  would make many panels impossible to letter. Of the three options in #73 — in the sequence under
  the rule, in it but exempt from the geometry, or outside it — the second shipped: an effect takes
  its `order`, which a reader of the text and accessible output follow, and is placed with no
  geometric constraint against any box.
- **When it is placed.** Before every balloon and caption, as the art is: lettering is placed over
  the picture, knowing where it is. An effect is placed after staging and the camera, from the
  figures they produced, and reaches neither, so nobody moves for one — the same proof as emanata.
- **What it costs.** Its footprint joins the emanata as ground a balloon or caption pays to cover,
  at the same weight, and is never forbidden to. A balloon over a sound effect deletes what the panel
  was saying, which is the argument emanata already made; forbidding it would turn a crowded panel
  into a placement error over a sound. It is drawn under the lettering for the same reason: when a
  balloon does cover one, the words stay readable.

Its own hard rules are a box's — never a face, never out of the frame, never under an inset — plus
never over another effect. It is set in a display face, bent and turned as transforms of the glyph
outlines Scenet already draws, so an arc comes out the same in every renderer; SVG's `<textPath>`
would have handed the layout back to the renderer and to installed fonts.

## Figures a picture draws come with a contract, beside the picture

When the people are in a supplied picture (#71), the solver still needs each face, mouth and body,
and still may not look at the picture. An [artwork contract](../reference/asset_contract.md#artwork-contracts)
declares them, as a puppet's contract declares its skeleton. What #71 left open was decided this way:

- **The contract is found beside its picture, by name.** `art/p01.png` has `art/p01.art.yaml`. The
  issue sketched `setting.image` naming the contract, and the contract naming its picture; that
  overloads `image`, joins two paths into Core's `href`, and breaks when a picture is renamed. A
  `contract:` key beside `image` lets the two name different pictures. By name, the pairing cannot
  drift, and the playground's renaming of uploads treats both alike. It is read only for a panel
  whose cast names a figure, so a file beside a picture never changes output by being there.
- **The size is the picture's, exactly.** A contract measured on another export would put every face
  elsewhere, and scaling it to fit would need a tolerance that hides a re-export. It is refused, and
  says to measure again or to scale the coordinates.
- **Every declared face is in the panel, cast or not**, because a painted face is a face. A cast
  figure the panel's picture does not draw is simply not in that panel, so a script's front matter
  can cast a chapter's figures over many pictures; a line it speaks there is the finding, and is
  where a misspelt name surfaces.
- **The camera and staging do not run, and are refused when written.** The artist framed and staged
  the picture; a `camera:` or a relation naming a figure would be a key with no effect, which this
  language reports, as it reports a horizon beside a picture. Gaze is not declared — a detector
  could not propose it reliably, and nothing else needs it — so the gaze term costs a figure
  nothing; an optional key could add it later without a format change.
- **Casts are not mixed.** A puppet staged in front of painted people would be placed by a solver
  that cannot see them, and could stand on a face. That is the hard half of a mixed cast, so it is
  refused rather than half-supported.
- **A cropped mouth is not a finding.** Under `cover` a mouth can fall outside the panel; whether it
  does depends on a frame size a page imposes, which the cheap pass does not know. Lettering stays
  inside the panel as it always does, the tail ends on the frame aimed at the mouth, and the build
  notes it.
- **Core gets a figure of its own**, `figures` beside `actors`, not optional `CoreActor` fields that
  would let a puppet Core with no transform validate. Empty, it is left out, so `format_version`
  stays 1.
- **A fault in a contract is reported in it** when the document is checked as a file — the editor
  and SARIF already file a result by its uri — and at the line naming the picture when it is checked
  as text, where the author can only see the document.
- **Detection is a helper, and not built.** A contract is a handful of numbers, and the debug overlay
  checks them against the picture. A detector inside the compiler would make output depend on a
  model and a platform, and could not run in the playground; see
  [prior art](prior_art.md#magi-a-helper-that-could-propose-a-contract).

## A panel is one image, read whole, in reading order

Accessible output (#76) makes each panel `role="img"`, named by one `<title>`: the description,
then every balloon, caption and sound effect's label, in `order`. The sources behind it are in
{ref}`prior art <accessible-svg>`, and the screen-reader results in
[the how-to](../howto/make_accessible_output.md#recorded-results).

- **One image, not a document of named parts.** The issue held up Vega-Lite's per-mark labels as
  the precedent, and Vega's own output is a `graphics-document` with `graphics-symbol` marks. That
  was examined and not taken. No published test says what NVDA, JAWS or VoiceOver do with
  those roles, the ACT rule calls their support inconsistent, and Firefox reduces the document
  to a plain one. With a group of named parts, document order would be reading order — and a
  sound effect is painted under every balloon, so it cannot be in its place in that order
  without changing the picture. As one image, the panel is read in the one order Core keeps,
  whatever the paint order. Its children are presentational, so nothing inside it is named.
- **The words are in the name, and in nothing else.** A description is often not spoken —
  Lembree's NVDA and JAWS results, NVDA's own guide — so `aria-describedby` alone would leave the
  dialogue unread. The first version named the panel through `aria-labelledby` by a `<title>`
  and a `<desc>`, the most-tested pattern in the published results. NVDA 2026.2 with Edge 155 read
  it in full, once, in browse mode — and a second time, the `<desc>` as the description, every
  time it moved to the panel by graphic. Of six ways of naming it tried in the same session, one
  `<title>` holding everything read once both ways, and needs no id, so a page that inlines
  several panels cannot name one with another's words. The cost is a long tooltip.
- **Strips and pages are groups of panels.** `role="group"` is what every engine computes; the
  panels are its images, in reading order — which is why a page now writes its panels in reading
  order and cuts each inset's parent around it rather than painting the inset last.
- **The words are resolved in the pipeline**, in `solve/describe.py`, and carried in Panel Core;
  the emitter copies them. Generated text is templated English, and says so.
- **`aria=False` is exactly the SVG written before.** A golden variant holds every gallery
  document built `--no-aria`, and its digests are those the default build had before.

## Right to left mirrors the reading, never the picture

`direction: rtl` (#68) is decided by one test: compile the mirror image of a panel right to left,
and every balloon and caption lands at the mirror of where left to right puts it in the original.
Everything reading decides is mirrored to pass it, and nothing the picture decides is touched.

- **The document's, not a panel's.** EPUB and ComicInfo say it once per book, and a page read one
  way holding a panel read the other has no order a reader could follow. So a panel's own
  `direction` is `panel-direction`, and a scene's or script's panels inherit the document's.
- **The order.** Never above-and-right of a predecessor, the exact mirror of the left-to-right
  test, still checked against every predecessor.
- **Tiebreaks are mirrored, not just the rule.** The first candidate wins an exact tie. The ring
  around a head used to try up-right first and the corners top-left first, so with the rule alone
  flipped, a right-to-left panel would have been a mirrored-but-different layout. Each candidate
  list is now built so that, read right to left, candidate *i* is the mirror of candidate *i* read
  left to right. The tests check the order, never a tie, since a near-tie can fall differently on
  another platform.
- **A written zone is a place; an unwritten one is where reading starts.** `prefer:` names a
  region of the panel and means it either way. A caption with none sat top left because that is
  where a locale caption conventionally sits, which is where reading starts. So `CaptionEvent.prefer`
  is `None` until the solver reads the direction. An off-panel voice with no side named starts
  there too, and a balloon dead centre goes to that side.
- **Sound effects stay put.** They are picture, placed first and exempt from the order. They keep
  their number in the one sequence, and their own tiebreaks, because the scene is not mirrored.
- **Tails and staging stay put.** A tail bends toward the side of its own line first, which has
  nothing to do with the page. Staging breaks a tie by anchor and id, never by "given to new" (see
  [prior art](prior_art.md)).
- **Text is not progression.** Lettering stays Latin, left to right, and captions stay flush left.
- **No disjunction comes back.** Reading order is a filter over candidates, not a Cassowary
  constraint, and the direction is known when the document is read.

## Text metrics are a hard dependency, not a detail

A balloon's size is a function of its text, wrapped at some measure, in a specific font. Nothing
downstream — placement, occlusion, reading order — can be computed until that size is known. The
font is therefore bundled rather than referenced, and measurement uses `fontTools` against that
exact file. If renderer and measurer disagree even slightly, output stops being deterministic.

## A font is a file beside the document, and Core names it by its bytes

An author's lettering face is declared as a path, read relative to the folder the document is in,
and an absolute path is refused. Three things follow from that one rule. A document and its fonts
move together and compile the same anywhere. A server that compiles documents it is sent cannot be
pointed at files of its own. And no path reaches any output: Panel Core records a face by its
family, style and the SHA-256 of its bytes, which is the same on every machine — `tests/test_golden.py`
already holds the output to not depending on where a document is.

The digest is also what keeps measurement and drawing together once they are separate steps. A
renderer is handed fonts by digest and refuses a Core that names one it was not given, rather than
drawing lettering in a face it was not measured in. Fonts are cached by digest too, so a file
replaced in place is read again.

The path rule lives in `scenet/paths.py`, written to be shared, and a picture to letter over (#70) is
read by it too: the same paths and the same refusals, and in Panel Core the same identity, a digest
of its bytes. A caller with no folder — text compiled with nothing behind it — may hand over the
files themselves instead, by the path the document writes; they are read from memory, never
written to a folder of the server's.

## The default face stays Source Sans Pro

Comic Neue (Craig Rozynski, SIL OFL 1.1) was the candidate to replace it, as a face with a lettering
feel that can be shipped. It was not adopted here. The choice is to be made on legibility at balloon
sizes rather than taste, which is a comparison of pictures, and the change that makes it cheap to
run is this one: declare the face beside a document and compile the gallery in both. Switching the
default would also move every example's output a second time and needs the face packaged, since no
PyPI package carries it. Until a comparison says otherwise, an author who wants it names it.

## Kerning is applied, because the outlines are positioned here

Pair kerning was ignored at first, on a sound argument: SVG renderers do not agree on whether to
kern `<text>`, and a measurement the renderer will not reproduce is worse than a slightly generous
one. That argument is about `--live-text`. The default emits glyph outlines, and Scenet positions
every one of them itself, so no renderer has a say: a pair adjustment that is measured is drawn,
exactly. So kerning is applied, to measurement and outlines through one function, and live text is
the best-effort mode it always was.

The pairs are read with `fontTools` from the GPOS `kern` feature, or from a legacy `kern` table in a
font with no GPOS kerning. HarfBuzz would shape the text for us, but Pyodide does not ship it and the
playground installs the same wheel as the CLI, so it is a dev dependency instead — the **oracle**.
`tests/test_kerning.py` checks every ordered pair of the characters the tests letter, in all three
faces, against HarfBuzz's advances. A hand-picked pair would not have caught the rules that matter:
the first subtable that covers a pair answers for it, and a class pair applies even when its value is
zero.

Only pair adjustments are applied: no ligatures, no contextual alternates, no mark positioning. That
is all a Latin line of lettering needs, and all that measurement can promise to reproduce. Two faces
are two fonts, so a stressed word in bold italic is not kerned against its roman neighbours.

Adopting it moved every example once: box widths changed by between −1.4% and +0.4%, since a pair can
loosen as well as tighten, one two-line balloon
fit on one line, and a few balloons whose candidate positions had scored nearly equal chose
differently.

## `ty` gates the build; `basedpyright` advises

[`ty`](https://docs.astral.sh/ty/) is Astral's type checker: fast, and consistent with `uv` and
`ruff`. It is also **pre-1.0 and in beta**.

Gating CI on a beta usually risks an upstream change reddening the build unbidden — but `uv.lock`
pins `ty` to an exact version, so it changes only when deliberately bumped. That objection does not
apply here.

The risk pinning does *not* solve is coverage: pre-1.0 `ty` is documented to miss advanced typing
patterns Pyright catches — Protocols, `ParamSpec`, recursive types, complex overloads. Since the IR
is pydantic models throughout and the solver will lean on Protocols, that is the wrong blind spot to
accept silently. So `basedpyright --strict` runs as a **second, non-blocking** job. Anything it
reports that `ty` missed is signal. Delete that job once `ty` reaches 1.0 and closes the gap.

## `TC001`-`TC003` are disabled deliberately

Ruff's flake8-type-checking rules want annotation-only imports moved into `if TYPE_CHECKING` blocks.
Declined, for two reasons:

1. **Pydantic resolves annotations at runtime** to build validators. An import hidden behind
   `TYPE_CHECKING` makes the model fail to build — and the IR is pydantic models throughout, so the
   rule is an active hazard rather than a style preference.
2. The import-time saving it exists for is largely gone in Python 3.14, which already evaluates
   annotations lazily (PEP 649/749).

That same PEP pair is why `from __future__ import annotations` is banned here: forward references
work unquoted, and the future import is on a deprecation path.

## License gate checks runtime dependencies only

Dev tooling is never distributed, so it is out of scope — which matters concretely, because
`hypothesis` is MPL-2.0 and would otherwise fail a permissive-only allowlist for no good reason. CI
therefore syncs with `--no-dev` first.

One trap worth recording: a bare `uv run` **re-syncs the project**, silently reinstalling the dev
dependencies `--no-dev` just pruned, so the gate checks the wrong environment and passes
meaninglessly. `uv run --no-sync` is required. This was caught by running the gate and reading its
output, not by reasoning about it — which is the general lesson.

## The documentation site serves every release from the site attached to it

The site's root used to be `main`, rebuilt on every push. So between releases it described
language a released `scenet` refused, the playground ran an unreleased compiler, and an
editor validating against `schemas/panel.schema.json` was checked against unreleased models.
Now the root is the latest release, `main` is under `/dev/`, and each minor version is under
`/vX.Y/` ([#171](https://github.com/creatoan/scenet/issues/171)). The layout is the one
pandas uses: stable at the root, development under it, old versions beside it.

**Where old versions come from.** A Pages deployment replaces the whole site and keeps
nothing, so every deploy must contain every version. Each release builds its site once, from
the wheel it publishes and before it publishes anything, and attaches it to the GitHub Release
as `scenet-X.Y.Z-site.zip`. `pages.yml` downloads those. The alternatives each failed on
something concrete:

- *Rebuilding every tag at deploy time.* The playground's build downloads the newest font
  wheels from PyPI, so a rebuild is not what shipped. Old lockfiles also rot.
- *A `gh-pages` branch.* At about 40 MB per version, it puts into history what every clone
  fetches. It also needs a workflow write token, and changes the Pages source setting.
- *A separate repository* needs a credential reaching across repositories.
- *Workflow artifacts* expire.
- *Read the Docs* moves the documentation to another domain, breaking every stable URL.
  It also injects its own script into a site whose playground's Content-Security-Policy says
  `'self'` and means it.

**What moves the root.** `pages.yml` runs on `workflow_run` when the Release workflow
completes, and only for runs a push started.

- `release: published` never fires, because the release is created with `GITHUB_TOKEN`,
  and events that token causes start no workflow.
- A deploy from the tag's ref is refused, because the `github-pages` environment allows
  only `main`.
- `workflow_run` runs on the default branch and needs no new permission.
- It is limited to push-started runs because a pull request can add a workflow with the
  same name, and its runs would set it off too.
- It is not limited to successful runs. A registry listing that fails after the release
  is out must not keep the root on the previous release.

Every deploy is a function of `main` and the releases' attachments. So a push rebuilds
`/dev/`, and everything else comes out byte-identical to the previous deploy.

**One build, at two paths.** A release's site is served at the root and at its `/vX.Y/`
unchanged, so nothing in it may depend on where it is:

- The playground's Vite base is relative.
- The documentation's links are relative already.
- The version switcher reads `/scenet/switcher.json`. The theme advises a fully resolved
  URL so that no build reads a stale copy of its own. A site-absolute path cannot do that
  either, and with it the local preview, served under `/scenet/` as Pages serves it, shows
  the real switcher before anything is deployed.
- The theme's build-time check of that file is off: it would fetch it over the network, and
  fail the build with `-W` whenever it is not there yet.

What a build does carry, `scripts/site_versions.py` checks on every page. That is which
version it documents, where the switcher is, and its canonical link.

**`main` says it is `dev`.** The theme hides its warning banner when a build's
`version_match` equals the preferred entry's `version`. Otherwise it calls the version an
unstable development one when the release string contains "dev", or an old one when it
compares lower. Between releases `main` carries the last release's version number, so it
would compare equal and get no banner. `SCENET_DOCS_VERSION=dev` labels it.

**Canonical links, not `noindex`.** Every page of every copy names its counterpart at the
root as canonical, as docs.python.org does from its 3.12 and development pages to `/3/`.
`/dev/` is not marked `noindex`: Google advises against using it to steer canonical
selection within a site. A project site cannot have a `robots.txt` either, since one is only
read at the host's root, `creatoan.github.io/robots.txt`. A page that has no counterpart at
the root — one removed since — points at a missing page, which a search engine ignores.

**By minor version.** Below 1.0 a minor version is where this project's language may change
(see [Releasing](../maintainer/releasing.md#versioning)), and a patch release is a fix to it.
So `/v0.11/` serves the highest 0.11 patch, and fixing a release's documentation means
cutting a patch release. numpy and pandas version their documentation by minor too.

**Old playgrounds retire.**

- A version's site is about 40 MB, of which the playground is 28 MB and Pyodide 22 MB.
- Pages caps a site at 1 GB, and its artifact may contain no links, so versions cannot
  share a copy.
- The root, `/dev/` and the three newest minor versions keep their playground.
- An older version keeps its documentation, schemas and spec pack. Its `playground/`
  becomes a page pointing at the latest playground, and at the complete site attached to
  its release.
- The assembly fails above 1 GB, before Pages would.

**Releases before 0.8 are not on the site.** Releases up to 0.11.0 predate the attachment,
and `scripts/backfill_site.py` builds one for them: the release's own sources and lockfiles,
the wheel it published, and only the files that version a build laid over them. That needs
the release's site tooling to be v0.11.0's, which holds from v0.8.0. Before that, the
documentation configuration itself differs. Those versions' documentation stays readable at
their tags on GitHub.

**Every version's playground shares one origin.** So a draft saved in one version's
playground opens in another's, where a construct from `/dev/` may not compile. A shared link
carries its document in the URL and is not affected.

**A playground learns its version from its address.** The page is the same in every version
and its build is not told which it is, but `switcher.json` names each version's address, and a
version's playground is `playground/` under it. Matching the address against the file needs no
label baked into the build, and shows nothing — rather than something wrong — wherever the page
is served without the file, as under `npm run dev`.

**Links to the playground are written absolute and built relative.** The Markdown links it by
its full address, the only kind that works where GitHub renders these pages. A transform in
`docs/conf.py` makes each such link relative in the built site, so every version's
documentation opens its own version's playground.

Sources:

- pydata-sphinx-theme, [version switcher](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/version-dropdown.html)
  and [warning banner](https://pydata-sphinx-theme.readthedocs.io/en/stable/user_guide/announcements.html)
- GitHub,
  [triggering a workflow from a workflow](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow),
  [`workflow_run`](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflow_run)
  and [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [upload-pages-artifact](https://github.com/actions/upload-pages-artifact) on links
- Vite, [relative base](https://vite.dev/guide/build.html#relative-base)
- Google, [consolidating duplicate URLs](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- [RFC 9309 §2.3](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.3) on where
  `robots.txt` is read
- numpy's and pandas' switcher data:
  [numpy](https://numpy.org/doc/_static/versions.json),
  [pandas](https://pandas.pydata.org/versions.json)
