/**
 * Run the extension end to end, in a real VS Code.
 *
 * The unit tests (`test/`) cover every decision the extension makes, in modules without a
 * `vscode` import. What they cannot cover is the glue: that VS Code activates the
 * extension, that a check runs on open and on save, that its findings land in the
 * Problems list where they should, and that they go when fixed. A run in a real editor
 * found a bug the unit tests could not: the preview ran `scenet` from VS Code's install
 * directory. So this runs one.
 *
 * It downloads the oldest VS Code `engines.vscode` admits -- the one the extension
 * promises to run on -- installs the YAML extension it depends on, and opens the
 * repository with the extension under development. `suite.ts` then runs inside that
 * editor. On Linux CI it runs under `xvfb-run`, so no display is needed. A run is
 * isolated: VS Code, its settings and its extensions live in `.vscode-test/`.
 */

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { downloadAndUnzipVSCode, runTests, runVSCodeCommand } from "@vscode/test-electron";

/** Pinned, so a release of it cannot change what this run means. */
const YAML_EXTENSION = "redhat.vscode-yaml@1.25.0";

async function main(): Promise<void> {
  const editor = resolve(__dirname, "..");
  const repository = resolve(editor, "..");
  const manifest = JSON.parse(readFileSync(join(editor, "package.json"), "utf8")) as {
    readonly engines: { readonly vscode: string };
  };
  const version = manifest.engines.vscode.replace(/^[\^~>=]+/, "");

  const executable = await downloadAndUnzipVSCode(version);
  // Into the run's own extensions directory, which is the one `runTests` launches with.
  await runVSCodeCommand(["--install-extension", YAML_EXTENSION], { version });

  await runTests({
    vscodeExecutablePath: executable,
    extensionDevelopmentPath: editor,
    extensionTestsPath: join(__dirname, "suite.js"),
    // The repository is the workspace, so `uv run scenet` finds the project and the
    // rule corpus is at hand.
    launchArgs: [repository, "--disable-workspace-trust", "--skip-welcome", "--skip-release-notes"],
  });
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
