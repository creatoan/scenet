/**
 * The end-to-end checks, run inside VS Code by `run.ts`.
 *
 * No test framework: VS Code calls `run`, which throws if anything failed, and that is
 * the whole contract (`@vscode/test-electron`). Each check prints one line, so a CI log
 * reads as a list.
 *
 * Everything goes through the API a user's actions go through -- open, edit, save,
 * change a setting -- and is judged by the Problems list, `languages.getDiagnostics`.
 * The checker runs as `uv run scenet` from the repository, the setting the README
 * suggests.
 */

import assert from "node:assert/strict";
import { copyFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import * as vscode from "vscode";

/** Long enough for a first `uv run` that has to sync, on a slow runner. */
const PATIENCE = 120_000;

interface Expected {
  readonly file: string;
  readonly rule: string;
  /** Start line, start character, end line, end character, 0-based as VS Code counts. */
  readonly range: readonly [number, number, number, number];
}

/** One finding per kind of document and of position, from `tests/rule_corpus/`. */
const CORPUS: readonly Expected[] = [
  // A line and a column.
  { file: "unknown-actor.panel.yaml", rule: "scenet/unknown-actor", range: [3, 14, 3, 17] },
  // A YAML parse error, beside the YAML extension's own diagnostic for it.
  { file: "syntax.panel.yaml", rule: "scenet/syntax", range: [2, 23, 2, 24] },
  // A comic script: the whole line.
  { file: "duplicate-panel.script", rule: "scenet/duplicate-panel", range: [9, 0, 9, 7] },
  // A finding about the whole document, spanning lines.
  { file: "not-a-mapping.panel.yaml", rule: "scenet/not-a-mapping", range: [1, 0, 3, 0] },
  // A scene document.
  { file: "page-layout.scene.yaml", rule: "scenet/page-layout", range: [5, 22, 5, 27] },
];

function repository(): string {
  const folder = vscode.workspace.workspaceFolders?.[0];
  assert.ok(folder, "the repository is open as the workspace");
  return folder.uri.fsPath;
}

function corpus(file: string): vscode.Uri {
  return vscode.Uri.file(join(repository(), "tests", "rule_corpus", file));
}

function findings(uri: vscode.Uri): vscode.Diagnostic[] {
  return vscode.languages.getDiagnostics(uri).filter((diagnostic) => diagnostic.source === "scenet");
}

async function until(condition: () => boolean, what: string): Promise<void> {
  const deadline = Date.now() + PATIENCE;
  while (!condition()) {
    if (Date.now() > deadline) {
      throw new Error(`timed out waiting until ${what}`);
    }
    await new Promise((done) => setTimeout(done, 250));
  }
}

async function open(uri: vscode.Uri): Promise<vscode.TextDocument> {
  const document = await vscode.workspace.openTextDocument(uri);
  await vscode.window.showTextDocument(document);
  return document;
}

async function setting(name: string, value: unknown): Promise<void> {
  await vscode.workspace.getConfiguration("scenet").update(name, value, vscode.ConfigurationTarget.Global);
}

const checks: [string, () => Promise<void>][] = [];

function check(name: string, body: () => Promise<void>): void {
  checks.push([name, body]);
}

check("the extension activates on a panel document", async () => {
  await open(corpus("unknown-actor.panel.yaml"));
  const extension = vscode.extensions.getExtension("scenet.scenet");
  assert.ok(extension, "the extension under development is installed");
  await until(() => extension.isActive, "the extension is active");
});

for (const expected of CORPUS) {
  check(`${expected.file}: ${expected.rule} where it is`, async () => {
    const uri = corpus(expected.file);
    await open(uri);
    await until(() => findings(uri).length > 0, `${expected.file} has findings`);
    const [finding, ...rest] = findings(uri);
    assert.equal(rest.length, 0, "one finding");
    assert.ok(finding);
    const { start, end } = finding.range;
    assert.deepEqual([start.line, start.character, end.line, end.character], [...expected.range]);
    assert.equal(finding.severity, vscode.DiagnosticSeverity.Error);
    assert.ok(typeof finding.code === "object", "the rule is linked");
    assert.equal(finding.code.value, expected.rule);
    assert.equal(finding.code.target.toString(), "https://creatoan.github.io/scenet/reference/cli.html#rules");
  });
}

check("a comic script is its own language", async () => {
  const document = await open(corpus("duplicate-panel.script"));
  assert.equal(document.languageId, "scenet-script");
});

check("a fix, once saved, clears its finding", async () => {
  // A copy inside the repository, so it is checked from the same workspace folder.
  const scratch = join(repository(), "editor", ".vscode-test", "e2e");
  mkdirSync(scratch, { recursive: true });
  const path = join(scratch, "fix-me.panel.yaml");
  copyFileSync(corpus("unknown-actor.panel.yaml").fsPath, path);
  const uri = vscode.Uri.file(path);

  const document = await open(uri);
  await until(() => findings(uri).length > 0, "the copy has its finding");

  // The last `bpb`: the first is in the file's comment.
  const at = document.getText().lastIndexOf("bpb");
  const edit = new vscode.WorkspaceEdit();
  edit.replace(uri, new vscode.Range(document.positionAt(at), document.positionAt(at + 3)), "bob");
  assert.ok(await vscode.workspace.applyEdit(edit));
  assert.ok(await document.save());
  await until(() => findings(uri).length === 0, "the fixed copy has no findings");
});

check("--deep finds what only a compile can", async () => {
  const uri = corpus("layout.panel.yaml");
  await open(uri);
  await setting("checkDeep", true);
  try {
    await until(() => findings(uri).length > 0, "layout.panel.yaml has a finding under --deep");
    const [finding] = findings(uri);
    assert.ok(finding && typeof finding.code === "object");
    assert.equal(finding.code.value, "scenet/layout");
  } finally {
    await setting("checkDeep", undefined);
  }
});

check("a missing executable leaves no stale findings", async () => {
  const uri = corpus("unknown-actor.panel.yaml");
  await open(uri);
  await until(() => findings(uri).length > 0, "the document has its finding");
  await setting("executable", "scenet-that-does-not-exist");
  try {
    await until(() => findings(uri).length === 0, "the finding is cleared");
  } finally {
    await setting("executable", "uv run scenet");
  }
});

export async function run(): Promise<void> {
  await setting("executable", "uv run scenet");
  const failed: string[] = [];
  for (const [name, body] of checks) {
    try {
      await body();
      console.log(`  ok    ${name}`);
    } catch (error) {
      failed.push(name);
      console.log(`  FAIL  ${name}\n        ${String(error instanceof Error ? error.message : error).replaceAll("\n", "\n        ")}`);
    }
  }
  console.log(`\n${checks.length - failed.length} passed, ${failed.length} failed`);
  if (failed.length > 0) {
    throw new Error(`end-to-end checks failed: ${failed.join("; ")}`);
  }
}
