/**
 * How the extension invokes `scenet`: one place for both the preview and the check, so
 * the two cannot read `scenet.executable` differently.
 */

import assert from "node:assert/strict";
import { join } from "node:path";
import { describe, test } from "node:test";

import { buildInvocation, checkInvocation, parseExecutable } from "../src/invocation";

describe("parseExecutable", () => {
  test("a bare command", () => {
    assert.deepEqual(parseExecutable("scenet"), { command: "scenet", leadingArgs: [] });
  });

  test("a command with its own arguments", () => {
    assert.deepEqual(parseExecutable("  uv   run scenet "), { command: "uv", leadingArgs: ["run", "scenet"] });
  });

  test("a quoted path keeps its spaces", () => {
    // The setting asks for an absolute path when scenet is not on PATH, and on Windows
    // those are often under `Program Files` or a user name with a space in it.
    assert.deepEqual(parseExecutable('"C:\\Program Files\\Scenet\\scenet.exe" --verbose'), {
      command: "C:\\Program Files\\Scenet\\scenet.exe",
      leadingArgs: ["--verbose"],
    });
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

describe("buildInvocation", () => {
  const folder = join("work", "comic");
  const file = join(folder, "pages", "duel.panel.yaml");
  const output = join("scratch", "preview.svg");

  test("the preview runs from the workspace folder, as the check does", () => {
    // VS Code runs its extension host from its own install directory, where
    // `uv run scenet` finds no project and fails with "program not found".
    assert.deepEqual(buildInvocation({ executable: "uv run scenet", file, output, workspaceFolder: folder }), {
      command: "uv",
      args: ["run", "scenet", "build", file, "-o", output],
      cwd: folder,
    });
  });

  test("a file outside any workspace folder builds from its own directory", () => {
    const { cwd } = buildInvocation({ executable: "scenet", file, output, workspaceFolder: undefined });
    assert.equal(cwd, join(folder, "pages"));
  });
});
