import assert from "node:assert/strict";
import { test } from "node:test";

import { IMAGE_FOLDER, declaredImagePath, imageFileName } from "./images.ts";

test("a picture keeps its own name, so the document can name it as the author sees it", () => {
  assert.equal(imageFileName("p01-street.png"), "p01-street.png");
  assert.equal(imageFileName("Photo.JPG"), "Photo.JPG");
  assert.equal(imageFileName("scan.jpeg"), "scan.jpeg");
});

test("only the file's own name is kept, never a folder it came from", () => {
  assert.equal(imageFileName("C:\\Users\\me\\Pictures\\street.png"), "street.png");
  assert.equal(imageFileName("../../etc/street.png"), "street.png");
});

test("characters a path, a link or a YAML value would trip on become hyphens", () => {
  assert.equal(imageFileName("My street: #2 (dusk).png"), "My-street---2--dusk-.png");
});

test("anything that is not a PNG or a JPEG is refused", () => {
  assert.equal(imageFileName("street.gif"), null);
  assert.equal(imageFileName("street.webp"), null);
  assert.equal(imageFileName("street.svg"), null);
  assert.equal(imageFileName(".png"), null);
  assert.equal(imageFileName(""), null);
});

test("an added picture is named relative to the document, as one beside it would be", () => {
  assert.equal(IMAGE_FOLDER, "art");
  assert.equal(declaredImagePath("street.png"), "art/street.png");
});
