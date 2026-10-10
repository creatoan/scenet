/**
 * How the extension invokes `scenet`: one place for both the preview and the check, so
 * the two cannot read `scenet.executable` differently.
 */

import assert from "node:assert/strict";
import { join } from "node:path";
import { describe, test } from "node:test";

import { checkInvocation, parseExecutable } from "../src/invocation";

describe("parseExecutable", () => {
  test("a bare command", () => {
    assert.deepEqual(parseExecutable("scenet"), { command: "scenet", leadingArgs: [] });
  });

  test("a command with its own arguments", () => {
    assert.deepEqual(parseExecutable("  uv   run scenet "), { command: "uv", leadingArgs: ["run", "scenet"] });
  });

  test("an empty setting falls back to scenet", () => {
    assert.deepEqual(parseExecutable("   "), { command: "scenet", leadingArgs: [] });
  });
});

describe("checkInvocation", () => {
  const folder = join("work", "comic");
  const file = join(folder, "pages", "duel.panel.yaml");

  test("asks for SARIF, for the one file, from the workspace folder", () => {
    assert.deepEqual(checkInvocation({ executable: "uv run scenet", deep: false, file, workspaceFolder: folder }), {
      command: "uv",
      args: ["run", "scenet", "check", "--format", "sarif", file],
      cwd: folder,
    });
  });

  test("--deep when asked for", () => {
    const { args } = checkInvocation({ executable: "scenet", deep: true, file, workspaceFolder: folder });
    assert.deepEqual(args, ["check", "--format", "sarif", "--deep", file]);
  });

  test("a file outside any workspace folder runs from its own directory", () => {
    // `uv run` finds its project from the working directory, so it has to be one near
    // the document rather than wherever the editor happened to start.
    const { cwd } = checkInvocation({ executable: "scenet", deep: false, file, workspaceFolder: undefined });
    assert.equal(cwd, join(folder, "pages"));
  });
});
