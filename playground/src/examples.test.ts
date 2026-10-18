import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { decodeBase64, exampleFiles, staysInside } from "./examples.ts";

describe("the files an example names", () => {
  it("are decoded from base64", () => {
    assert.deepEqual([...decodeBase64("UE5H")], [0x50, 0x4e, 0x47]);
  });

  it("are written once each, in a fixed order", () => {
    const files = exampleFiles([
      { files: { "art/street.png": "AAE=", "art/a.png": "Ag==" } },
      {},
      { files: { "art/street.png": "/w==" } },
    ]);
    assert.deepEqual(
      files.map((file) => [file.path, [...file.bytes]]),
      [
        ["art/a.png", [2]],
        ["art/street.png", [0, 1]],
      ],
    );
  });

  for (const path of ["art/street.png", "a.png", "deep/er/x.jpg"]) {
    it(`keep a path inside the document's folder: ${path}`, () => {
      assert.equal(staysInside(path), true);
    });
  }

  for (const path of ["", "/etc/x", "../x.png", "art/../../x", "art\\x.png", "C:/x.png", "a//b", "./a"]) {
    it(`refuse a path that would leave it: ${JSON.stringify(path)}`, () => {
      assert.equal(staysInside(path), false);
    });
  }

  it("skip a path that would leave it, rather than writing it", () => {
    assert.deepEqual(exampleFiles([{ files: { "../x.png": "AA==" } }]), []);
  });
});
