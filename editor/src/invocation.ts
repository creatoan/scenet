/**
 * How the extension invokes `scenet`.
 *
 * The preview and the check both shell out to the CLI, so they read `scenet.executable`
 * through one function and cannot come to disagree about it. No `vscode` import: this is
 * tested on its own.
 */

import { dirname } from "node:path";

export interface Executable {
  readonly command: string;
  readonly leadingArgs: readonly string[];
}

/**
 * Split the `scenet.executable` setting into a command and the arguments it brings.
 *
 * `uv run scenet` is a command, `uv`, with two arguments of its own, which go before
 * whatever the extension adds. A part in double quotes keeps its spaces, which an
 * absolute path on Windows often needs. Backslashes are literal, being path separators
 * there, so there is no escaping: a quote cannot be part of a path anyway.
 */
export function parseExecutable(setting: string): Executable {
  const parts = [...setting.matchAll(/"([^"]*)"|(\S+)/g)].map((match) => match[1] ?? match[2] ?? "");
  const [command, ...leadingArgs] = parts.filter((part) => part !== "");
  return { command: command ?? "scenet", leadingArgs };
}

export interface Invocation {
  readonly command: string;
  readonly args: readonly string[];
  readonly cwd: string;
}

export interface CheckRequest {
  /** The `scenet.executable` setting. */
  readonly executable: string;
  /** The `scenet.checkDeep` setting. */
  readonly deep: boolean;
  /** Absolute path of the document to check. */
  readonly file: string;
  /** The workspace folder holding the document, if any. */
  readonly workspaceFolder: string | undefined;
}

/**
 * The `scenet check` run for one document.
 *
 * It runs from the document's workspace folder, or its own directory when it has none.
 * `uv run` finds its project from the working directory, so `uv run scenet` only works
 * from somewhere inside the project, and that is also the directory the SARIF report's
 * relative uris are written against. The workspace folder is the document's root too: a
 * file it names may be anywhere in the workspace, and nowhere outside it.
 */
export function checkInvocation(request: CheckRequest): Invocation {
  const { command, leadingArgs } = parseExecutable(request.executable);
  return {
    command,
    args: [
      ...leadingArgs,
      "check",
      "--format",
      "sarif",
      ...(request.deep ? ["--deep"] : []),
      ...rooted(request.workspaceFolder),
      request.file,
    ],
    cwd: request.workspaceFolder ?? dirname(request.file),
  };
}

/**
 * `--root` the workspace folder, or nothing: with none, the CLI chooses the root itself,
 * the nearest folder holding a `scenet.toml` above the document, or the document's own.
 */
function rooted(workspaceFolder: string | undefined): readonly string[] {
  return workspaceFolder === undefined ? [] : ["--root", workspaceFolder];
}

export interface BuildRequest {
  /** The `scenet.executable` setting. */
  readonly executable: string;
  /** Absolute path of the document to preview. */
  readonly file: string;
  /** Where to write the SVG. */
  readonly output: string;
  /** The workspace folder holding the document, if any. */
  readonly workspaceFolder: string | undefined;
}

/**
 * The `scenet build` run for the preview, from the same directory as the check and for
 * the same reason. VS Code starts its extension host in its own install directory, and
 * `uv run scenet` there fails with "program not found".
 */
export function buildInvocation(request: BuildRequest): Invocation {
  const { command, leadingArgs } = parseExecutable(request.executable);
  return {
    command,
    // The preview is written to a scratch folder and inlined into a webview, where a
    // picture linked by the path the document wrote would resolve against neither.
    args: [
      ...leadingArgs,
      "build",
      request.file,
      "-o",
      request.output,
      "--embed-images",
      ...rooted(request.workspaceFolder),
    ],
    cwd: request.workspaceFolder ?? dirname(request.file),
  };
}
