/**
 * Which kind a document is, guessed from its text.
 *
 * In a module of its own, importing nothing, so it can be tested without a browser.
 */

/** Which of the three document kinds a source string is. */
export type ScenetDocumentKind = "panel" | "scene" | "script";

/** A comic script's front matter: YAML between two `---` fences, at the top. */
const FRONT_MATTER = /^\s*---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/;

/**
 * A panel heading as the compiler reads one: `PANEL 1` alone, or Dark Horse's `Panel 1.
 * A corner.`, in any case, after Markdown's `##` or inside its `**`.
 */
const PANEL_HEADING = new RegExp(
  String.raw`^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*|__)?panel[ \t]+(?:[^\s:]+?[ \t]*[.:]?[ \t]*(?:\*\*|__)?[ \t]*$|[^\s.:—–-]+[ \t]*(?:[.:—–]|[ \t]-)[ \t]*\S)`,
  "imu",
);

/** A key a YAML panel or scene has at its left margin, which no script line starts with. */
const YAML_KEY = /^(?:panel|panels|camera|cast|staging|script|setting|lettering|page|pages|over)[ \t]*:/m;

/**
 * Guess a document's kind from its text.
 *
 * The compiler dispatches on the file extension, which a browser editor does not have.
 * A script has front matter fenced by `---` at the top, or a panel heading, and no YAML key
 * at the left margin; a scene has `panels:`. Anything else is a single panel, which is also
 * the right answer for an empty buffer.
 *
 * It used to take any document whose first line was `---` for a script -- a YAML panel may
 * open with that document marker -- and to see only `PANEL 1` in capitals, alone on its
 * line, so a script written as Dark Horse asks, `Panel 1.`, was read as YAML.
 */
export function detectKind(source: string): ScenetDocumentKind {
  const body = source.replace(FRONT_MATTER, "");
  const fenced = body !== source;
  if (!YAML_KEY.test(body) && (fenced || PANEL_HEADING.test(body))) {
    return "script";
  }
  if (/^panels\s*:/m.test(source)) {
    return "scene";
  }
  return "panel";
}
