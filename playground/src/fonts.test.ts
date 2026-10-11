import assert from "node:assert/strict";
import { test } from "node:test";

import { FONT_FOLDER, declaredPath, fontFileName } from "./fonts.ts";

test("a font keeps its own name, so the document can name it as the author sees it", () => {
  assert.equal(fontFileName("ComicNeue-Regular.ttf"), "ComicNeue-Regular.ttf");
  assert.equal(fontFileName("Lettering.OTF"), "Lettering.OTF");
});

test("only the file's own name is kept, never a folder it came from", () => {
  assert.equal(fontFileName("C:\\Users\\me\\Fonts\\Comic.ttf"), "Comic.ttf");
  assert.equal(fontFileName("../../etc/Comic.ttf"), "Comic.ttf");
});

test("characters a path or a YAML value would trip on become hyphens", () => {
  assert.equal(fontFileName("My Font: Bold #2.ttf"), "My-Font--Bold--2.ttf");
});

test("anything that is not a TrueType or OpenType file is refused", () => {
  assert.equal(fontFileName("notes.txt"), null);
  assert.equal(fontFileName("font.woff2"), null);
  assert.equal(fontFileName(".ttf"), null);
  assert.equal(fontFileName(""), null);
});

test("an added font is declared relative to the document, as a file beside it would be", () => {
  assert.equal(FONT_FOLDER, "fonts");
  assert.equal(declaredPath("Comic.ttf"), "fonts/Comic.ttf");
});
