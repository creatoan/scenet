/**
 * Font files an author adds to the playground, to letter in their own face.
 *
 * The compiler reads a declared font relative to the folder the document is in, never
 * as a system lookup. The playground's document has no folder on disk, so it is given
 * one in Pyodide's in-memory file system, and a font added here is written into its
 * `fonts/` folder -- where `lettering: {font: fonts/Name.ttf}` finds it, exactly as it
 * would beside a file on disk.
 *
 * Fonts are not kept: they live in memory and are gone when the page reloads.
 */

/** The folder, relative to the document, that added fonts are written into. */
export const FONT_FOLDER = "fonts";

/**
 * The name an added font is written under, or `null` for a file that is not a font.
 *
 * Only the file's own name is kept -- never a folder a browser reported with it -- and
 * any character that a path or a YAML value would trip on becomes a hyphen. TrueType and
 * OpenType only: they are what the compiler measures.
 *
 * @param raw - The name the browser gave the file.
 */
export function fontFileName(raw: string): string | null {
  const base = raw.split(/[\\/]/).pop() ?? "";
  const [, name, extension] = /^(.+)\.(ttf|otf)$/i.exec(base) ?? [];
  if (name === undefined || extension === undefined) return null;
  const stem = name.replace(/[^A-Za-z0-9._-]/g, "-");
  if (stem.startsWith(".")) return null;
  return `${stem}.${extension}`;
}

/** What a document writes to letter in an added font. */
export function declaredPath(name: string): string {
  return `${FONT_FOLDER}/${name}`;
}
