/**
 * Monaco language definition for Scenet comic scripts.
 *
 * Comic script is a format writers already use, and its structure is carried entirely
 * by line shape: a heading is a word and a number, a speaker cue is a name in capitals
 * on its own line, a directive starts with `@`, and everything else is prose. A Monarch
 * tokenizer -- which is a state machine over regular expressions, line by line -- fits
 * that exactly, and needs no parser.
 *
 * The one rule worth stating twice, because it is the one that trips people up: a
 * speaker cue is recognised by **the name** being in capitals, not the whole line.
 * `BOB (whisper)` is a cue; the parenthetical is lower case and does not disqualify it.
 * The compiler's own frontend makes the same distinction, and got it wrong first.
 */

import type * as Monaco from "monaco-editor";

export const SCRIPT_LANGUAGE_ID = "scenet-script";

/**
 * Bracket pairs, comment syntax and auto-closing behaviour.
 *
 * Comic script has no comment syntax of its own, so none is declared -- offering one
 * would invite people to write comments the compiler then treats as prose.
 */
export const scriptLanguageConfiguration: Monaco.languages.LanguageConfiguration = {
  brackets: [
    ["(", ")"],
    ["[", "]"],
    ["{", "}"],
  ],
  autoClosingPairs: [
    { open: "(", close: ")" },
    { open: "[", close: "]" },
    { open: "{", close: "}" },
    { open: '"', close: '"' },
  ],
  surroundingPairs: [
    { open: "(", close: ")" },
    { open: '"', close: '"' },
  ],
  wordPattern: /[A-Za-z_][\w-]*/,
};

// The line shapes, each the frontend's own pattern (`scenet/frontends/script_front.py`)
// with the leading whitespace it strips made explicit. With groups, Monaco requires every
// character of a match to be in one and refuses the rule otherwise -- silently, leaving
// the line uncoloured -- so whitespace and punctuation are grouped too.
//
// Headings are case-insensitive, as the frontend's are, spelled out letter by letter
// because a cue has to stay case-sensitive in the same tokenizer.
/** A word in any case, spelled letter by letter: a cue in the same tokenizer is not. */
const anyCase = (word: string): string =>
  [...word].map((letter) => `[${letter.toUpperCase()}${letter.toLowerCase()}]`).join("");
const oneOf = (words: readonly string[]): string => words.map(anyCase).join("|");

const UNITS = [
  "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
  "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
  "nineteen",
];
const ONE_TO_NINE = UNITS.slice(1, 10);
const TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

/** A page number in words, `ONE` to `NINETY-NINE`, however they are joined. */
const NUMBER_PHRASE = String.raw`(?:(?:${oneOf(TENS)})(?:[ \t-]+(?:${oneOf(ONE_TO_NINE)}))?|${oneOf(UNITS)})`;
/**
 * A label a panel heading with a description on its line may have: digits, digits and a
 * letter, one letter, or a number in a word -- so `Panel shows Alice.` stays prose.
 */
const NUMBER_LIKE = String.raw`(?:\d+\p{L}?|(?:${oneOf(TENS)}|${oneOf(UNITS)})(?!\p{L})|\p{L}(?!\p{L}))`;
/** A page's label: a number in words, `TWENTY ONE`, or one token, `3A`. */
const PAGE_LABEL = String.raw`${NUMBER_PHRASE}(?=\s*(?:\(|[.:*_]|$))|[^\s:()]+?`;
/** Markdown a writer may put around a heading: `## ` before it, `**` around it. */
const MARKDOWN_OPEN = String.raw`(?:#{1,6}[ \t]+)?(?:\*\*|__)?`;
const MARKDOWN_CLOSE = String.raw`(?:\*\*|__)?`;

const unicode = (pattern: string): RegExp => new RegExp(pattern, "u");

// A Markdown horizontal rule, `---` or `* * *`, which the frontend reads as a blank line.
const RULE = /^(\s*)(-(?:[ \t]*-){2,}|\*(?:[ \t]*\*){2,}|_(?:[ \t]*_){2,})(\s*)$/;
// Dark Horse's `PAGE ONE (five panels)`, and a page with no count.
const PAGE_WITH_COUNT = unicode(
  String.raw`^(\s*)(${MARKDOWN_OPEN})(${anyCase("page")})(\s+)(${PAGE_LABEL})(\s*\()([^)]*)(\)\s*[.:]?\s*)(${MARKDOWN_CLOSE})(\s*)$`,
);
const PAGE = unicode(
  String.raw`^(\s*)(${MARKDOWN_OPEN})(${anyCase("page")})(\s+)(${PAGE_LABEL})(\s*[.:]?\s*)(${MARKDOWN_CLOSE})(\s*)$`,
);
// `PANEL 1` alone, and Dark Horse's `Panel 1. Alice and Bob on a corner.`
const PANEL = unicode(
  String.raw`^(\s*)(${MARKDOWN_OPEN})(${anyCase("panel")})(\s+)([^\s:]+?)(\s*[.:]?\s*)(${MARKDOWN_CLOSE})(\s*)$`,
);
const PANEL_DESCRIBED = unicode(
  String.raw`^(\s*)(${MARKDOWN_OPEN})(${anyCase("panel")})(\s+)(${NUMBER_LIKE})(\s*(?:[.:—–]|\s-)\s*)(\S.*)$`,
);
const DIRECTIVE = /^(\s*)(@)(\w+)(\s*:\s*)(.+)$/;
const CAPTION_WITH_KIND = /^(\s*)([Cc][Aa][Pp][Tt][Ii][Oo][Nn])(\s*\()([^)]*)(\)\s*:\s*)(.+)$/;
const CAPTION = /^(\s*)([Cc][Aa][Pp][Tt][Ii][Oo][Nn])(\s*:\s*)(.+)$/;
// A sound effect, with its sound on the line -- `SFX: BLAM`, `SFX (BOB, large): KRAK` --
// or Dark Horse's bare `SFX:` cue, the sound on the next line.
const SFX_WITH_PARENTHETICAL = /^(\s*)([Ss][Ff][Xx])(\s*\()([^)]*)(\)\s*:\s*)(.+)$/;
const SFX = /^(\s*)([Ss][Ff][Xx])(\s*:\s*)(.+)$/;
const SFX_CUE_WITH_PARENTHETICAL = /^(\s*)([Ss][Ff][Xx])(\s*\()([^)]*)(\)\s*:?\s*)$/;
const SFX_CUE = /^(\s*)([Ss][Ff][Xx])(\s*:?\s*)$/;
// A cue is a name in capitals, then an optional parenthetical and colon, on a line of at
// most forty characters once trimmed -- longer, and it is a shouted description. Any
// capital letter counts, `HÉLÈNE`'s as well as `ALICE`'s, and so does a combining accent:
// the compiler composes `E` and `◌́` into `É` before it reads a line, and an editor on
// macOS may well have stored them apart. With the `u` flag (`unicode` below), `.` is a
// code point, so forty characters are counted as Python counts them.
const CUE_NAME = String.raw`\p{Lu}[\p{Lu}\p{M}\p{Nd} _'.\-]*?`;
const CUE_WITH_PARENTHETICAL = new RegExp(
  String.raw`^(\s*)(?=\S(?:.{0,38}\S)?\s*$)(${CUE_NAME})(\s*\()([^)]*)(\)\s*:?\s*)$`,
  "u",
);
const CUE = new RegExp(String.raw`^(\s*)(?=\S(?:.{0,38}\S)?\s*$)(${CUE_NAME})(\s*:?\s*)$`, "u");

type Rule = Monaco.languages.IMonarchLanguageRule;

// A state change rides on a group that always matches something: Monaco skips the
// action of a group that matched nothing, state change and all, so `ALICE` with no
// colon would never start a speech if the change were on the colon's group.

/** Headings, captions and sound effects, which end whatever came before them. */
const STRUCTURE: Rule[] = [
  [RULE, ["", { token: "keyword.markdown", switchTo: "@root" }, ""]],
  [
    PAGE_WITH_COUNT,
    [
      "",
      "keyword.markdown",
      { token: "keyword.page", switchTo: "@root" },
      "",
      "string.page",
      "delimiter",
      "annotation.page-count",
      "delimiter",
      "keyword.markdown",
      "",
    ],
  ],
  [
    PAGE,
    ["", "keyword.markdown", { token: "keyword.page", switchTo: "@root" }, "", "string.page", "delimiter", "keyword.markdown", ""],
  ],
  [
    PANEL,
    ["", "keyword.markdown", { token: "keyword.panel", switchTo: "@root" }, "", "number.panel", "delimiter", "keyword.markdown", ""],
  ],
  [
    PANEL_DESCRIBED,
    ["", "keyword.markdown", { token: "keyword.panel", switchTo: "@root" }, "", "number.panel", "delimiter", "comment.prose"],
  ],
  [
    CAPTION_WITH_KIND,
    ["", { token: "keyword.caption", switchTo: "@root" }, "delimiter", "annotation.caption", "delimiter", "string.caption"],
  ],
  [CAPTION, ["", { token: "keyword.caption", switchTo: "@root" }, "delimiter", "string.caption"]],
  [
    SFX_WITH_PARENTHETICAL,
    ["", { token: "keyword.sfx", switchTo: "@root" }, "delimiter", "annotation.sfx", "delimiter", "string.sfx"],
  ],
  [SFX, ["", { token: "keyword.sfx", switchTo: "@root" }, "delimiter", "string.sfx"]],
  [
    SFX_CUE_WITH_PARENTHETICAL,
    ["", { token: "keyword.sfx", switchTo: "@sound" }, "delimiter", "annotation.sfx", "delimiter"],
  ],
  [SFX_CUE, ["", { token: "keyword.sfx", switchTo: "@sound" }, "delimiter"]],
];

/** A directive, and the state it leaves the tokenizer in. */
function directive(state: string): Rule {
  return [DIRECTIVE, ["", { token: "operator", switchTo: state }, "attribute.name", "delimiter", "attribute.value"]];
}

/** A cue, which makes the next line speech. */
const CUES: Rule[] = [
  [
    CUE_WITH_PARENTHETICAL,
    ["", { token: "type.identifier", switchTo: "@speech" }, "delimiter", "annotation", "delimiter"],
  ],
  [CUE, ["", { token: "type.identifier", switchTo: "@speech" }, "delimiter"]],
];

/**
 * The tokenizer, a state machine over the same line shapes as the frontend's own loop
 * (`_Reader`), so that what is coloured as dialogue is what compiles as dialogue:
 *
 * - `preamble` — blank lines before anything else. Front matter can only open here; a
 *   `---` further down is prose, as writers use it for a scene divider.
 * - `frontMatter` — between the fences, handed to the YAML tokenizer.
 * - `root` — the body: headings, directives, captions, cues and prose.
 * - `speech` — the line after a cue, which is speech whatever it looks like, so `OK.`
 *   is spoken, not a character called OK. A directive leaves the cue waiting.
 * - `dialogue` — the lines of a speech after its first, until a blank line, a heading, a
 *   caption, a sound effect, a directive or the next cue.
 * - `sound` — the line after a bare `SFX:` cue, which is the sound whatever it looks like:
 *   `BLAM` is in capitals too.
 *
 * Every transition is a `switchTo`, never a push, so the stack does not grow with the
 * length of the script.
 */
export const scriptMonarchTokens: Monaco.languages.IMonarchLanguage = {
  defaultToken: "",
  tokenPostfix: ".scenet",
  start: "preamble",
  // Every rule is compiled with the `u` flag, which `\p{Lu}` in a cue needs.
  unicode: true,

  tokenizer: {
    preamble: [
      [/^\s*$/, ""],
      [/^\s*---[ \t]*$/, { token: "meta.separator", switchTo: "@frontMatter", nextEmbedded: "yaml" }],
      [/^/, { token: "@rematch", switchTo: "@root" }],
    ],

    frontMatter: [[/^---[ \t]*$/, { token: "meta.separator", switchTo: "@root", nextEmbedded: "@pop" }]],

    root: [
      ...STRUCTURE,
      directive("@root"),
      ...CUES,
      [/^\s*$/, ""],
      // Everything else is prose. Preserved by the compiler, interpreted by nothing.
      [/.+$/, "comment.prose"],
    ],

    speech: [
      [/^\s*$/, { token: "", switchTo: "@root" }],
      ...STRUCTURE,
      directive("@speech"),
      [/.+$/, { token: "string.dialogue", switchTo: "@dialogue" }],
    ],

    sound: [
      [/^\s*$/, { token: "", switchTo: "@root" }],
      [/^(\s*)(.+)$/, ["", { token: "string.sfx", switchTo: "@root" }]],
    ],

    dialogue: [
      [/^\s*$/, { token: "", switchTo: "@root" }],
      ...STRUCTURE,
      directive("@root"),
      ...CUES,
      [/.+$/, "string.dialogue"],
    ],
  },
};

/**
 * Colours for the token classes above.
 *
 * Defined as a theme rather than left to Monaco's defaults because the default palette
 * has no opinion about `comment.prose` or `string.dialogue`, and those two are the ones
 * that matter: a writer scanning a script wants dialogue to stand out from description
 * at a glance.
 */
export const scriptThemeRules: Monaco.editor.ITokenThemeRule[] = [
  { token: "keyword.panel", fontStyle: "bold" },
  { token: "keyword.page", fontStyle: "bold" },
  { token: "type.identifier.scenet", fontStyle: "bold" },
  { token: "annotation.scenet", fontStyle: "italic" },
  { token: "keyword.caption", fontStyle: "bold" },
  { token: "annotation.caption.scenet", fontStyle: "italic" },
  { token: "keyword.sfx", fontStyle: "bold" },
  { token: "annotation.sfx.scenet", fontStyle: "italic" },
  { token: "comment.prose.scenet", fontStyle: "italic" },
];
