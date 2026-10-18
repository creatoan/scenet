/**
 * A cached Pyodide wheel is reused only when it is the file the lockfile names.
 *
 * Pyodide's lockfile carries a sha256 per wheel, and the browser checks it as
 * subresource integrity. Reusing a cached file by name alone served a wheel from an
 * older Pyodide build under an unchanged filename, which the browser then refused.
 */

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, describe, test } from "node:test";

import { ensureWheel } from "./pyodide-wheels.ts";

const CURRENT = new TextEncoder().encode("the wheel this lockfile names");
const STALE = new TextEncoder().encode("a wheel from an older Pyodide build");
const DIGEST = createHash("sha256").update(CURRENT).digest("hex");
const WHEEL_URL = "https://cdn.example/pyodide/numpy.whl";

let root: string;

before(async () => {
  root = await mkdtemp(join(tmpdir(), "scenet-wheels-"));
});

after(async () => {
  await rm(root, { recursive: true, force: true });
});

/** A fetch that records what it was asked for and answers with `bytes`. */
function fetcher(bytes: Uint8Array): ((url: string) => Promise<Uint8Array>) & {
  calls: string[];
} {
  const calls: string[] = [];
  return Object.assign(
    async (url: string) => {
      calls.push(url);
      return bytes;
    },
    { calls },
  );
}

describe("ensureWheel", () => {
  test("keeps a cached wheel whose digest matches, without downloading", async () => {
    const target = join(root, "kept.whl");
    await writeFile(target, CURRENT);
    const fetch = fetcher(STALE);

    const result = await ensureWheel(target, WHEEL_URL, DIGEST, fetch);

    assert.deepEqual(fetch.calls, []);
    assert.deepEqual(result, { bytes: CURRENT.byteLength, fetched: false });
    assert.deepEqual(new Uint8Array(await readFile(target)), CURRENT);
  });

  test("replaces a cached wheel whose digest does not match", async () => {
    const target = join(root, "stale.whl");
    await writeFile(target, STALE);
    const fetch = fetcher(CURRENT);

    const result = await ensureWheel(target, WHEEL_URL, DIGEST, fetch);

    assert.deepEqual(fetch.calls, [WHEEL_URL]);
    assert.deepEqual(result, { bytes: CURRENT.byteLength, fetched: true });
    assert.deepEqual(new Uint8Array(await readFile(target)), CURRENT);
  });

  test("downloads a wheel that is not cached", async () => {
    const target = join(root, "missing.whl");
    const fetch = fetcher(CURRENT);

    await ensureWheel(target, WHEEL_URL, DIGEST, fetch);

    assert.deepEqual(fetch.calls, [WHEEL_URL]);
    assert.deepEqual(new Uint8Array(await readFile(target)), CURRENT);
  });

  test("refuses a download that is not the wheel the lockfile names", async () => {
    // The browser would refuse it anyway; failing the build says why, and where.
    const target = join(root, "tampered.whl");
    const fetch = fetcher(STALE);

    await assert.rejects(ensureWheel(target, WHEEL_URL, DIGEST, fetch), /sha256/);
    assert.equal(existsSync(target), false);
  });

  test("compares digests without regard to case", async () => {
    const target = join(root, "upper.whl");
    await writeFile(target, CURRENT);
    const fetch = fetcher(STALE);

    await ensureWheel(target, WHEEL_URL, DIGEST.toUpperCase(), fetch);

    assert.deepEqual(fetch.calls, []);
  });
});
