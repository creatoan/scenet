/**
 * The files beside the document: the Files tab.
 *
 * A document reads files by a path relative to itself -- a picture to letter over, its
 * artwork contract, a font -- and in the playground they sit in its folder in Pyodide's file
 * system, where nothing showed them. The gallery's are written there at start, and so is
 * whatever the author adds with Font… and Image…. This says what each is, so the tab can show
 * it: a contract as its text, a picture as itself, a font by its name.
 */

export type FileKind = "text" | "image" | "font" | "other";

const IMAGE_TYPES: Readonly<Record<string, string>> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
};

const TEXT = new Set(["yaml", "yml", "json", "txt"]);
const FONT = new Set(["ttf", "otf"]);

function extension(path: string): string {
  const name = path.split("/").pop() ?? "";
  const dot = name.lastIndexOf(".");
  return dot <= 0 ? "" : name.slice(dot + 1).toLowerCase();
}

/** The picture's media type, for a PNG or a JPEG. */
export function imageType(path: string): string | undefined {
  return IMAGE_TYPES[extension(path)];
}

export function fileKind(path: string): FileKind {
  const found = extension(path);
  if (TEXT.has(found)) return "text";
  if (imageType(path) !== undefined) return "image";
  if (FONT.has(found)) return "font";
  return "other";
}

/** A size as a person reads it: bytes, kilobytes or megabytes, in thousands. */
export function formatSize(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${(bytes / 1000).toFixed(1)} kB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

/** The files by path, compared code unit by code unit: the same order in every browser. */
export function listed<T extends { readonly path: string }>(files: readonly T[]): T[] {
  return [...files].sort((one, other) => (one.path < other.path ? -1 : one.path > other.path ? 1 : 0));
}
