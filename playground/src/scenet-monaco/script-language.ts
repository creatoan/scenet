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
// A cue is a name in capitals, then any parentheticals and a colon, on a line of at most
// forty characters once trimmed -- longer, and it is a shouted description. Any capital
// letter counts, `HÉLÈNE`'s as well as `ALICE`'s, and so does a combining accent: the
// compiler composes `E` and `◌́` into `É` before it reads a line, and an editor on macOS may
// well have stored them apart. With the `u` flag (`unicode` below), `.` is a code point, so
// forty characters are counted as Python counts them.
const CUE_NAME = String.raw`\p{Lu}[\p{Lu}\p{M}\p{Nd} _'.\-]*?`;
const SHORT_LINE = String.raw`(?=\S(?:.{0,38}\S)?\s*$)`;

type Rule = Monaco.languages.IMonarchLanguageRule;
type Action = string | Monaco.languages.IExpandedMonarchLanguageAction;

/**
 * One group of a rule: its pattern, which holds no group of its own, and its token.
 *
 * Every group of a Monarch rule has to take part in every match -- Monaco reads the length
 * of each, and one that did not match is `undefined` -- so a part that may be absent is
 * written as two rules, one with it and one without, rather than an optional group.
 */
interface Part {
  readonly pattern: string;
  readonly action: Action;
}

const part = (pattern: string, action: Action): Part => ({ pattern, action });

/** A whole-line rule from its parts, in order. */
function rule(parts: readonly Part[]): Rule {
  return [
    unicode(`^${parts.map((each) => `(${each.pattern})`).join("")}$`),
    parts.map((each) => each.action),
  ];
}

/** Every combination of the parts that may be left out, as one rule each. */
function variants(...choices: readonly (readonly Part[])[][]): Part[][] {
  return choices.reduce<Part[][]>(
    (made, options) => made.flatMap((before) => options.map((option) => [...before, ...option])),
    [[]],
  );
}

const LEAD = part(String.raw`\s*`, "");
// Blambot's numbered lettering items, `1.` or `2)` before a label.
const NUMBERED = part(String.raw`(?:\d+[.)]?[ \t]+)?`, "number.balloon");
// Markdown bold around a label, `**ALICE:**`.
const BOLD = part(String.raw`(?:\*\*|__)?`, "keyword.markdown");
// Any number of parentheticals, `(OP) (whisper)` or `(OP, whisper)`.
const parentheticals = (token: string): Part[] => [
  part(String.raw`\s*\(`, "delimiter"),
  part(String.raw`[^)]*(?:\)\s*\([^)]*)*`, token),
  part(String.raw`\)`, "delimiter"),
];
const withOrWithout = (parts: Part[]): Part[][] => [parts, []];

// `CAP: Later.`, `CAPTION (monologue)` with its text under it, Dark Horse's `CAP/ALICE`.
const CAPTION_WORD = String.raw`(?:${anyCase("caption")}|${anyCase("cap")})(?![\p{L}\p{N}_])`;
const CAPTION_SPEAKER = [
  part(String.raw`\s*\/\s*`, "delimiter"),
  part(String.raw`[^():\/\s](?:[^():\/]*[^():\/\s])?`, "type.caption-speaker"),
];
const CAPTIONS: Rule[] = [true, false].flatMap((inline) =>
  variants(withOrWithout(CAPTION_SPEAKER), withOrWithout(parentheticals("annotation.caption"))).map(
    (optional) =>
      rule([
        LEAD,
        NUMBERED,
        BOLD,
        part(CAPTION_WORD, { token: "keyword.caption", switchTo: inline ? "@root" : "@captionFirst" }),
        ...optional,
        ...(inline
          ? [part(String.raw`\s*:`, "delimiter"), BOLD, part(String.raw`\s*`, ""), part(String.raw`\S.*`, "string.caption")]
          : [part(String.raw`\s*:?`, "delimiter"), BOLD, part(String.raw`\s*`, "")]),
      ]),
  ),
);

// A sound effect, with its sound on the line -- `SFX: BLAM`, `SFX (BOB, large): KRAK` --
// or Dark Horse's bare `SFX:` cue, the sound on the next line.
const SOUNDS: Rule[] = [true, false].flatMap((inline) =>
  variants(withOrWithout(parentheticals("annotation.sfx"))).map((optional) =>
    rule([
      LEAD,
      NUMBERED,
      part(anyCase("sfx"), { token: "keyword.sfx", switchTo: inline ? "@root" : "@sound" }),
      ...optional,
      ...(inline
        ? [part(String.raw`\s*:\s*`, "delimiter"), part(String.raw`.+`, "string.sfx")]
        : [part(String.raw`\s*:?\s*`, "delimiter")]),
    ]),
  ),
);

// `ALICE: Hello.`: a cue with its line after the colon, and the lines it wraps onto. The
// tokenizer cannot see the cast, so every `NAME: text` in capitals is one here; the compiler
// reads one whose name is not in the cast as prose, and notes it.
const INLINE_CUES: Rule[] = variants(withOrWithout(parentheticals("annotation"))).map((optional) =>
  rule([
    LEAD,
    NUMBERED,
    BOLD,
    part(CUE_NAME, { token: "type.identifier", switchTo: "@dialogue" }),
    ...optional,
    part(String.raw`\s*:`, "delimiter"),
    BOLD,
    part(String.raw`\s*`, ""),
    part(String.raw`\S.*`, "string.dialogue"),
  ]),
);

// A state change rides on a group that always matches something: Monaco skips the
// action of a group that matched nothing, state change and all, so `ALICE` with no
// colon would never start a speech if the change were on the colon's group.

/**
 * Headings, captions, sound effects and cues with their line on theirs, which end
 * whatever came before them, even a cue waiting for its line.
 */
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
  ...CAPTIONS,
  ...SOUNDS,
  ...INLINE_CUES,
];

/** A directive, and the state it leaves the tokenizer in. */
function directive(state: string): Rule {
  return [DIRECTIVE, ["", { token: "operator", switchTo: state }, "attribute.name", "delimiter", "attribute.value"]];
}

/** A cue, which makes the next line speech. */
const CUES: Rule[] = variants(withOrWithout(parentheticals("annotation"))).map((optional) =>
  rule([
    LEAD,
    NUMBERED,
    part(`${SHORT_LINE}${CUE_NAME}`, { token: "type.identifier", switchTo: "@speech" }),
    ...optional,
    part(String.raw`\s*:?\s*`, "delimiter"),
  ]),
);

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
 * - `captionFirst`, `captionMore` — the lines under a caption label, `CAP:` or Dark Horse's
 *   `CAP/ALICE`: the first is its text whatever it looks like, and the text runs on to a
 *   blank line, as a speech does.
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

    captionFirst: [
      [/^\s*$/, { token: "", switchTo: "@root" }],
      ...STRUCTURE,
      directive("@captionFirst"),
      [/.+$/, { token: "string.caption", switchTo: "@captionMore" }],
    ],

    captionMore: [
      [/^\s*$/, { token: "", switchTo: "@root" }],
      ...STRUCTURE,
      directive("@root"),
      ...CUES,
      [/.+$/, "string.caption"],
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
