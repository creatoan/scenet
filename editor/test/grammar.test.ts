/**
 * The `.script` TextMate grammar, against the shared highlighting fixtures.
 *
 * The playground's Monarch tokenizer is tested against the same fixtures
 * (`playground/src/scenet-monaco/script-language.test.ts`), and
 * `tests/test_script_highlighting.py` holds the fixtures to the compiler's own reading
 * of each script. So the two tokenizers cannot drift apart, nor away from the format.
 *
 * The grammar runs in `vscode-textmate` with the Oniguruma build VS Code itself uses.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { before, describe, test } from "node:test";

import * as oniguruma from "vscode-oniguruma";
import * as textmate from "vscode-textmate";

const EDITOR = join(__dirname, "..");
const FIXTURES = join(EDITOR, "..", "tests", "script_highlighting");
const SCOPE = "source.scenet-script";

interface Manifest {
  readonly contributes: {
    readonly grammars?: readonly {
      readonly language: string;
      readonly scopeName: string;
      readonly path: string;
      readonly embeddedLanguages?: Readonly<Record<string, string>>;
    }[];
  };
}

const manifest = JSON.parse(readFileSync(join(EDITOR, "package.json"), "utf8")) as Manifest;
const contribution = manifest.contributes.grammars?.find((grammar) => grammar.language === "scenet-script");

/**
 * Scope to fixture class, innermost scope first. The `.scenet-script` suffix keeps a
 * scope from the embedded YAML grammar from ever matching one of these.
 */
const CLASS_OF: readonly (readonly [string, string])[] = [
  ["punctuation.separator.frontmatter.scenet-script", "front-matter-delimiter"],
  ["keyword.control.page.scenet-script", "page-keyword"],
  ["entity.name.section.page.scenet-script", "page-label"],
  ["keyword.control.panel.scenet-script", "panel-keyword"],
  ["entity.name.section.panel.scenet-script", "panel-label"],
  ["punctuation.definition.directive.scenet-script", "directive-marker"],
  ["entity.other.attribute-name.directive.scenet-script", "directive-name"],
  ["string.unquoted.directive.scenet-script", "directive-value"],
  ["entity.name.type.cue.scenet-script", "cue-name"],
  ["markup.italic.parenthetical.scenet-script", "cue-parenthetical"],
  ["keyword.other.caption.scenet-script", "caption-keyword"],
  ["markup.italic.caption-kind.scenet-script", "caption-kind"],
  ["string.unquoted.caption.scenet-script", "caption-text"],
  ["string.unquoted.dialogue.scenet-script", "dialogue"],
  ["comment.line.prose.scenet-script", "prose"],
  // Anything in the front matter that is not a delimiter, whichever YAML scope it has.
  ["meta.embedded.block.frontmatter", "front-matter"],
];

function classOf(scopes: readonly string[]): string | undefined {
  for (const scope of [...scopes].reverse()) {
    const found = CLASS_OF.find(([prefix]) => scope === prefix || scope.startsWith(`${prefix}.`));
    if (found !== undefined) {
      return found[1];
    }
  }
  return undefined;
}

/**
 * A line's spans as `[class, text]`: neighbours of one class merged, the rest dropped,
 * each trimmed. Whitespace and punctuation are nobody's business but the theme's.
 */
function classify(line: string, tokens: readonly textmate.IToken[]): [string, string][] {
  const merged: { kind: string | undefined; text: string }[] = [];
  for (const token of tokens) {
    const kind = classOf(token.scopes);
    const text = line.slice(token.startIndex, token.endIndex);
    const last = merged.at(-1);
    if (last !== undefined && last.kind === kind) {
      last.text += text;
    } else {
      merged.push({ kind, text });
    }
  }
  return merged
    .filter((span): span is { kind: string; text: string } => span.kind !== undefined)
    .map((span): [string, string] => [span.kind, span.text.trim()])
    .filter(([, text]) => text !== "");
}

let grammar: textmate.IGrammar;

before(async () => {
  const wasm = readFileSync(require.resolve("vscode-oniguruma/release/onig.wasm"));
  await oniguruma.loadWASM(wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength));
  const registry = new textmate.Registry({
    onigLib: Promise.resolve({
      createOnigScanner: (patterns) => new oniguruma.OnigScanner(patterns),
      createOnigString: (text) => new oniguruma.OnigString(text),
    }),
    // Only the script grammar. VS Code supplies `source.yaml` for the front matter;
    // here it resolves to nothing, and the front matter is one embedded block.
    loadGrammar: async (scopeName) => {
      if (scopeName !== SCOPE || contribution === undefined) {
        return null;
      }
      const path = join(EDITOR, contribution.path);
      return textmate.parseRawGrammar(readFileSync(path, "utf8"), path);
    },
  });
  const loaded = await registry.loadGrammar(SCOPE);
  if (loaded === null) {
    throw new Error(`no grammar for ${SCOPE}`);
  }
  grammar = loaded;
});

describe("the contribution", () => {
  test("gives .script files a grammar", () => {
    assert.equal(contribution?.scopeName, SCOPE);
  });

  test("hands the front matter to the YAML grammar", () => {
    assert.deepEqual(contribution?.embeddedLanguages, { "meta.embedded.block.frontmatter": "yaml" });
  });
});

describe("the shared fixtures", () => {
  const names = readdirSync(FIXTURES)
    .filter((file) => file.endsWith(".script"))
    .map((file) => file.slice(0, -".script".length))
    .sort();

  for (const name of names) {
    test(name, () => {
      const lines = readFileSync(join(FIXTURES, `${name}.script`), "utf8").split(/\r?\n/);
      if (lines.at(-1) === "") {
        lines.pop();
      }
      const expected = readFileSync(join(FIXTURES, `${name}.tokens`), "utf8")
        .split(/\r?\n/)
        .filter((row) => row !== "")
        .map((row) => JSON.parse(row) as [string, string][]);

      let stack = textmate.INITIAL;
      const actual = lines.map((line) => {
        const { tokens, ruleStack } = grammar.tokenizeLine(line, stack);
        stack = ruleStack;
        return classify(line, tokens);
      });
      // Line by line, numbered, so a failure says where.
      assert.deepEqual(
        actual.map((spans, index) => `${index + 1}: ${JSON.stringify(spans)}`),
        expected.map((spans, index) => `${index + 1}: ${JSON.stringify(spans)}`),
      );
    });
  }
});
