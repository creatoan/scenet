/**
 * SARIF from `scenet check` to editor diagnostics.
 *
 * Most cases run over reports captured from the checker itself (`fixtures/*.sarif`,
 * kept current by `tests/test_editor_fixtures.py`); the rest are SARIF the checker does
 * not write today but the format allows, written inline.
 *
 * Positions are rendered 0-based, `line:character`, which is how VS Code counts.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { describe, test } from "node:test";

import { MalformedSarif, RULE_REFERENCE, sarifToDiagnostics, type DiagnosticSpec } from "../src/sarif";

const FIXTURES = join(__dirname, "fixtures");

function source(name: string): string {
  return join(FIXTURES, "sources", name);
}

function lineText(file: string, line: number): string | undefined {
  try {
    return readFileSync(file, "utf8").split(/\r?\n/)[line];
  } catch {
    return undefined;
  }
}

function captured(name: string): unknown {
  return JSON.parse(readFileSync(join(FIXTURES, `${name}.sarif`), "utf8"));
}

function map(log: unknown, checkedFile = source("unknown-actor.panel.yaml")): Map<string, DiagnosticSpec[]> {
  return sarifToDiagnostics(log, { cwd: FIXTURES, checkedFile, lineText });
}

function render(diagnostic: DiagnosticSpec): string {
  const { start, end } = diagnostic;
  return `${start.line}:${start.character}-${end.line}:${end.character} ${diagnostic.severity} ${diagnostic.rule ?? "-"}`;
}

/** Every diagnostic in a mapping, by file name, so a failure reads as the Problems list. */
function problems(mapped: Map<string, DiagnosticSpec[]>): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [file, diagnostics] of mapped) {
    out[file.slice(join(FIXTURES, "sources").length + 1)] = diagnostics.map(render);
  }
  return out;
}

/** A one-result log, for the cases the checker does not produce. */
function log(result: object, run: object = {}): object {
  return { version: "2.1.0", runs: [{ tool: { driver: { name: "test" } }, results: [result], ...run }] };
}

describe("captured from scenet check", () => {
  test("a YAML finding has a line and a column", () => {
    // SARIF says 4:15-4:18, 1-based; the editor counts from 0.
    assert.deepEqual(problems(map(captured("unknown-actor"))), {
      "unknown-actor.panel.yaml": ["3:14-3:17 error scenet/unknown-actor"],
    });
  });

  test("the message and the rule's reference travel with it", () => {
    const [diagnostic] = map(captured("unknown-actor")).get(source("unknown-actor.panel.yaml")) ?? [];
    assert.match(diagnostic?.message ?? "", /unknown actor 'bpb'/);
    assert.equal(diagnostic?.help, RULE_REFERENCE);
  });

  test("a comic-script finding is its whole line", () => {
    // Line 10 is `PANEL 1`, seven characters.
    assert.deepEqual(problems(map(captured("duplicate-panel"), source("duplicate-panel.script"))), {
      "duplicate-panel.script": ["9:0-9:7 error scenet/duplicate-panel"],
    });
  });

  test("a finding about the whole document starts where the document does", () => {
    assert.deepEqual(problems(map(captured("not-a-mapping"), source("not-a-mapping.panel.yaml"))), {
      "not-a-mapping.panel.yaml": ["1:0-3:0 error scenet/not-a-mapping"],
    });
  });

  test("several files are reported each under its own name", () => {
    assert.deepEqual(problems(map(captured("several-files"))), {
      "unknown-actor.panel.yaml": ["3:14-3:17 error scenet/unknown-actor"],
      "duplicate-panel.script": ["9:0-9:7 error scenet/duplicate-panel"],
      "syntax.panel.yaml": ["2:23-2:24 error scenet/syntax"],
    });
  });

  test("a column past an emoji counts UTF-16 code units, as the editor does", () => {
    // The checker counts code points; each emoji is one of those and two code units.
    const line = lineText(source("astral.panel.yaml"), 3) ?? "";
    const at = line.indexOf("bpb");
    assert.deepEqual(problems(map(captured("astral"), source("astral.panel.yaml"))), {
      "astral.panel.yaml": [`3:${at}-3:${at + 3} error scenet/unknown-actor`],
    });
  });

  test("a clean report has nothing to show", () => {
    assert.equal(map(captured("clean")).size, 0);
  });
});

describe("SARIF the checker does not write, but may", () => {
  const where = { artifactLocation: { uri: "sources/unknown-actor.panel.yaml" } };
  const firstLine = (lineText(source("unknown-actor.panel.yaml"), 0) ?? "").length;
  const secondLine = (lineText(source("unknown-actor.panel.yaml"), 1) ?? "").length;

  test("no region is the first line of the file", () => {
    const result = { ruleId: "r", level: "error", message: { text: "m" }, locations: [{ physicalLocation: where }] };
    assert.deepEqual(problems(map(log(result))), { "unknown-actor.panel.yaml": [`0:0-0:${firstLine} error r`] });
  });

  test("a start line alone is that whole line (SARIF 3.30.6-8)", () => {
    const result = {
      ruleId: "r",
      level: "error",
      message: { text: "m" },
      locations: [{ physicalLocation: { ...where, region: { startLine: 2 } } }],
    };
    assert.deepEqual(problems(map(log(result))), { "unknown-actor.panel.yaml": [`1:0-1:${secondLine} error r`] });
  });

  test("no location at all is the first line of the document checked", () => {
    const result = { ruleId: "r", level: "error", message: { text: "m" } };
    assert.deepEqual(problems(map(log(result), source("unknown-actor.panel.yaml"))), {
      "unknown-actor.panel.yaml": [`0:0-0:${firstLine} error r`],
    });
  });

  test("a file: uri is a path", () => {
    const uri = pathToFileURL(source("unknown-actor.panel.yaml")).href;
    const result = {
      ruleId: "r",
      level: "error",
      message: { text: "m" },
      locations: [{ physicalLocation: { artifactLocation: { uri }, region: { startLine: 1, startColumn: 3, endColumn: 4 } } }],
    };
    assert.deepEqual(problems(map(log(result))), { "unknown-actor.panel.yaml": ["0:2-0:3 error r"] });
  });

  test("columns already in UTF-16 code units are taken as they are", () => {
    const result = {
      ruleId: "r",
      level: "error",
      message: { text: "m" },
      locations: [
        {
          physicalLocation: {
            artifactLocation: { uri: "sources/astral.panel.yaml" },
            region: { startLine: 4, startColumn: 36, endColumn: 39 },
          },
        },
      ],
    };
    assert.deepEqual(problems(map(log(result, { columnKind: "utf16CodeUnits" }))), {
      "astral.panel.yaml": ["3:35-3:38 error r"],
    });
  });

  test("levels map to severities, and a missing level is SARIF's default, a warning", () => {
    const at = { locations: [{ physicalLocation: { ...where, region: { startLine: 1 } } }], message: { text: "m" } };
    const document = {
      version: "2.1.0",
      runs: [
        {
          tool: { driver: { name: "test", rules: [{ id: "strict", defaultConfiguration: { level: "error" } }] } },
          results: [
            { ruleId: "w", level: "warning", ...at },
            { ruleId: "n", level: "note", ...at },
            { ruleId: "none", level: "none", ...at },
            { ruleId: "unset", ...at },
            { ruleId: "strict", ruleIndex: 0, ...at },
          ],
        },
      ],
    };
    const severities = [...map(document).values()].flat().map((d) => `${d.rule} ${d.severity}`);
    assert.deepEqual(severities, [
      "w warning",
      "n information",
      "none information",
      "unset warning",
      "strict error",
    ]);
  });

  test("results from several runs are all kept", () => {
    const result = { ruleId: "r", level: "error", message: { text: "m" }, locations: [{ physicalLocation: where }] };
    const first = log(result) as { runs: object[] };
    const both = { version: "2.1.0", runs: [...first.runs, ...first.runs] };
    assert.equal(map(both).get(source("unknown-actor.panel.yaml"))?.length, 2);
  });

  test("something that is not a SARIF log is refused, not shown as nothing", () => {
    for (const bad of [null, "text", {}, { version: "2.1.0" }, { version: "2.1.0", runs: "x" }]) {
      assert.throws(() => map(bad), MalformedSarif);
    }
  });
});
