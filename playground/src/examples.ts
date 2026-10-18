/**
 * The files a gallery example names beside itself, as the build inlines them.
 *
 * An example lettered over a picture names it by a path relative to the document --
 * `art/street.png` -- and the compiler reads it from the document's folder in Pyodide's
 * file system. So the build puts each such file into `examples.json` as base64, and the
 * page writes them all into that folder once, at start: a draft restored from an example,
 * or a link shared from one, then finds its picture too.
 */

/** A file to write beside the document: where, and what is in it. */
export interface DocumentFile {
  readonly path: string;
  readonly bytes: Uint8Array;
}

/**
 * Whether a path stays inside the document's folder: relative, `/`-separated, and never
 * climbing out with `..`. Anything else is not written -- `examples.json` is the build's
 * own output, but a path that escaped would write over the page's own files.
 */
export function staysInside(path: string): boolean {
  if (path === "" || path.startsWith("/") || path.includes("\\") || /^[A-Za-z]:/.test(path)) {
    return false;
  }
  return path.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}

/** Decode the base64 an example's files are inlined as. */
export function decodeBase64(text: string): Uint8Array {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

/** Every file the examples name, decoded, in a fixed order, each path once. */
export function exampleFiles(
  examples: readonly { readonly files?: Readonly<Record<string, string>> }[],
): DocumentFile[] {
  const seen = new Map<string, Uint8Array>();
  for (const example of examples) {
    for (const [path, text] of Object.entries(example.files ?? {})) {
      if (staysInside(path) && !seen.has(path)) seen.set(path, decodeBase64(text));
    }
  }
  return [...seen.entries()]
    .sort(([one], [other]) => (one < other ? -1 : one > other ? 1 : 0))
    .map(([path, bytes]) => ({ path, bytes }));
}
