# Implementation status

| Document | Contents |
|---|---|
| [Language specification](../reference/language.md) | The DSL — every construct, with examples |
| [Panel Core](../reference/panel_core.md) | The resolved intermediate format |
| [Shot types](../reference/shot_types.md) | Normative camera framing table |
| [Asset contract](../reference/asset_contract.md) | What a character puppet must declare |

**This specification is free to implement.** The project is released under
[0BSD](https://github.com/creatoan/scenet/blob/main/LICENSE), which imposes no conditions whatsoever — but to be explicit: anyone may
build a competing compiler, editor, renderer or tool for this language without permission or
attribution. A notation is only worth having if it is not owned.

## Implementation status

| Phase | Scope | State |
|---|---|---|
| 0 | Toolchain, CI, specification, project scaffolding | **Done** |
| 1 | IR, Panel Core schema, YAML frontend, puppets and forward kinematics | **Done** |
| 2 | Camera scale resolution and actor placement (Cassowary) | **Done** |
| 3 | Text metrics, balloon placement, reading order, tails | **Done** |
| 4 | SVG emitter, debug overlay and CLI | **Done** |
| 5 | Comic-script frontend; multi-panel `over` inheritance | **Done** |
| 6 | Browser playground (Pyodide); VS Code extension | **Done** |
| 7 | Machine-readable diagnostics: `scenet check`, in SARIF | **Done** |
| 8 | Captions, faces, and the setting layer — places, masses, planes, atmosphere | **Done** |
| 9 | Emanata — plewds, squeans, grawlixes, briffits — as a soft placement cost | **Done** |
| 10 | The agent-facing surface: spec pack and `llms.txt`, Agent Skill, MCP server | **Done** |
| 11 | Pages: tiers of panels at varying sizes, columns, one type size per page, Page Core | **Done** |

Single panels compile end to end. Constructs described in `language.md` are the specification,
not a report of what is implemented — the table above is authoritative on what actually runs.

## Planned

Each of these is scoped to be a release on its own. The order is deliberately not fixed, and the
dependency between them is stated in the tickets rather than implied by this table.

| Scope | Ticket |
|---|---|
| Insets, frames that are not rectangles (columns are done) | [#67](https://github.com/creatoan/scenet/issues/67) |
| Right-to-left reading, for manga | [#68](https://github.com/creatoan/scenet/issues/68) |
| Supplied artwork: lettering over an image, in two parts | [#69](https://github.com/creatoan/scenet/issues/69) |
| Export a panel's staging for image models: pose, boxes, depth, masks | [#72](https://github.com/creatoan/scenet/issues/72) |
| Sound effects | [#73](https://github.com/creatoan/scenet/issues/73) |
| Lettering: emphasis, an author's lettering face, kerning, type size | [#74](https://github.com/creatoan/scenet/issues/74) |
| Comic scripts in publishers' formats, and in French | [#75](https://github.com/creatoan/scenet/issues/75) |
| Accessible output | [#76](https://github.com/creatoan/scenet/issues/76) |
| VS Code: `scenet check` findings, and highlighting for comic scripts | [#77](https://github.com/creatoan/scenet/issues/77) |
| `scenet build --watch` | [#78](https://github.com/creatoan/scenet/issues/78) |
| Print: a PDF emitter with trim, bleed and a black plate | [#80](https://github.com/creatoan/scenet/issues/80) |

Still further out, and not yet ticketed: the interpretation layer that would give a panel a
*style*.
