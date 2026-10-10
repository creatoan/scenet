/**
 * What a `scenet check` run means, before any of it reaches the editor.
 *
 * A failed run must never look like a clean document. Each way it can fail becomes one
 * message a person can act on: install or point at the compiler, fix the invocation, or
 * report a crash, because a traceback from `scenet` is a bug in `scenet`. No `vscode`
 * import: this is tested on its own.
 */

/** A finished process, as `child_process.execFile` reports it, reduced to what matters. */
export interface RunResult {
  /** Why the process did not run or finish normally, such as `ENOENT` or `ABORT_ERR`. */
  readonly errorCode: string | undefined;
  /** The exit status, or `null` when the process never ran to an exit. */
  readonly exitCode: number | null;
  readonly stdout: string;
  readonly stderr: string;
}

/**
 * Reduce `execFile`'s callback arguments to a `RunResult`.
 *
 * `execFile` signals both a non-zero exit and a failure to start through its error, and
 * tells them apart only by whether `code` is a number or a string.
 */
export function fromExecFile(error: Error | null, stdout: string, stderr: string): RunResult {
  if (error === null) {
    return { errorCode: undefined, exitCode: 0, stdout, stderr };
  }
  const code: unknown = (error as { code?: unknown }).code;
  if (typeof code === "number") {
    return { errorCode: undefined, exitCode: code, stdout, stderr };
  }
  const errorCode = typeof code === "string" ? code : error.name === "AbortError" ? "ABORT_ERR" : error.name;
  return { errorCode, exitCode: null, stdout, stderr };
}

export type Outcome =
  | { readonly kind: "report"; readonly log: unknown }
  | { readonly kind: "cancelled" }
  | { readonly kind: "notFound" }
  | { readonly kind: "usage"; readonly detail: string }
  | { readonly kind: "crash"; readonly detail: string };

export type Failure = Extract<Outcome, { kind: "notFound" | "usage" | "crash" }>;

const TRACEBACK = "Traceback (most recent call last)";

/**
 * Classify a run by the CLI's documented contract (`docs/reference/cli.md`): exit 0 or 1
 * with a SARIF document on stdout, or exit 2 for a usage error.
 */
export function classifyRun(run: RunResult): Outcome {
  if (run.errorCode === "ABORT_ERR") {
    return { kind: "cancelled" };
  }
  if (run.errorCode === "ENOENT") {
    return { kind: "notFound" };
  }
  if (run.stderr.includes(TRACEBACK)) {
    return { kind: "crash", detail: run.stderr.trim() };
  }
  if (run.errorCode !== undefined) {
    return { kind: "crash", detail: `could not run scenet: ${run.errorCode}` };
  }
  if (run.exitCode === 2) {
    return { kind: "usage", detail: run.stderr.trim() };
  }
  if (run.exitCode !== 0 && run.exitCode !== 1) {
    return { kind: "crash", detail: run.stderr.trim() || `scenet exited with status ${String(run.exitCode)}` };
  }
  let log: unknown;
  try {
    log = JSON.parse(run.stdout);
  } catch {
    return { kind: "crash", detail: `scenet did not print a SARIF report:\n${run.stdout}${run.stderr}`.trim() };
  }
  if (!isSarif21(log)) {
    return { kind: "crash", detail: `scenet printed JSON that is not a SARIF 2.1.0 report:\n${run.stdout}`.trim() };
  }
  return { kind: "report", log };
}

function isSarif21(value: unknown): boolean {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { version?: unknown }).version === "2.1.0" &&
    Array.isArray((value as { runs?: unknown }).runs)
  );
}

export type FailureAction = "openSettings" | "showOutput" | "reportIssue";

export interface FailureMessage {
  readonly message: string;
  readonly actions: readonly FailureAction[];
}

/** The message a failure is shown as, and what the person can do from it. */
export function describeFailure(failure: Failure, executable: string): FailureMessage {
  switch (failure.kind) {
    case "notFound":
      return {
        message:
          `Scenet: could not run '${executable}', so documents are not being checked. ` +
          "Install scenet, or set scenet.executable (for example to 'uv run scenet').",
        actions: ["openSettings"],
      };
    case "usage":
      return {
        message: `Scenet: scenet check refused the request: ${failure.detail}`,
        actions: ["showOutput", "openSettings"],
      };
    case "crash":
      return {
        message: "Scenet: scenet check crashed, which is a bug in scenet. Please report it, with the output.",
        actions: ["showOutput", "reportIssue"],
      };
  }
}
