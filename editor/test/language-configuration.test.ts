/**
 * Editing behaviour for `.script` files, as opposed to their colours.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

const configuration = JSON.parse(readFileSync(join(__dirname, "..", "language-configuration.json"), "utf8")) as {
  readonly comments?: unknown;
};

test("a comic script has no comment syntax, so none is declared", () => {
  // Declaring `//` made Toggle Line Comment write lines the compiler keeps as prose,
  // or reads as dialogue under a cue. The playground declares none, for that reason.
  assert.equal(configuration.comments, undefined);
});
