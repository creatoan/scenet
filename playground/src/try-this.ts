/**
 * The "try this" line of a gallery example, and the link that uncomments it.
 *
 * Each example that shows what Scenet tells you ends with a line commented out that,
 * uncommented, makes it an error (#240). The convention is the gallery's, as
 * `tests/test_gallery.py` reads it: the last line of the document's YAML -- of a comic
 * script, its front matter, the only place a script can hold a comment -- written `# ` and
 * then exactly as it must read, under a comment that opens `# Try this:`.
 *
 * Uncommenting it by hand is easy to get wrong: deleting only the `#` leaves a space too
 * many, and a comic script has no comment for Ctrl+/ to toggle. So the editor puts a link
 * over the comment that deletes exactly the `# `, as one edit Ctrl+Z takes back.
 */

/** How the comment over the line opens. */
const OPENING = "# Try this:";

/** What a line to uncomment is written with in front of it. */
export const COMMENT_MARK = "# ";

/** Where a document's try-this is, one-based. */
export interface TryThis {
  /** The `# Try this:` line, which the link sits over. */
  readonly comment: number;
  /** The line to uncomment. */
  readonly line: number;
}

/**
 * The document's try-this, if it has one.
 *
 * @param text - The document.
 * @param script - Whether it is a comic script, whose try-this ends its front matter.
 */
export function findTryThis(text: string, script: boolean): TryThis | undefined {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const at = (index: number): string => lines[index] ?? "";
  let last: number;
  if (script) {
    if (at(0).trim() !== "---") return undefined;
    const closing = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
    if (closing === -1) return undefined;
    last = closing - 1;
  } else {
    last = lines.length - 1;
    while (last >= 0 && at(last).trim() === "") last -= 1;
  }
  if (last < 0 || !at(last).startsWith(COMMENT_MARK)) return undefined;
  // The comment over it, up to the nearest line that opens a try-this.
  for (let index = last - 1; index >= 0 && at(index).startsWith("#"); index -= 1) {
    if (at(index).startsWith(OPENING)) return { comment: index + 1, line: last + 1 };
  }
  return undefined;
}
