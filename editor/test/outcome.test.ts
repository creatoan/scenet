/**
 * What a `scenet check` run means, before any of it reaches the editor.
 *
 * The rule this module exists for: a run that failed is never shown as a clean
 * document. A missing executable, a usage error and a crash each become one message a
 * person can act on, never an empty Problems list.
 */

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { classifyRun, describeFailure, fromExecFile, type RunResult } from "../src/outcome";

const SARIF = JSON.stringify({ version: "2.1.0", runs: [{ tool: { driver: { name: "scenet" } }, results: [] }] });
const TRACEBACK = 'Traceback (most recent call last):\n  File "cli.py", line 1\nKeyError: x\n';

function run(overrides: Partial<RunResult>): RunResult {
  return { errorCode: undefined, exitCode: 0, stdout: "", stderr: "", ...overrides };
}

describe("fromExecFile", () => {
  test("a clean exit", () => {
    assert.deepEqual(fromExecFile(null, SARIF, ""), run({ stdout: SARIF }));
  });

  test("a non-zero exit carries its status", () => {
    const error = Object.assign(new Error("Command failed"), { code: 1 });
    assert.deepEqual(fromExecFile(error, SARIF, ""), run({ exitCode: 1, stdout: SARIF }));
  });

  test("a process that never started carries its error code", () => {
    const error = Object.assign(new Error("spawn scenet ENOENT"), { code: "ENOENT" });
    assert.deepEqual(fromExecFile(error, "", ""), run({ errorCode: "ENOENT", exitCode: null }));
  });

  test("a run cancelled for a newer one says so", () => {
    const error = Object.assign(new Error("The operation was aborted"), { name: "AbortError", code: "ABORT_ERR" });
    assert.equal(fromExecFile(error, "", "").errorCode, "ABORT_ERR");
  });
});

describe("classifyRun", () => {
  test("a valid document is a report", () => {
    assert.equal(classifyRun(run({ stdout: SARIF })).kind, "report");
  });

  test("findings are a report too: exit 1 means the check worked", () => {
    assert.equal(classifyRun(run({ exitCode: 1, stdout: SARIF })).kind, "report");
  });

  test("an executable that is not there", () => {
    assert.deepEqual(classifyRun(run({ errorCode: "ENOENT", exitCode: null })), { kind: "notFound" });
  });

  test("a cancelled run is neither a result nor a failure", () => {
    assert.deepEqual(classifyRun(run({ errorCode: "ABORT_ERR", exitCode: null })), { kind: "cancelled" });
  });

  test("exit 2 is a usage error, with what scenet said", () => {
    const outcome = classifyRun(run({ exitCode: 2, stderr: "scenet: no such file: x.panel.yaml\n" }));
    assert.deepEqual(outcome, { kind: "usage", detail: "scenet: no such file: x.panel.yaml" });
  });

  test("a traceback is a crash, whatever the exit status", () => {
    for (const exitCode of [0, 1, 2]) {
      const outcome = classifyRun(run({ exitCode, stdout: SARIF, stderr: TRACEBACK }));
      assert.equal(outcome.kind, "crash", `exit ${exitCode}`);
    }
  });

  test("output that is not SARIF is a crash, not a clean document", () => {
    for (const stdout of ["", "not json", "{}", '{"version": "2.0.0", "runs": []}']) {
      assert.equal(classifyRun(run({ exitCode: 0, stdout })).kind, "crash", JSON.stringify(stdout));
    }
  });

  test("an exit status the CLI does not define is a crash", () => {
    const outcome = classifyRun(run({ exitCode: 3, stderr: "boom" }));
    assert.deepEqual(outcome, { kind: "crash", detail: "boom" });
  });

  test("another error starting the process is reported, not swallowed", () => {
    const outcome = classifyRun(run({ errorCode: "EACCES", exitCode: null }));
    assert.equal(outcome.kind, "crash");
  });
});

describe("describeFailure", () => {
  test("a missing executable names the command and the setting", () => {
    const { message, actions } = describeFailure({ kind: "notFound" }, "uv run scenet");
    assert.match(message, /uv run scenet/);
    assert.match(message, /scenet\.executable/);
    assert.ok(actions.includes("openSettings"));
  });

  test("a crash asks to be reported", () => {
    const { message, actions } = describeFailure({ kind: "crash", detail: TRACEBACK }, "scenet");
    assert.match(message, /report/i);
    assert.ok(actions.includes("reportIssue"));
    assert.ok(actions.includes("showOutput"));
  });

  test("a usage error says what scenet said", () => {
    const { message } = describeFailure({ kind: "usage", detail: "scenet: no such file: x" }, "scenet");
    assert.match(message, /no such file: x/);
  });
});
