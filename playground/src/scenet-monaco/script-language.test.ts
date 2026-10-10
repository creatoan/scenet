/**
 * The comic-script tokenizer, run by Monaco's own lexer.
 *
 * Monaco swallows an exception a Monarch rule throws and leaves the line uncoloured, so a
 * rule Monaco refuses fails silently in the playground. Through `monarch-harness.ts` it
 * fails here instead.
 *
 * The shared highlighting fixtures in `tests/script_highlighting/` are the main test.
 * The VS Code extension's TextMate grammar is tested against the same files
 * (`editor/test/grammar.test.ts`), and `tests/test_script_highlighting.py` holds them to
 * the compiler's own reading of each script, so the two tokenizers cannot drift apart,
 * nor away from the format.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { describe, test } from "node:test";

import { describeLine, tokenizeScript, type MonarchToken } from "./monarch-harness.ts";

const FIXTURES = new URL("../../../tests/script_highlighting/", import.meta.url);

/** Monarch token type, without the `.scenet` postfix, to fixture class. */
const CLASS_OF: Readonly<Record<string, string>> = {
  "meta.separator": "front-matter-delimiter",
  "keyword.page": "page-keyword",
  "string.page": "page-label",
  "keyword.panel": "panel-keyword",
  "number.panel": "panel-label",
  operator: "directive-marker",
  "attribute.name": "directive-name",
  "attribute.value": "directive-value",
  "type.identifier": "cue-name",
  annotation: "cue-parenthetical",
  "keyword.caption": "caption-keyword",
  "annotation.caption": "caption-kind",
  "string.caption": "caption-text",
  "string.dialogue": "dialogue",
  "comment.prose": "prose",
};

function classOf(token: MonarchToken): string | undefined {
  // Whatever the embedded YAML tokenizer makes of the front matter, it is front matter.
  if (token.language === "yaml") {
    return "front-matter";
  }
  return CLASS_OF[token.type.replace(/\.scenet$/, "")];
}

/**
 * A line's spans as `[class, text]`: neighbours of one class merged, the rest dropped,
 * each trimmed. Whitespace and punctuation are nobody's business but the theme's.
 */
function classify(line: string, tokens: readonly MonarchToken[]): [string, string][] {
  const merged: { kind: string | undefined; text: string }[] = [];
  tokens.forEach((token, index) => {
    const kind = classOf(token);
    const text = line.slice(token.offset, tokens[index + 1]?.offset ?? line.length);
    const last = merged.at(-1);
    if (last !== undefined && last.kind === kind) {
      last.text += text;
    } else {
      merged.push({ kind, text });
    }
  });
  return merged
    .filter((span): span is { kind: string; text: string } => span.kind !== undefined)
    .map((span): [string, string] => [span.kind, span.text.trim()])
    .filter(([, text]) => text !== "");
}

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

describe("the shared fixtures", () => {
  const names = readdirSync(FIXTURES)
    .filter((file) => file.endsWith(".script"))
    .map((file) => file.slice(0, -".script".length))
    .sort();

  for (const name of names) {
    test(name, () => {
      const text = readFileSync(new URL(`${name}.script`, FIXTURES), "utf8").replace(/\n$/, "");
      const lines = text.split(/\r?\n/);
      const expected = readFileSync(new URL(`${name}.tokens`, FIXTURES), "utf8")
        .split(/\r?\n/)
        .filter((row) => row !== "")
        .map((row) => JSON.parse(row) as [string, string][]);

      const tokens = tokenizeScript(text);
      const actual = lines.map((line, index) => classify(line, tokens[index] ?? []));
      // Line by line, numbered, so a failure says where.
      assert.deepEqual(
        actual.map((spans, index) => `${index + 1}: ${JSON.stringify(spans)}`),
        expected.map((spans, index) => `${index + 1}: ${JSON.stringify(spans)}`),
      );
    });
  }
});
