/**
 * Types for the two Monaco internals the tokenizer tests run.
 *
 * `monaco-editor` ships no declarations for these modules, because they are not its
 * public API. They are what the editor itself runs to tokenize a Monarch language, which
 * is why a test uses them rather than a reimplementation. `monaco-editor` is pinned to an
 * exact version in `package.json`, so a release that moves them fails the tests on the
 * upgrade, not silently.
 *
 * Only what the harness touches is declared.
 */

declare module "monaco-editor/esm/vs/editor/standalone/common/monarch/monarchCompile.js" {
  import type * as Monaco from "monaco-editor";

  /** The compiled lexer. Opaque: it is only ever handed to `MonarchTokenizer`. */
  export interface CompiledLexer {
    readonly languageId: string;
  }

  export function compile(languageId: string, json: Monaco.languages.IMonarchLanguage): CompiledLexer;
}

declare module "monaco-editor/esm/vs/editor/standalone/common/monarch/monarchLexer.js" {
  import type { CompiledLexer } from "monaco-editor/esm/vs/editor/standalone/common/monarch/monarchCompile.js";

  /** A tokenizer's state between lines. Opaque, passed from one line to the next. */
  export interface MonarchState {
    clone(): MonarchState;
  }

  export interface MonarchToken {
    readonly offset: number;
    readonly type: string;
    /** The language the token belongs to: the script's own, or an embedded one. */
    readonly language: string;
  }

  export interface LanguageService {
    readonly languageIdCodec: { encodeLanguageId(languageId: string): number };
    isRegisteredLanguageId(languageId: string): boolean;
    getLanguageIdByLanguageName(name: string): string | null;
    getLanguageIdByMimeType(mimeType: string): string | null;
    requestBasicLanguageFeatures(languageId: string): void;
  }

  export interface ThemeService {
    getColorTheme(): { readonly tokenTheme: { match(languageId: number, token: string): number } };
  }

  export interface ConfigurationService {
    getValue(key: string, overrides?: object): unknown;
    onDidChangeConfiguration(listener: () => void): { dispose(): void };
  }

  export class MonarchTokenizer {
    constructor(
      languageService: LanguageService,
      themeService: ThemeService,
      languageId: string,
      lexer: CompiledLexer,
      configurationService: ConfigurationService,
    );
    getInitialState(): MonarchState;
    tokenize(
      line: string,
      hasEOL: boolean,
      state: MonarchState,
    ): { readonly tokens: readonly MonarchToken[]; readonly endState: MonarchState };
    dispose(): void;
  }
}
