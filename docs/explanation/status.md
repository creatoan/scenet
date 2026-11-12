# What Scenet does today

Everything here runs, and every example of it is compiled by the test suite. Each line gives the
release it arrived in. Work marked *not yet released* is on `main`, and in
[the documentation of `main`](https://creatoan.github.io/scenet/dev/), but not in what
`pip install scenet` gives you until the next release. [What's new](whats_new.md) has the detail,
release by release.

Each "Written as" names the key, command or function the feature is used through, which
[the language reference](../reference/language/keys.md), [the command line](../reference/cli.md)
or [the Python API](../reference/api/index.md) describes in full.

## Frontends

| Feature | Written as | Since |
|---|---|---|
| A panel, written in YAML | `panel`, `cast`, `script` | 0.1 |
| A sequence, each panel saying only what changed | `panels`, `over` | 0.1 |
| Pages of tiers, columns and insets | `pages`, `page`, `panels[].insets` | 0.10 |
| Slanted tiers | `tiers[].slant` | 0.10 |
| A comic script, as writers write it | `parse_script()` | 0.1 |
| Scripts in Dark Horse's published format, and in French | | 0.11 |
| A voice from off panel | `say.off_panel` | 0.11 |
| Scripts laid out as a manga script, a screenplay or a letterer's script | | 0.13, not yet released |
| Characters of your own, as puppet files | `load_puppet()` | 0.1 |
| A JSON Schema for puppet files, for completion in an editor | `scenet schema --puppet` | 0.13, not yet released |

## Layout

| Feature | Written as | Since |
|---|---|---|
| Shots framed by where they cut the body | `camera.shot` | 0.1 |
| Camera angles | `camera.angle` | 0.1 |
| Figures ordered, overlapped, grounded and looking at each other | `staging` | 0.1 |
| Balloons sized for their words, placed in reading order, with tails | `say` | 0.1 |
| Captions | `caption` | 0.4 |
| Faces and expressions | `cast.<id>.expression` | 0.5 |
| Settings: places, masses, the hour and the weather | `setting` | 0.6 |
| Emanata: plewds, squeans, grawlixes and briffits | `cast.<id>.marks` | 0.8 |
| A supplied picture behind the cast | `setting.image` | 0.12 |
| Figures a supplied picture draws, lettered around | `cast.<id>.figure` | 0.12 |
| Reading right to left, for manga | `direction` | 0.12 |
| Colour, as a twin of the value ladder | `palette` | 0.13, not yet released |
| Panels that bleed off the page | `panels[].bleed`, `page.bleed` | 0.13, not yet released |

## Lettering

| Feature | Written as | Since |
|---|---|---|
| Lettering drawn as glyph outlines, measured in the face it is drawn in | `render()` | 0.1 |
| Kerning, and emphasis in bold and italic | | 0.11 |
| A face of your own | `lettering.font` | 0.11 |
| One type size for a page, and small type | `lettering.size`, `say.size` | 0.11 |
| Sound effects, in the display face | `sfx` | 0.11 |
| The warm caption | `caption.tone: warm` | 0.13, not yet released |

## Outputs

| Feature | Written as | Since |
|---|---|---|
| An SVG for each panel | `scenet build` | 0.1 |
| A strip of a document's panels | `scenet build --strip` | 0.1 |
| Panel Core, the resolved layout, as JSON | `scenet build --core` | 0.1 |
| The debug overlay | `scenet build --debug` | 0.1 |
| Lettering as live text | `scenet build --live-text` | 0.1 |
| Output a screen reader reads, with a description of each panel | `description`, `scenet build --no-aria` | 0.12 |
| A supplied picture embedded, so the SVG stands alone | `scenet build --embed-images` | 0.12 |
| Exports for image models: pose, boxes, depth, mask and semantics | `scenet build --conditioning` | 0.12 |
| A PDF for print, with its trim, its bleed and lettering on the black plate | `scenet build --pdf`, `render_pdf()` | 0.13, not yet released |
| A monochrome edition of a tinted document | `scenet build --mono` | 0.13, not yet released |

## Tools

| Feature | Written as | Since |
|---|---|---|
| The Python API | `compile_source()` | 0.1 |
| JSON Schemas for panel and scene documents | `scenet schema` | 0.1 |
| The browser playground | | 0.1 |
| The VS Code extension | | 0.1 |
| `scenet check`, its findings as text or SARIF | `scenet check` | 0.3 |
| The checks that compile, `--deep` | `scenet check --deep` | 0.6 |
| The spec pack, `llms.txt` and the Agent Skill | | 0.8 |
| The MCP server | `scenet mcp` | 0.8 |
| A rebuild on every save | `scenet build --watch` | 0.13, not yet released |

## Roadmap

What is planned is in [the issues](https://github.com/creatoan/scenet/issues), each scoped to be
a release of its own, with what it depends on stated there. What Scenet will not do is said in
[Why Scenet](why.md): it draws no picture with a model, interprets no prose, and leaves style to
whoever performs the score.
