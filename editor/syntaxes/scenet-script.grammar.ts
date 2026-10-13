/**
 * The comic-script TextMate grammar, built from named line shapes.
 *
 * Each kind of line the script frontend (`src/scenet/frontends/script_front.py`) tells
 * apart is written here once, in two forms: one that captures its parts for colouring,
 * and one that only recognises it, for the lookaheads that end a speech. A line that ends
 * a speech has to be spelled out again inside those lookaheads, and hand-written copies
 * drifted; composing them from one definition cannot.
 *
 * `npm run grammar` writes `scenet-script.tmLanguage.json` from this module, and
 * `test/grammar-source.test.ts` fails when the committed file is not what it builds.
 * Every pattern is the frontend's, with the leading whitespace it strips made explicit.
 */

const raw = String.raw;

/** What a TextMate rule looks like, as far as this grammar uses one. */
interface Rule {
  readonly comment?: string;
  readonly name?: string;
  readonly contentName?: string;
  readonly match?: string;
  readonly begin?: string;
  readonly end?: string;
  readonly captures?: Captures;
  readonly beginCaptures?: Captures;
  readonly endCaptures?: Captures;
  readonly patterns?: readonly Rule[];
  readonly include?: string;
}

type Captures = Readonly<Record<string, { readonly name: string }>>;

/** A line shape: the pattern that captures its parts, and the one that only tests for it. */
interface Shape {
  readonly capture: string;
  readonly test: string;
}

/** Scope names all end in the grammar's own suffix, so no embedded scope can match one. */
const scope = (name: string): { readonly name: string } => ({ name: `${name}.scenet-script` });

/** Numbered captures, from scope names (without the suffix) in group order. */
function captures(...names: readonly string[]): Captures {
  return Object.fromEntries(names.map((name, index) => [String(index + 1), scope(name)]));
}

/** An optional parenthetical, `(whisper)`, as three groups: open, contents, close. */
const PARENTHETICAL = { capture: raw`(?:(\()([^)]*)(\)))?`, test: raw`(?:\([^)]*\))?` } as const;

/**
 * Markdown a writer may put around a heading, `## ` before it or `**` around it. The
 * frontend strips it and reads the heading; the markers are coloured as what they are.
 */
const MARKDOWN = {
  open: raw`((?:#{1,6}[ \t]+)?(?:\*\*|__)?)`,
  openTest: raw`(?:#{1,6}[ \t]+)?(?:\*\*|__)?`,
  close: raw`((?:\*\*|__)?)`,
  closeTest: raw`(?:\*\*|__)?`,
} as const;

const UNITS = "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen";
const ONE_TO_NINE = "one|two|three|four|five|six|seven|eight|nine";
const TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety";

/** A page number in words, `ONE` to `NINETY-NINE`, however they are joined. */
const NUMBER_PHRASE = raw`(?i:(?:${TENS})(?:[ \t-]+(?:${ONE_TO_NINE}))?|${UNITS})`;

/**
 * A label a panel heading with a description on its line may have: digits, digits and a
 * letter, one letter, or a number in a word -- so `Panel shows Alice.` stays prose.
 */
const NUMBER_LIKE = raw`(?:\d+\p{L}?|(?i:${TENS}|${UNITS})(?!\p{L})|\p{L}(?!\p{L}))`;

/**
 * Dark Horse's `PAGE ONE (five panels)`. A label of several words is a number in words,
 * `PAGE TWENTY ONE`; the parenthetical states the count, or is a note.
 */
const PAGE: Shape = {
  capture: raw`${MARKDOWN.open}((?i:page))[ \t]+(${NUMBER_PHRASE}(?=[ \t]*(?:\(|[.:*_]|$))|[^\s:()]+?)[ \t]*${PARENTHETICAL.capture}[ \t]*([.:]?)[ \t]*${MARKDOWN.close}[ \t]*$`,
  test: raw`${MARKDOWN.openTest}(?i:page)[ \t]+(?:${NUMBER_PHRASE}(?=[ \t]*(?:\(|[.:*_]|$))|[^\s:()]+?)[ \t]*${PARENTHETICAL.test}[ \t]*[.:]?[ \t]*${MARKDOWN.closeTest}[ \t]*$`,
};

/** `PANEL 1`, `Panel One:`: a panel heading alone on its line. */
const PANEL: Shape = {
  capture: raw`${MARKDOWN.open}((?i:panel))[ \t]+([^\s:]+?)[ \t]*([.:]?)[ \t]*${MARKDOWN.close}[ \t]*$`,
  test: raw`${MARKDOWN.openTest}(?i:panel)[ \t]+[^\s:]+?[ \t]*[.:]?[ \t]*${MARKDOWN.closeTest}[ \t]*$`,
};

/** Dark Horse's `Panel 1. Alice and Bob on a corner.`, the description on the same line. */
const PANEL_DESCRIBED: Shape = {
  capture: raw`${MARKDOWN.open}((?i:panel))[ \t]+(${NUMBER_LIKE})[ \t]*([.:—–]|[ \t]-)[ \t]*(\S.*)$`,
  test: raw`${MARKDOWN.openTest}(?i:panel)[ \t]+${NUMBER_LIKE}[ \t]*(?:[.:—–]|[ \t]-)[ \t]*\S`,
};

/** A Markdown horizontal rule, `---` or `* * *`, which the frontend reads as a blank line. */
const RULE: Shape = {
  capture: raw`(-(?:[ \t]*-){2,}|\*(?:[ \t]*\*){2,}|_(?:[ \t]*_){2,})[ \t]*$`,
  test: raw`(?:-(?:[ \t]*-){2,}|\*(?:[ \t]*\*){2,}|_(?:[ \t]*_){2,})[ \t]*$`,
};

/** `CAPTION (monologue): text`, `SFX: BLAM`: a label with its text on the same line. */
function labelWithText(keyword: string): Shape {
  return {
    capture: raw`((?i:${keyword}))[ \t]*${PARENTHETICAL.capture}[ \t]*(:)[ \t]*(.+)$`,
    test: raw`(?i:${keyword})[ \t]*${PARENTHETICAL.test}[ \t]*:[ \t]*\S`,
  };
}

/** Dark Horse's `SFX:` on a line of its own, the text on the next. */
function labelAlone(keyword: string): Shape {
  return {
    capture: raw`((?i:${keyword}))[ \t]*${PARENTHETICAL.capture}[ \t]*(:?)[ \t]*$`,
    test: raw`(?i:${keyword})[ \t]*${PARENTHETICAL.test}[ \t]*:?[ \t]*$`,
  };
}

/** The frontend's forty-character limit on a cue, once trimmed. */
const SHORT_LINE = raw`(?=\S(?:.{0,38}\S)?[ \t]*$)`;
/**
 * A name in capitals: only the name is tested, not the parenthetical. Any capital letter
 * counts, `HÉLÈNE`'s as well as `ALICE`'s, and so does a combining accent, since the
 * compiler composes `E` and `◌́` into `É` before it reads a line.
 */
const CUE_NAME = raw`\p{Lu}[\p{Lu}\p{M}\p{Nd} _'.\-]*?`;

const SHAPES = {
  rule: RULE,
  page: PAGE,
  panel: PANEL,
  panelDescribed: PANEL_DESCRIBED,
  directive: { capture: raw`(@)(\w+)[ \t]*(:)[ \t]*(.+)$`, test: raw`@\w+[ \t]*:[ \t]*\S` },
  caption: labelWithText("caption"),
  sfxLine: labelWithText("sfx"),
  sfxCue: labelAlone("sfx"),
  cue: {
    capture: raw`${SHORT_LINE}(${CUE_NAME})[ \t]*${PARENTHETICAL.capture}[ \t]*(:?)[ \t]*$`,
    test: raw`${SHORT_LINE}${CUE_NAME}[ \t]*${PARENTHETICAL.test}[ \t]*:?[ \t]*$`,
  },
} as const satisfies Record<string, Shape>;

/** The frontend strips a line before reading it. */
const LEAD = raw`[ \t]*`;
const BLANK = raw`[ \t]*$`;

/**
 * Lines that end a speech even before its first line: the first line under a cue is
 * speech whatever it looks like, except these.
 */
const INTERRUPTS: readonly Shape[] = [
  SHAPES.rule,
  SHAPES.page,
  SHAPES.panel,
  SHAPES.panelDescribed,
  SHAPES.caption,
  SHAPES.sfxLine,
  SHAPES.sfxCue,
];

/** A speech also ends at a directive and at the next cue, once its first line is read. */
const ENDS_A_SPEECH: readonly Shape[] = [...INTERRUPTS, SHAPES.directive, SHAPES.cue];

/** `^(?=` one of `lines`, after leading whitespace, or a blank line `)`. */
function startOfAnyOf(lines: readonly Shape[]): string {
  return `^(?=${[BLANK, ...lines.map((line) => LEAD + line.test)].join("|")})`;
}

/** A whole line, `^` and the whitespace the frontend strips included. */
const line = (pattern: string): string => `^${LEAD}${pattern}`;

const PARENTHETICAL_SCOPES = (kind: string): readonly string[] => [
  `punctuation.definition.${kind}.begin`,
  `markup.italic.${kind}`,
  `punctuation.definition.${kind}.end`,
];

export const grammar = {
  $schema: "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
  name: "Scenet comic script",
  scopeName: "source.scenet-script",
  comment:
    "Generated from scenet-script.grammar.ts by `npm run grammar`: edit that, not this. Follows the script frontend (src/scenet/frontends/script_front.py) line for line, as the playground's Monarch tokenizer does. Both are tested against tests/script_highlighting/, which tests/test_script_highlighting.py holds to the frontend. Each pattern is the frontend's, with the leading whitespace it strips made explicit.",
  patterns: [{ include: "#preamble" }, { include: "#body" }],
  repository: {
    preamble: {
      comment:
        "Blank lines before anything else, where front matter may open. Begins only on a first line that is blank or a fence, and ends at the first other non-blank line, so a later --- is prose.",
      begin: raw`\A(?=[ \t]*(?:---[ \t]*)?$)`,
      end: raw`^(?=[ \t]*\S)(?![ \t]*---[ \t]*$)`,
      patterns: [{ include: "#front-matter" }],
    },
    "front-matter": {
      name: "meta.frontmatter.scenet-script",
      contentName: "meta.embedded.block.frontmatter",
      begin: raw`^[ \t]*(---)[ \t]*$`,
      beginCaptures: captures("punctuation.separator.frontmatter"),
      end: raw`^(---)[ \t]*$`,
      endCaptures: captures("punctuation.separator.frontmatter"),
      patterns: [{ include: "source.yaml" }],
    },
    body: {
      patterns: [
        { include: "#rule" },
        { include: "#page" },
        { include: "#panel" },
        { include: "#directive" },
        { include: "#caption" },
        { include: "#sfx" },
        { include: "#speech" },
        { include: "#prose" },
      ],
    },
    rule: {
      comment: "A Markdown horizontal rule, which the frontend reads as the blank line it looks like.",
      match: line(SHAPES.rule.capture),
      captures: captures("punctuation.definition.markdown"),
    },
    page: {
      match: line(SHAPES.page.capture),
      captures: captures(
        "punctuation.definition.markdown",
        "keyword.control.page",
        "entity.name.section.page",
        "punctuation.definition.page-count.begin",
        "markup.italic.page-count",
        "punctuation.definition.page-count.end",
        "punctuation.separator",
        "punctuation.definition.markdown",
      ),
    },
    panel: {
      comment: "`PANEL 1` alone, or Dark Horse's `Panel 1. Alice and Bob on a corner.`",
      patterns: [
        {
          match: line(SHAPES.panel.capture),
          captures: captures(
            "punctuation.definition.markdown",
            "keyword.control.panel",
            "entity.name.section.panel",
            "punctuation.separator",
            "punctuation.definition.markdown",
          ),
        },
        {
          match: line(SHAPES.panelDescribed.capture),
          captures: captures(
            "punctuation.definition.markdown",
            "keyword.control.panel",
            "entity.name.section.panel",
            "punctuation.separator",
            "comment.line.prose",
          ),
        },
      ],
    },
    directive: {
      match: line(SHAPES.directive.capture),
      captures: captures(
        "punctuation.definition.directive",
        "entity.other.attribute-name.directive",
        "punctuation.separator.key-value",
        "string.unquoted.directive",
      ),
    },
    caption: {
      match: line(SHAPES.caption.capture),
      captures: captures(
        "keyword.other.caption",
        ...PARENTHETICAL_SCOPES("caption-kind"),
        "punctuation.separator",
        "string.unquoted.caption",
      ),
    },
    sfx: {
      comment:
        "A sound effect: `SFX: BLAM`, `SFX (BOB, large): KRAK`, or Dark Horse's bare `SFX:` cue with the sound on the next line. Checked before cues, as the compiler checks it: `SFX` is a perfectly good name in capitals.",
      patterns: [{ include: "#sfx-line" }, { include: "#sfx-cue" }],
    },
    "sfx-line": {
      match: line(SHAPES.sfxLine.capture),
      captures: captures(
        "keyword.other.sfx",
        ...PARENTHETICAL_SCOPES("sfx-parenthetical"),
        "punctuation.separator",
        "string.unquoted.sfx",
      ),
    },
    "sfx-cue": {
      comment: "The next line is the sound, whatever it looks like: `BLAM` is in capitals too.",
      name: "meta.sfx.scenet-script",
      begin: line(SHAPES.sfxCue.capture),
      beginCaptures: captures(
        "keyword.other.sfx",
        ...PARENTHETICAL_SCOPES("sfx-parenthetical"),
        "punctuation.separator",
      ),
      end: raw`^(?=[ \t]*$)|^[ \t]*(\S.*)$`,
      endCaptures: captures("string.unquoted.sfx"),
    },
    speech: {
      comment:
        "A cue -- a name in capitals, an optional parenthetical and colon, at most forty characters once trimmed -- and the speech under it. The speech ends at a blank line, a heading, a caption, a directive or the next cue. Its first line is handled by #pending.",
      name: "meta.speech.scenet-script",
      begin: line(SHAPES.cue.capture),
      beginCaptures: captures(
        "entity.name.type.cue",
        ...PARENTHETICAL_SCOPES("parenthetical"),
        "punctuation.separator",
      ),
      end: startOfAnyOf(ENDS_A_SPEECH),
      patterns: [
        { include: "#pending" },
        { match: raw`^[ \t]*(\S.*)$`, captures: captures("string.unquoted.dialogue") },
      ],
    },
    pending: {
      comment:
        "From the end of the cue line to the end of the first line of speech. While it is open, the speech's end is not tested, so the first line is speech whatever it looks like: `OK.` is spoken, not a cue. A directive leaves the cue waiting.",
      begin: raw`\G`,
      end: `${startOfAnyOf(INTERRUPTS)}|^${LEAD}(?!${SHAPES.directive.test})(\\S.*)$`,
      endCaptures: captures("string.unquoted.dialogue"),
      patterns: [{ include: "#directive" }],
    },
    prose: {
      comment: "Everything else. Preserved by the compiler, interpreted by nothing.",
      match: raw`^[ \t]*(\S.*)$`,
      captures: captures("comment.line.prose"),
    },
  },
} as const satisfies Rule & {
  readonly $schema: string;
  readonly scopeName: string;
  readonly repository: Readonly<Record<string, Rule>>;
};

/** The grammar as the committed file holds it. */
export function serialise(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}
