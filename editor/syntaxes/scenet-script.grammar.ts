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

/** `PAGE ONE`, `Panel 1.`: a heading keyword and its label. */
function heading(keyword: string): Shape {
  return {
    capture: raw`((?i:${keyword}))[ \t]+([^\s:]+?)[ \t]*([.:]?)[ \t]*$`,
    test: raw`(?i:${keyword})[ \t]+[^\s:]+?[ \t]*[.:]?[ \t]*$`,
  };
}

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
/** A name in capitals: only the name is tested, not the parenthetical. */
const CUE_NAME = raw`[A-Z][A-Z0-9 _'.\-]*?`;

const SHAPES = {
  page: heading("page"),
  panel: heading("panel"),
  anyHeading: heading("page|panel"),
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
const INTERRUPTS: readonly Shape[] = [SHAPES.anyHeading, SHAPES.caption, SHAPES.sfxLine, SHAPES.sfxCue];

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
        { include: "#page" },
        { include: "#panel" },
        { include: "#directive" },
        { include: "#caption" },
        { include: "#sfx" },
        { include: "#speech" },
        { include: "#prose" },
      ],
    },
    page: {
      match: line(SHAPES.page.capture),
      captures: captures("keyword.control.page", "entity.name.section.page", "punctuation.separator"),
    },
    panel: {
      match: line(SHAPES.panel.capture),
      captures: captures("keyword.control.panel", "entity.name.section.panel", "punctuation.separator"),
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
