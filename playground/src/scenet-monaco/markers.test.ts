/**
 * Findings to editor markers.
 *
 * A note reports a house limit -- a balloon over Dark Horse's twenty-five words -- not a
 * fault, and the panel still compiles. Underlining it in red, as an error, would say the
 * opposite.
 */

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import type * as Monaco from "monaco-editor";

import { toMarkers, type ScenetFinding } from "./markers.ts";

/** The two severities used, with Monaco's own values. */
const monaco = { MarkerSeverity: { Error: 8, Info: 2 } } as unknown as typeof Monaco;

function finding(level: ScenetFinding["level"]): ScenetFinding {
  return { rule: "scenet/word-limit", message: "long", line: 3, column: 5, endLine: 3, endColumn: 9, level };
}

describe("toMarkers", () => {
  test("an error is an error", () => {
    assert.equal(toMarkers(monaco, [finding("error")])[0]?.severity, 8);
  });

  test("a note is information", () => {
    assert.equal(toMarkers(monaco, [finding("note")])[0]?.severity, 2);
  });

  test("a finding is where it says, at least one character wide", () => {
    const [marker] = toMarkers(monaco, [{ ...finding("error"), endColumn: 5 }]);
    assert.deepEqual(
      [marker?.startLineNumber, marker?.startColumn, marker?.endLineNumber, marker?.endColumn],
      [3, 5, 3, 6],
    );
  });
});
