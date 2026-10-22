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
| 11 | Pages: tiers of panels at varying sizes, columns, insets, slanted tiers, one type size per page, Page Core | **Done** |
| 12 | Lettering: emphasis, kerning, type size, an author's own face; sound effects in the display face | **Done** |
| 13 | Comic scripts as publishers write them, and in French; off-panel speech; small type; a script's pages; notes in `scenet check` | **Done** |
| 14 | Accessible output: every panel an image a screen reader reads whole, in reading order; descriptions written, kept from a script or generated | **Done** |
| 15 | Supplied artwork: a picture behind the cast, linked or embedded; figures the picture draws, declared in an artwork contract and lettered around | **Done** |
| 16 | Right-to-left reading, for manga: panels, pages, strips and lettering read from the top right, the scene never mirrored | **Done** |

Single panels compile end to end. Constructs described in `language.md` are the specification,
not a report of what is implemented — the table above is authoritative on what actually runs.

## Planned

Each of these is scoped to be a release on its own. The order is deliberately not fixed, and the
dependency between them is stated in the tickets rather than implied by this table.

| Scope | Ticket |
|---|---|
| Export a panel's staging for image models: pose, boxes, depth, masks | [#72](https://github.com/creatoan/scenet/issues/72) |
| VS Code: `scenet check` findings, and highlighting for comic scripts | [#77](https://github.com/creatoan/scenet/issues/77) |
| `scenet build --watch` | [#78](https://github.com/creatoan/scenet/issues/78) |
| Print: a PDF emitter with trim, bleed and a black plate | [#80](https://github.com/creatoan/scenet/issues/80) |

Still further out, and not yet ticketed: the interpretation layer that would give a panel a
*style*.
