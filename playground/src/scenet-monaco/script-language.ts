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
const PAGE = /^(\s*)([Pp][Aa][Gg][Ee])(\s+)([^\s:]+?)(\s*[.:]?\s*)$/;
const PANEL = /^(\s*)([Pp][Aa][Nn][Ee][Ll])(\s+)([^\s:]+?)(\s*[.:]?\s*)$/;
const DIRECTIVE = /^(\s*)(@)(\w+)(\s*:\s*)(.+)$/;
const CAPTION_WITH_KIND = /^(\s*)([Cc][Aa][Pp][Tt][Ii][Oo][Nn])(\s*\()([^)]*)(\)\s*:\s*)(.+)$/;
const CAPTION = /^(\s*)([Cc][Aa][Pp][Tt][Ii][Oo][Nn])(\s*:\s*)(.+)$/;
// A cue is a name in capitals, then an optional parenthetical and colon, on a line of at
// most forty characters once trimmed -- longer, and it is a shouted description.
const CUE_WITH_PARENTHETICAL =
  /^(\s*)(?=\S(?:.{0,38}\S)?\s*$)([A-Z][A-Z0-9 _'.-]*?)(\s*\()([^)]*)(\)\s*:?\s*)$/;
const CUE = /^(\s*)(?=\S(?:.{0,38}\S)?\s*$)([A-Z][A-Z0-9 _'.-]*?)(\s*:?\s*)$/;

type Rule = Monaco.languages.IMonarchLanguageRule;

// A state change rides on a group that always matches something: Monaco skips the
// action of a group that matched nothing, state change and all, so `ALICE` with no
// colon would never start a speech if the change were on the colon's group.

/** Headings and captions, which end whatever came before them. */
const STRUCTURE: Rule[] = [
  [PAGE, ["", { token: "keyword.page", switchTo: "@root" }, "", "string.page", "delimiter"]],
  [PANEL, ["", { token: "keyword.panel", switchTo: "@root" }, "", "number.panel", "delimiter"]],
  [
    CAPTION_WITH_KIND,
    ["", { token: "keyword.caption", switchTo: "@root" }, "delimiter", "annotation.caption", "delimiter", "string.caption"],
  ],
  [CAPTION, ["", { token: "keyword.caption", switchTo: "@root" }, "delimiter", "string.caption"]],
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
 * (`_read_panels`), so that what is coloured as dialogue is what compiles as dialogue:
 *
 * - `preamble` — blank lines before anything else. Front matter can only open here; a
 *   `---` further down is prose, as writers use it for a scene divider.
 * - `frontMatter` — between the fences, handed to the YAML tokenizer.
 * - `root` — the body: headings, directives, captions, cues and prose.
 * - `speech` — the line after a cue, which is speech whatever it looks like, so `OK.`
 *   is spoken, not a character called OK. A directive leaves the cue waiting.
 * - `dialogue` — the lines of a speech after its first, until a blank line, a heading, a
 *   caption, a directive or the next cue.
 *
 * Every transition is a `switchTo`, never a push, so the stack does not grow with the
 * length of the script.
 */
export const scriptMonarchTokens: Monaco.languages.IMonarchLanguage = {
  defaultToken: "",
  tokenPostfix: ".scenet",
  start: "preamble",

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
  { token: "comment.prose.scenet", fontStyle: "italic" },
];
