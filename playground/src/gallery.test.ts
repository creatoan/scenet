import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  displayOrder,
  docHref,
  exampleHash,
  exampleIndex,
  exampleNameFromHash,
  grouped,
  neighbours,
} from "./gallery.ts";
import { tokenFromHash } from "./persist.ts";

/** Manifest order is append-only, so the tour comes last and is shown first. */
const gallery = {
  groups: ["Start here", "Staging", "Art"],
  start: 4,
  examples: [
    { file: "01-two.panel.yaml", group: "Start here" },
    { file: "02-shots.scene.yaml", group: "Staging" },
    { file: "03-art.scene.yaml", group: "Art" },
    { file: "04-angles.scene.yaml", group: "Staging" },
    { file: "05-tour.scene.yaml", group: "Start here" },
  ],
};

describe("the gallery's groups", () => {
  it("come in the manifest's order, each with its entries in manifest order", () => {
    assert.deepEqual(grouped({ ...gallery, start: -1 }), [
      { name: "Start here", indices: [0, 4] },
      { name: "Staging", indices: [1, 3] },
      { name: "Art", indices: [2] },
    ]);
  });

  it("put the example the playground opens on first in its group", () => {
    assert.deepEqual(grouped(gallery)[0], { name: "Start here", indices: [4, 0] });
  });

  it("leave out a group nothing is in", () => {
    const names = grouped({ ...gallery, groups: [...gallery.groups, "Empty"] }).map((g) => g.name);
    assert.deepEqual(names, ["Start here", "Staging", "Art"]);
  });

  it("still show an entry whose group the manifest does not list, after the others", () => {
    const stray = { ...gallery, examples: [...gallery.examples, { file: "06-x", group: "New" }] };
    assert.deepEqual(grouped(stray).at(-1), { name: "New", indices: [5] });
  });
});

describe("walking the gallery", () => {
  const order = displayOrder(gallery);

  it("goes group by group, from the tour", () => {
    assert.deepEqual(order, [4, 0, 1, 3, 2]);
  });

  it("has no previous example before the first, and no next after the last", () => {
    assert.deepEqual(neighbours(order, 4), { previous: undefined, next: 0 });
    assert.deepEqual(neighbours(order, 2), { previous: 3, next: undefined });
  });

  it("steps across a group's edge", () => {
    assert.deepEqual(neighbours(order, 0), { previous: 4, next: 1 });
  });

  it("starts at the first example from a document no example is", () => {
    assert.deepEqual(neighbours(order, -1), { previous: undefined, next: 4 });
    assert.deepEqual(neighbours(order, 99), { previous: undefined, next: 4 });
  });
});

describe("a link to an example by name", () => {
  it("names its file in the fragment", () => {
    assert.equal(exampleHash("05-tour.scene.yaml"), "#example=05-tour.scene.yaml");
  });

  it("is read back from the fragment", () => {
    assert.equal(exampleNameFromHash("#example=05-tour.scene.yaml"), "05-tour.scene.yaml");
    assert.equal(exampleNameFromHash(exampleHash("a b&c.panel.yaml")), "a b&c.panel.yaml");
  });

  it("is not a share link, and a share link is not one", () => {
    assert.equal(tokenFromHash(exampleHash("05-tour.scene.yaml")), undefined);
    assert.equal(exampleNameFromHash("#src=abc"), undefined);
  });

  for (const hash of ["", "#", "#example=", "#other=1"]) {
    it(`is absent from ${JSON.stringify(hash)}`, () => {
      assert.equal(exampleNameFromHash(hash), undefined);
    });
  }

  it("finds the example by its file", () => {
    assert.equal(exampleIndex(gallery.examples, "03-art.scene.yaml"), 2);
    assert.equal(exampleIndex(gallery.examples, "99-gone.panel.yaml"), undefined);
  });
});

describe("the documentation an example points to", () => {
  it("is the same version's page, built as HTML, at its heading", () => {
    assert.equal(docHref("reference/language.md#camera"), "../reference/language.html#camera");
  });

  it("may be a whole page", () => {
    assert.equal(docHref("tutorial/first_panel.md"), "../tutorial/first_panel.html");
  });
});
