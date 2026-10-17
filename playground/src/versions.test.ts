/**
 * Which version a playground is, and the way to the others.
 *
 * Every version of the site carries a playground -- the latest release's at the root,
 * main's under /dev/, each minor version's under /vX.Y/ -- and nothing in one says which
 * it is but its address. The version switcher's data, the switcher.json every version of
 * the documentation reads, names the address of each; the playground is `playground/`
 * under it. That file is fetched, so it is treated as untrusted.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";

import { decodeSource } from "./persist.ts";
import {
  SWITCHER_URL,
  banner,
  currentVersion,
  parseVersions,
  playgroundUrl,
  type Version,
} from "./versions.ts";

const SWITCHER: Version[] = [
  { name: "dev", version: "dev", url: "/scenet/dev/" },
  { name: "0.11 (latest)", version: "0.11", url: "/scenet/", preferred: true },
  { name: "0.10", version: "0.10", url: "/scenet/v0.10/" },
];

describe("parseVersions", () => {
  test("reads the switcher's entries", () => {
    assert.deepEqual(parseVersions(JSON.parse(JSON.stringify(SWITCHER))), SWITCHER);
  });

  test("drops what is not an entry", () => {
    const parsed = parseVersions([
      SWITCHER[0],
      { name: "no url", version: "0.9" },
      { name: 3, version: "0.8", url: "/scenet/v0.8/" },
      { name: "elsewhere", version: "0.7", url: "https://example.com/" },
      "0.6",
    ]);
    assert.deepEqual(parsed, [SWITCHER[0]]);
  });

  test("anything but a list is no versions", () => {
    assert.deepEqual(parseVersions({ versions: SWITCHER }), []);
    assert.deepEqual(parseVersions(null), []);
  });

  test("it is the file the documentation reads", () => {
    assert.equal(SWITCHER_URL, "/scenet/switcher.json");
  });
});

describe("currentVersion", () => {
  test("the root is the latest release", () => {
    assert.equal(currentVersion(SWITCHER, "/scenet/playground/")?.version, "0.11");
  });

  test("a version's own playground, not the root's that prefixes it", () => {
    assert.equal(currentVersion(SWITCHER, "/scenet/dev/playground/")?.version, "dev");
    assert.equal(currentVersion(SWITCHER, "/scenet/v0.10/playground/index.html")?.version, "0.10");
  });

  test("served from anywhere else, it is no version", () => {
    assert.equal(currentVersion(SWITCHER, "/playground/"), undefined);
    assert.equal(currentVersion(SWITCHER, "/"), undefined);
    assert.equal(currentVersion(SWITCHER, "/scenet/v0.9/playground/"), undefined);
  });
});

describe("playgroundUrl", () => {
  test("keeps the document a share link carries", () => {
    assert.equal(playgroundUrl(SWITCHER[2]!, "#src=abc"), "/scenet/v0.10/playground/#src=abc");
    assert.equal(playgroundUrl(SWITCHER[1]!, ""), "/scenet/playground/");
  });
});

describe("banner", () => {
  test("none on the latest release", () => {
    assert.equal(banner(SWITCHER, SWITCHER[1]!), undefined);
  });

  test("main is the development version", () => {
    const shown = banner(SWITCHER, SWITCHER[0]!);
    assert.match(shown?.text ?? "", /development version/);
    assert.equal(shown?.latest.url, "/scenet/");
  });

  test("an older release is old, and says which", () => {
    const shown = banner(SWITCHER, SWITCHER[2]!);
    assert.match(shown?.text ?? "", /old version.*0\.10/);
    assert.equal(shown?.latest.version, "0.11");
  });

  test("none without exactly one latest", () => {
    const unmarked = SWITCHER.map(({ preferred: _, ...entry }) => entry);
    assert.equal(banner(unmarked, unmarked[0]!), undefined);
  });
});

describe("the documentation's home page", () => {
  test("opens the example it shows, as a share link this playground reads", async () => {
    const home = readFileSync(new URL("../../docs/index.md", import.meta.url), "utf8");
    const token = /playground\/#src=([A-Za-z0-9_-]+)/.exec(home)?.[1];
    assert.ok(token, "the home page links the playground with a document");
    const example = readFileSync(
      new URL("../../examples/gallery/01-two-characters.panel.yaml", import.meta.url),
      "utf8",
    ).replaceAll("\r\n", "\n");
    const body = example.slice(example.indexOf("panel:"));
    assert.equal(await decodeSource(token), body);
  });
});
