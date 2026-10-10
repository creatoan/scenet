/**
 * `scenet check` findings as editor diagnostics, on open and on save.
 *
 * This is the glue, and deliberately thin: what to run is `invocation.ts`, what a run
 * means is `outcome.ts`, and where a finding goes is `sarif.ts`, all three tested
 * without an editor. What is left here is the part only VS Code can do: listen, run,
 * cancel, show.
 *
 * Like the preview, this shells out rather than reimplementing the checker, so the
 * editor reports exactly what `scenet check` reports.
 */

import { execFile } from "node:child_process";
import { readFileSync } from "node:fs";
import * as vscode from "vscode";

import { checkInvocation, type Invocation } from "./invocation";
import { classifyRun, describeFailure, fromExecFile, type Failure, type RunResult } from "./outcome";
import { MalformedSarif, sarifToDiagnostics, type DiagnosticSpec } from "./sarif";

/** Documents `scenet check` reads. */
const CHECKED = /\.(panel|scene)\.yaml$|\.script$/;

const ISSUES = "https://github.com/creatoan/scenet/issues/new";

const SEVERITY: Record<DiagnosticSpec["severity"], vscode.DiagnosticSeverity> = {
  error: vscode.DiagnosticSeverity.Error,
  warning: vscode.DiagnosticSeverity.Warning,
  information: vscode.DiagnosticSeverity.Information,
};

export class Checker implements vscode.Disposable {
  private readonly collection = vscode.languages.createDiagnosticCollection("scenet");
  /** The run in flight for each document, so a newer one can cancel it. */
  private readonly running = new Map<string, AbortController>();
  /** The files each document's last run put diagnostics on, so a fix can clear them. */
  private readonly shown = new Map<string, readonly vscode.Uri[]>();
  /** Failures already shown, so a broken setting is one message, not one per save. */
  private readonly reported = new Set<Failure["kind"]>();
  private readonly subscriptions: vscode.Disposable[] = [];

  constructor(private readonly output: vscode.LogOutputChannel) {
    this.subscriptions.push(
      this.collection,
      vscode.workspace.onDidOpenTextDocument((document) => this.check(document)),
      vscode.workspace.onDidSaveTextDocument((document) => this.check(document)),
      vscode.workspace.onDidCloseTextDocument((document) => this.forget(document.uri)),
      vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration("scenet")) {
          // A changed setting deserves a fresh chance to fail, and a fresh check.
          this.reported.clear();
          this.checkAll();
        }
      }),
    );
    this.checkAll();
  }

  dispose(): void {
    for (const controller of this.running.values()) {
      controller.abort();
    }
    this.running.clear();
    for (const subscription of this.subscriptions) {
      subscription.dispose();
    }
  }

  private checkAll(): void {
    for (const document of vscode.workspace.textDocuments) {
      this.check(document);
    }
  }

  private check(document: vscode.TextDocument): void {
    const config = vscode.workspace.getConfiguration("scenet", document.uri);
    if (document.uri.scheme !== "file" || !CHECKED.test(document.uri.fsPath)) {
      return;
    }
    if (!config.get<boolean>("checkOnSave", true)) {
      this.forget(document.uri);
      return;
    }
    // The checker reads the file on disk. Unsaved edits are checked when they are saved.
    if (document.isDirty) {
      return;
    }

    const key = document.uri.toString();
    this.running.get(key)?.abort();
    const controller = new AbortController();
    this.running.set(key, controller);

    const executable = config.get<string>("executable", "scenet");
    const invocation = checkInvocation({
      executable,
      deep: config.get<boolean>("checkDeep", false),
      file: document.uri.fsPath,
      workspaceFolder: vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath,
    });
    void run(invocation, controller.signal).then((result) => {
      if (this.running.get(key) !== controller) {
        return; // A newer run owns this document now.
      }
      this.running.delete(key);
      this.apply(document, invocation, executable, result);
    });
  }

  private apply(document: vscode.TextDocument, invocation: Invocation, executable: string, result: RunResult): void {
    const outcome = classifyRun(result);
    if (outcome.kind === "cancelled") {
      return;
    }
    if (result.stderr.trim() !== "") {
      this.output.info(`${invocation.command} ${invocation.args.join(" ")}\n${result.stderr.trim()}`);
    }
    if (outcome.kind !== "report") {
      this.fail(document.uri, outcome, executable);
      return;
    }
    let mapped: Map<string, DiagnosticSpec[]>;
    try {
      mapped = sarifToDiagnostics(outcome.log, {
        cwd: invocation.cwd,
        checkedFile: document.uri.fsPath,
        lineText: (file, line) => lineOf(document, file, line),
      });
    } catch (error) {
      if (!(error instanceof MalformedSarif)) {
        throw error;
      }
      this.fail(document.uri, { kind: "crash", detail: `${error.message}\n${result.stdout}` }, executable);
      return;
    }

    // Replacing, not adding: whatever the last run showed and this one did not find is
    // fixed, and goes.
    this.clear(document.uri);
    const shown: vscode.Uri[] = [];
    for (const [file, specs] of mapped) {
      const uri = vscode.Uri.file(file);
      this.collection.set(uri, specs.map(toDiagnostic));
      shown.push(uri);
    }
    this.shown.set(document.uri.toString(), shown);
  }

  /** A failed check shows nothing stale, and says why once per kind of failure. */
  private fail(uri: vscode.Uri, failure: Failure, executable: string): void {
    this.clear(uri);
    if (failure.kind !== "notFound") {
      this.output.error(failure.detail);
    }
    if (this.reported.has(failure.kind)) {
      return;
    }
    this.reported.add(failure.kind);
    const { message, actions } = describeFailure(failure, executable);
    const labels = { openSettings: "Open Settings", showOutput: "Show Output", reportIssue: "Report Issue" };
    void vscode.window.showErrorMessage(message, ...actions.map((action) => labels[action])).then((chosen) => {
      if (chosen === labels.openSettings) {
        void vscode.commands.executeCommand("workbench.action.openSettings", "scenet.executable");
      } else if (chosen === labels.showOutput) {
        this.output.show(true);
      } else if (chosen === labels.reportIssue) {
        void vscode.env.openExternal(vscode.Uri.parse(ISSUES));
      }
    });
  }

  private clear(uri: vscode.Uri): void {
    for (const shown of this.shown.get(uri.toString()) ?? [uri]) {
      this.collection.delete(shown);
    }
    this.shown.delete(uri.toString());
  }

  private forget(uri: vscode.Uri): void {
    this.running.get(uri.toString())?.abort();
    this.running.delete(uri.toString());
    this.clear(uri);
  }
}

function run(invocation: Invocation, signal: AbortSignal): Promise<RunResult> {
  return new Promise((done) => {
    execFile(
      invocation.command,
      [...invocation.args],
      { cwd: invocation.cwd, signal, windowsHide: true, maxBuffer: 16 * 1024 * 1024 },
      (error, stdout, stderr) => done(fromExecFile(error, stdout, stderr)),
    );
  });
}

/** A line of the checked document, or of another file the report names, read from disk. */
function lineOf(document: vscode.TextDocument, file: string, line: number): string | undefined {
  if (file === document.uri.fsPath) {
    return line < document.lineCount ? document.lineAt(line).text : undefined;
  }
  try {
    return readFileSync(file, "utf8").split(/\r?\n/)[line];
  } catch {
    return undefined;
  }
}

function toDiagnostic(spec: DiagnosticSpec): vscode.Diagnostic {
  const range = new vscode.Range(spec.start.line, spec.start.character, spec.end.line, spec.end.character);
  const diagnostic = new vscode.Diagnostic(range, spec.message, SEVERITY[spec.severity]);
  diagnostic.source = "scenet";
  if (spec.rule !== undefined) {
    diagnostic.code =
      spec.help === undefined ? spec.rule : { value: spec.rule, target: vscode.Uri.parse(spec.help) };
  }
  return diagnostic;
}
