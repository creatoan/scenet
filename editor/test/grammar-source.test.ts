/**
 * The committed `.script` grammar is exactly what its source builds.
 *
 * `syntaxes/scenet-script.grammar.ts` writes each line shape once and composes the
 * grammar's rules, and the lookaheads that end a speech, from those shapes. VS Code reads
 * the JSON, so the JSON is committed; this keeps the two from drifting apart.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "node:test";

import { grammar, serialise } from "../syntaxes/scenet-script.grammar";

const COMMITTED = join(__dirname, "..", "syntaxes", "scenet-script.tmLanguage.json");

describe("the script grammar's source", () => {
  test("builds the committed grammar, byte for byte", () => {
    assert.equal(
      readFileSync(COMMITTED, "utf8"),
      serialise(grammar),
      "run `npm run grammar` in editor/ and commit the result",
    );
  });

  test("ends a speech at every line that interrupts a pending cue, and more", () => {
    // The first line under a cue is speech whatever it looks like, unless it is one of
    // the lines that end even that. A speech ends at those, at a directive and at the
    // next cue: the pending lookahead must be a prefix of the speech's.
    const speechEnd = grammar.repository.speech.end ?? "";
    const pendingEnd = grammar.repository.pending.end ?? "";
    const interrupts = pendingEnd.slice(0, pendingEnd.indexOf(")|^"));
    assert.ok(interrupts.length > 0);
    assert.ok(speechEnd.startsWith(interrupts), `${speechEnd}\ndoes not start with\n${interrupts}`);
  });
});
