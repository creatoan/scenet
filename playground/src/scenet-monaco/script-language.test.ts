/**
 * The comic-script tokenizer, run by Monaco's own lexer.
 *
 * Monaco swallows an exception a Monarch rule throws and leaves the line uncoloured, so a
 * rule Monaco refuses fails silently in the playground. Through `monarch-harness.ts` it
 * fails here instead.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";

import { describeLine, tokenizeScript } from "./monarch-harness.ts";

/** Each line of a script as `type:text` spans. */
function spans(...lines: string[]): string[][] {
  const tokens = tokenizeScript(lines.join("\n"));
  return lines.map((line, index) => describeLine(line, tokens[index] ?? []));
}

describe("scriptMonarchTokens", () => {
  test("the gallery's comic script tokenizes", () => {
    const script = readFileSync(new URL("../../../examples/umbrella.script", import.meta.url), "utf8");
    assert.doesNotThrow(() => tokenizeScript(script));
  });

  test("a page heading is a keyword and its label", () => {
    // Monaco refused the rule: its groups did not cover the space between them.
    assert.deepEqual(spans("PAGE ONE"), [["keyword.page.scenet:PAGE", "string.page.scenet:ONE"]]);
  });

  test("a panel heading is a keyword and its number", () => {
    assert.deepEqual(spans("PANEL 1"), [
      ["keyword.panel.scenet:PANEL", "number.panel.scenet:1"],
    ]);
  });

  test("a cue with a parenthetical colours each part, and starts dialogue", () => {
    // Monaco refused the rule: it named five actions for four groups.
    assert.deepEqual(spans("BOB (whisper)", "I left it on purpose."), [
      [
        "type.identifier.scenet:BOB",
        "delimiter.scenet: (",
        "annotation.scenet:whisper",
        "delimiter.scenet:)",
      ],
      ["string.dialogue.scenet:I left it on purpose."],
    ]);
  });

  test("a bare cue starts dialogue, and a blank line ends it", () => {
    assert.deepEqual(spans("ALICE", "You forgot your umbrella!", "", "Rain."), [
      ["type.identifier.scenet:ALICE"],
      ["string.dialogue.scenet:You forgot your umbrella!"],
      [],
      ["comment.prose.scenet:Rain."],
    ]);
  });
});
