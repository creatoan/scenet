import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { CompileNote, Finding } from "./compiler.ts";
import { noteRows } from "./notes.ts";

function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    rule: "word-limit",
    message: "this balloon holds 31 words; Dark Horse asks for about 25",
    line: 12,
    column: 21,
    endLine: 12,
    endColumn: 80,
    level: "note",
    ...overrides,
  };
}

const bent: CompileNote = {
  panel: null,
  rule: "curved-tail",
  message: "balloon b0 needed a curved tail to clear a face",
};

describe("the notes under the picture", () => {
  it("list what the checker notes first, each at its line, then what the compiler does", () => {
    assert.deepEqual(noteRows([finding()], [bent]), [
      {
        where: "12:21",
        rule: "word-limit",
        message: "this balloon holds 31 words; Dark Horse asks for about 25",
        at: { line: 12, column: 21 },
      },
      { where: "", rule: "curved-tail", message: "balloon b0 needed a curved tail to clear a face" },
    ]);
  });

  it("keep the checker's notes in the order it gives them, which is the source's", () => {
    const rows = noteRows([finding({ line: 3 }), finding({ line: 9, rule: "dropped-relation" })], []);
    assert.deepEqual(
      rows.map((row) => row.where),
      ["3:21", "9:21"],
    );
  });

  it("name the panel a compile note is about, in a document of several", () => {
    const [row] = noteRows([], [{ ...bent, panel: "street" }]);
    assert.equal(row?.where, "street");
    assert.equal(row?.at, undefined);
  });

  it("leave out an error, which is not a note", () => {
    assert.deepEqual(noteRows([finding({ level: "error", rule: "unknown-actor" })], []), []);
  });

  it("are none when nothing is said", () => {
    assert.deepEqual(noteRows([], []), []);
  });
});
