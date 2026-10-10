/**
 * Run the comic-script Monarch tokenizer in Node, with Monaco's own lexer.
 *
 * A test that reimplemented Monarch would test the reimplementation. These are the modules
 * the editor runs, given the three services the lexer asks for as stubs: none of them can
 * change a token's type, which is all the tests look at. See `monaco-internals.d.ts` for
 * why importing them is acceptable.
 *
 * Monaco catches an exception the tokenizer throws and leaves the line uncoloured, logging
 * nothing a user sees. Here it propagates, which is the point.
 */

import { compile } from "monaco-editor/esm/vs/editor/standalone/common/monarch/monarchCompile.js";
import {
  MonarchTokenizer,
  type MonarchToken,
} from "monaco-editor/esm/vs/editor/standalone/common/monarch/monarchLexer.js";

import { SCRIPT_LANGUAGE_ID, scriptMonarchTokens } from "./script-language.ts";

export type { MonarchToken };

/** Tokenize a script, one list of tokens per line, carrying state between lines. */
export function tokenizeScript(text: string): MonarchToken[][] {
  const tokenizer = new MonarchTokenizer(
    {
      languageIdCodec: { encodeLanguageId: () => 0 },
      // Nothing is registered, so embedded front matter is tokenized as a single token
      // in the `yaml` language: enough to see where it starts and stops.
      isRegisteredLanguageId: () => false,
      getLanguageIdByLanguageName: (name) => name,
      getLanguageIdByMimeType: () => null,
      requestBasicLanguageFeatures: () => undefined,
    },
    { getColorTheme: () => ({ tokenTheme: { match: () => 0 } }) },
    SCRIPT_LANGUAGE_ID,
    compile(SCRIPT_LANGUAGE_ID, scriptMonarchTokens),
    {
      getValue: () => 20_000,
      onDidChangeConfiguration: () => ({ dispose: () => undefined }),
    },
  );
  try {
    let state = tokenizer.getInitialState();
    return text.split(/\r?\n/).map((line) => {
      const { tokens, endState } = tokenizer.tokenize(line, true, state);
      state = endState;
      return [...tokens];
    });
  } finally {
    tokenizer.dispose();
  }
}

/**
 * A line as `type:text` spans, so a failure reads as the script does.
 *
 * Empty spans are dropped: Monarch emits one for a group it was told to leave unstyled
 * that happened to match nothing, and it carries no meaning.
 */
export function describeLine(line: string, tokens: readonly MonarchToken[]): string[] {
  return tokens
    .map((token, index) => {
      const end = tokens[index + 1]?.offset ?? line.length;
      return { type: token.type, text: line.slice(token.offset, end) };
    })
    .filter((span) => span.text.length > 0)
    .map((span) => `${span.type}:${span.text}`);
}
