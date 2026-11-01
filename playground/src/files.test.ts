import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { fileKind, formatSize, imageType, listed } from "./files.ts";

describe("what a file beside the document is", () => {
  it("is text for a contract, YAML or JSON, shown as it is written", () => {
    for (const path of ["art/figures.art.yaml", "notes.yml", "data.json", "README.txt"]) {
      assert.equal(fileKind(path), "text", path);
    }
  });

  it("is a picture for a PNG or a JPEG, whatever case its extension", () => {
    for (const path of ["art/street.png", "art/a.JPG", "b.jpeg"]) {
      assert.equal(fileKind(path), "image", path);
    }
    assert.equal(imageType("art/street.png"), "image/png");
    assert.equal(imageType("art/a.JPG"), "image/jpeg");
    assert.equal(imageType("notes.yml"), undefined);
  });

  it("is a font for TrueType or OpenType", () => {
    assert.equal(fileKind("fonts/Comic.ttf"), "font");
    assert.equal(fileKind("fonts/Comic.OTF"), "font");
  });

  it("is anything else otherwise, shown by name and size only", () => {
    assert.equal(fileKind("archive.zip"), "other");
    assert.equal(fileKind("art/no-extension"), "other");
  });
});

describe("a file's size", () => {
  it("in bytes, kilobytes or megabytes, as a person reads it", () => {
    assert.equal(formatSize(0), "0 B");
    assert.equal(formatSize(812), "812 B");
    assert.equal(formatSize(12_345), "12.3 kB");
    assert.equal(formatSize(1_400_000), "1.4 MB");
  });
});

describe("the files listed", () => {
  it("in path order, the same in every browser", () => {
    const files = [
      { path: "fonts/Z.ttf" },
      { path: "art/street.png" },
      { path: "art/figures.png" },
      { path: "art/figures.art.yaml" },
    ];
    assert.deepEqual(
      listed(files).map((file) => file.path),
      ["art/figures.art.yaml", "art/figures.png", "art/street.png", "fonts/Z.ttf"],
    );
    assert.equal(files[0]?.path, "fonts/Z.ttf", "the list it was given is left as it was");
  });
});
