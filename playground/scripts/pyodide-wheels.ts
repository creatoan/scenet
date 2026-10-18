/**
 * Bringing a Pyodide wheel in `public/pyodide/` to the one the lockfile names.
 *
 * `pyodide-lock.json` carries a sha256 for every wheel, and Pyodide passes it to the
 * browser as subresource integrity, so a wheel that differs from it is refused at load.
 * A cached wheel is therefore reused only when its digest matches, never by filename
 * alone: a Pyodide release can rebuild a wheel without renaming it, and a stale copy
 * left from an earlier build would otherwise be served and blocked. A download is held
 * to the same digest, so a wrong file fails the build rather than the page.
 */

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";

/** Whatever fetches a URL's bytes: `fetch` at build time, a stub under test. */
export type FetchBytes = (url: string) => Promise<Uint8Array>;

function digestOf(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

/**
 * Make `target` the wheel whose sha256 is `sha256`, downloading it from `url` unless a
 * matching copy is already there. Returns its size and whether it was downloaded.
 */
export async function ensureWheel(
  target: string,
  url: string,
  sha256: string,
  fetchBytes: FetchBytes,
): Promise<{ bytes: number; fetched: boolean }> {
  const expected = sha256.toLowerCase();
  if (existsSync(target)) {
    const cached = await readFile(target);
    if (digestOf(cached) === expected) {
      return { bytes: cached.byteLength, fetched: false };
    }
  }
  const bytes = await fetchBytes(url);
  const actual = digestOf(bytes);
  if (actual !== expected) {
    throw new Error(`${url}: sha256 ${actual}, but pyodide-lock.json says ${expected}`);
  }
  await writeFile(target, bytes);
  return { bytes: bytes.byteLength, fetched: true };
}
