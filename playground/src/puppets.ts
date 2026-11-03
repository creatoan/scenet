/**
 * Puppets an author adds to the playground, to cast as characters of their own (#242).
 *
 * A cast member names a puppet file by its path, relative to the folder the document is in,
 * as a document names a font or a picture: `reference: puppets/Name.puppet.yaml`. The
 * playground's document has its folder in Pyodide's in-memory file system, so a puppet added
 * here is written into its `puppets/` folder -- where that reference finds it, exactly as it
 * would beside a file on disk. The gallery's own puppet is written there too.
 *
 * Puppets are not kept: they live in memory and are gone when the page reloads.
 */

/** What a puppet file's name ends in, as a reference names one. */
export const PUPPET_SUFFIX = ".puppet.yaml";

/** The folder, relative to the document, that added puppets are written into. */
export const PUPPET_FOLDER = "puppets";

/**
 * The name an added puppet is written under, or `null` for a file that is not a puppet.
 *
 * Only the file's own name is kept -- never a folder a browser reported with it -- and any
 * character that a path, a link or a YAML value would trip on becomes a hyphen. The suffix is
 * kept in lower case, since that is what the compiler tells a puppet file by.
 *
 * @param raw - The name the browser gave the file.
 */
export function puppetFileName(raw: string): string | null {
  const base = raw.split(/[\\/]/).pop() ?? "";
  const [, name] = /^(.+)\.puppet\.yaml$/i.exec(base) ?? [];
  if (name === undefined) return null;
  const stem = name.replace(/[^A-Za-z0-9._-]/g, "-");
  if (stem.startsWith(".")) return null;
  return `${stem}${PUPPET_SUFFIX}`;
}

/** What a cast member's `reference` writes to be drawn by an added puppet. */
export function declaredPuppetPath(name: string): string {
  return `${PUPPET_FOLDER}/${name}`;
}
