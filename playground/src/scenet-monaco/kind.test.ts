/**
 * Which kind a document is, guessed from its text: the compiler dispatches on a file's
 * extension, and an editor buffer has none.
 */

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { detectKind } from "./kind.ts";

describe("detectKind", () => {
  for (const heading of ["PANEL 1", "Panel 1.", "panel 1", "Panel 1. A corner, in the rain.", "## PANEL 2", "**PANEL 2**", "Panel One"]) {
    test(`a script is one with a panel heading: ${heading}`, () => {
      assert.equal(detectKind(`PAGE ONE\n\n${heading}\nALICE\nHi.\n`), "script");
    });
  }

  test("a script may start with its front matter after a blank line", () => {
    assert.equal(detectKind("\n---\ncast: {ALICE: {reference: alice}}\n---\n"), "script");
  });

  test("a YAML panel that opens with a document marker is a panel", () => {
    assert.equal(detectKind("---\ncast: {a: {reference: alice}}\n"), "panel");
  });

  test("a YAML comment that reads like a heading does not make a script", () => {
    assert.equal(detectKind("# Panel 1: the setup\ncast: {a: {reference: alice}}\n"), "panel");
  });

  test("a scene has panels", () => {
    assert.equal(detectKind("panels:\n  a: {cast: {x: {reference: alice}}}\n"), "scene");
  });

  test("anything else is a panel, an empty buffer included", () => {
    assert.equal(detectKind("cast: {a: {reference: alice}}\n"), "panel");
    assert.equal(detectKind(""), "panel");
  });
});
