/**
 * Compiler findings as editor markers.
 *
 * In a module of its own, importing Monaco's types and nothing else, so it can be tested
 * without a browser.
 */

import type * as Monaco from "monaco-editor";

/**
 * One finding from the compiler's checker, as `scenet.diagnostics` reports it.
 *
 * Lines and columns are one-based and the end column is exclusive -- SARIF's convention,
 * which is also Monaco's, so they need no adjustment.
 */
export interface ScenetFinding {
  readonly rule: string;
  readonly message: string;
  readonly line: number;
  readonly column: number;
  readonly endLine: number;
  readonly endColumn: number;
  /**
   * `error` stops the document compiling. A `note` reports a house limit -- a balloon
   * over the words a publisher asks for -- and the document still compiles.
   */
  readonly level: "error" | "note";
}

/** Owner name for markers set from compiler findings, distinct from the schema's. */
export const SCENET_MARKER_OWNER = "scenet";

/** Turn compiler findings into editor markers: an error as an error, a note as information. */
export function toMarkers(
  monaco: typeof Monaco,
  findings: readonly ScenetFinding[],
): Monaco.editor.IMarkerData[] {
  return findings.map((finding) => {
    const sameLine = finding.endLine <= finding.line;
    return {
      severity: finding.level === "note" ? monaco.MarkerSeverity.Info : monaco.MarkerSeverity.Error,
      message: finding.message,
      code: finding.rule,
      source: "scenet",
      startLineNumber: finding.line,
      startColumn: finding.column,
      endLineNumber: Math.max(finding.line, finding.endLine),
      // A zero-width marker is invisible; one character at least.
      endColumn: sameLine ? Math.max(finding.endColumn, finding.column + 1) : finding.endColumn,
    };
  });
}
