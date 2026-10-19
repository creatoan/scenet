import assert from "node:assert/strict";
import { test } from "node:test";

import { CONTRACT_SUFFIX, IMAGE_FOLDER, declaredImagePath, imageFileName, isContract } from "./images.ts";

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

test("an artwork contract is added beside its picture, and pairs with it by name", () => {
  assert.equal(imageFileName("p01-street.art.yaml"), "p01-street.art.yaml");
  assert.equal(imageFileName("P01.ART.YAML"), `P01${CONTRACT_SUFFIX}`);
  // Cleaned exactly as its picture is, so the two still pair.
  assert.equal(imageFileName("My street.art.yaml"), "My-street.art.yaml");
  assert.equal(imageFileName("My street.png"), "My-street.png");
  assert.ok(isContract("art/p01.art.yaml"));
  assert.ok(!isContract("art/p01.png"));
});

test("a YAML file that is not a contract is refused", () => {
  assert.equal(imageFileName("street.yaml"), null);
  assert.equal(imageFileName("street.panel.yaml"), null);
  assert.equal(imageFileName(".art.yaml"), null);
});

test("an added picture is named relative to the document, as one beside it would be", () => {
  assert.equal(IMAGE_FOLDER, "art");
  assert.equal(declaredImagePath("street.png"), "art/street.png");
});
