/**
 * Pictures an author adds to the playground, to letter over.
 *
 * A document names a supplied picture relative to the folder it is in, as it names a
 * font. The playground's document has its folder in Pyodide's in-memory file system, so
 * a picture added here is written into its `art/` folder -- where
 * `setting: {image: art/Name.png}` finds it, exactly as it would beside a file on disk.
 * The compiler reads its size from its header; the preview and the downloads embed it.
 *
 * A picture whose people the author casts with `figure:` has an artwork contract beside it,
 * named after it -- `art/Name.art.yaml` for `art/Name.png` -- which is added the same way,
 * through the same control. Both names go through the same cleaning, so a picture and its
 * contract still pair up however the browser named them.
 *
 * Pictures are not kept: they live in memory and are gone when the page reloads.
 */

/** What an artwork contract's name ends in, as the compiler looks for it. */
export const CONTRACT_SUFFIX = ".art.yaml";

/** The folder, relative to the document, that added pictures are written into. */
export const IMAGE_FOLDER = "art";

/**
 * The name an added picture or contract is written under, or `null` for a file that is
 * neither.
 *
 * Only the file's own name is kept -- never a folder a browser reported with it -- and
 * any character that a path, a link or a YAML value would trip on becomes a hyphen. PNG
 * and JPEG only: they are what the compiler reads, and what every SVG renderer draws. A
 * contract keeps its suffix in lower case, since that is the name the compiler looks for.
 *
 * @param raw - The name the browser gave the file.
 */
export function imageFileName(raw: string): string | null {
  const base = raw.split(/[\\/]/).pop() ?? "";
  const [, name, extension] = /^(.+)\.(png|jpe?g|art\.yaml)$/i.exec(base) ?? [];
  if (name === undefined || extension === undefined) return null;
  const stem = name.replace(/[^A-Za-z0-9._-]/g, "-");
  if (stem.startsWith(".")) return null;
  const suffix = isContract(`.${extension}`) ? CONTRACT_SUFFIX : `.${extension}`;
  return `${stem}${suffix}`;
}

/** Whether a name is an artwork contract's, rather than a picture's. */
export function isContract(name: string): boolean {
  return name.toLowerCase().endsWith(CONTRACT_SUFFIX);
}

/** What a document writes to be lettered over an added picture. */
export function declaredImagePath(name: string): string {
  return `${IMAGE_FOLDER}/${name}`;
}
