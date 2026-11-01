import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { parse } from "yaml";

import { findTryThis } from "./try-this.ts";

const DOCUMENT = [
  "cast: {a: {reference: alice}}",
  "script:",
  "  - say: {by: a, text: Hi.}",
  "",
  '# Try this: delete the "# " that starts the last line: `unknown-actor`.',
  "#   - say: {by: b, text: Hi.}",
  "",
].join("\n");

const SCRIPT = [
  "---",
  "cast:",
  "  A: {reference: alice}",
  "# Try this: delete the \"# \" that starts the next line: `unknown-puppet`.",
  "#   B: {reference: nell}",
  "---",
  "PANEL 1",
  "A",
  "Hi.",
  "",
].join("\n");

describe("a try-this", () => {
  it("is the last line of a document, under the comment that opens it", () => {
    assert.deepEqual(findTryThis(DOCUMENT, false), { comment: 5, line: 6 });
  });

  it("is found past blank lines at the end, and in a document written with CRLF", () => {
    assert.deepEqual(findTryThis(`${DOCUMENT}\n\n`, false), { comment: 5, line: 6 });
    assert.deepEqual(findTryThis(DOCUMENT.replaceAll("\n", "\r\n"), false), {
      comment: 5,
      line: 6,
    });
  });

  it("closes a comic script's front matter", () => {
    assert.deepEqual(findTryThis(SCRIPT, true), { comment: 4, line: 5 });
  });

  it("is not in a script with no front matter, nor in a script's prose", () => {
    assert.equal(findTryThis("PANEL 1\nA\nHi.\n", true), undefined);
    assert.equal(findTryThis("PANEL 1\n# Try this: x\n# A\n", true), undefined);
  });

  it("is a line commented out, under a comment that opens with Try this", () => {
    assert.equal(findTryThis(DOCUMENT.replace("#   - say", "  - say"), false), undefined);
    assert.equal(findTryThis(DOCUMENT.replace("# Try this:", "# Then:"), false), undefined);
    const apart = DOCUMENT.replace("`.\n#   - say", "`.\n\n#   - say");
    assert.equal(findTryThis(apart, false), undefined, "the comment is right over the line");
  });
});

describe("the gallery's try-these", () => {
  const gallery = new URL("../../examples/gallery/", import.meta.url);
  const manifest = parse(readFileSync(new URL("manifest.yaml", gallery), "utf8")) as {
    examples: { file: string; kind: string; group: string }[];
  };

  it("are found in every example that shows what Scenet tells you, and in no other", () => {
    for (const entry of manifest.examples) {
      const text = readFileSync(new URL(entry.file, gallery), "utf8");
      const found = findTryThis(text, entry.kind === "script");
      assert.equal(found !== undefined, entry.group === "What Scenet tells you", entry.file);
    }
  });
});
