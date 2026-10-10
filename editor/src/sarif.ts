/**
 * Map a SARIF 2.1.0 report from `scenet check` to editor diagnostics.
 *
 * Positions are where the two disagree. SARIF counts lines and columns from 1, VS Code
 * from 0; SARIF counts columns in whatever unit the run's `columnKind` names, Scenet's
 * being Unicode code points, while VS Code counts UTF-16 code units, so a column past an
 * emoji moves. And SARIF lets a region leave out its columns and its end, which mean
 * "from the start of the line" and "to the end of it" (sections 3.30.5-3.30.8).
 *
 * No `vscode` import, so that all of this is tested on its own: a `DiagnosticSpec` is
 * everything a `vscode.Diagnostic` needs, in plain data.
 *
 * Reference: https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/sarif-v2.1.0-errata01-os-complete.html
 */

import { isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** Where every `scenet/...` rule is documented. */
export const RULE_REFERENCE = "https://creatoan.github.io/scenet/reference/cli.html#rules";

export type Severity = "error" | "warning" | "information";

/** A 0-based position, its character in UTF-16 code units, as VS Code counts. */
export interface Place {
  readonly line: number;
  readonly character: number;
}

export interface DiagnosticSpec {
  readonly start: Place;
  readonly end: Place;
  readonly message: string;
  readonly severity: Severity;
  /** The SARIF `ruleId`, such as `scenet/unknown-actor`. */
  readonly rule: string | undefined;
  /** Where the rule is explained, for a rule Scenet defines. */
  readonly help: string | undefined;
}

export interface MappingOptions {
  /** The directory `scenet check` ran in, which relative uris are written against. */
  readonly cwd: string;
  /** The document that was checked, for a result that names no file. */
  readonly checkedFile: string;
  /** A 0-based line of a file, without its line ending; `undefined` if unknown. */
  readonly lineText: (file: string, line: number) => string | undefined;
}

/** The report was not a SARIF log at all, which is a failure, not a clean document. */
export class MalformedSarif extends Error {
  override readonly name = "MalformedSarif";
}

/**
 * Every result in the report, grouped by the absolute path of the file it is in.
 *
 * A file with no results is absent from the map, and an empty map means the report found
 * nothing: the caller clears what it showed before.
 */
export function sarifToDiagnostics(log: unknown, options: MappingOptions): Map<string, DiagnosticSpec[]> {
  if (!isRecord(log) || !Array.isArray(log["runs"])) {
    throw new MalformedSarif("not a SARIF log: no `runs` array");
  }
  const found = new Map<string, DiagnosticSpec[]>();
  for (const run of log["runs"]) {
    if (!isRecord(run)) {
      throw new MalformedSarif("not a SARIF log: a run is not an object");
    }
    const codePoints = run["columnKind"] !== "utf16CodeUnits";
    const rules = arrayOf(recordAt(recordAt(run, "tool"), "driver")?.["rules"]);
    for (const result of arrayOf(run["results"])) {
      if (!isRecord(result)) {
        continue;
      }
      const physical = recordAt(arrayOf(result["locations"]).find(isRecord), "physicalLocation");
      const file = fileOf(stringAt(recordAt(physical, "artifactLocation"), "uri"), options);
      const region = recordAt(physical, "region");
      const rule = stringAt(result, "ruleId") ?? ruleAt(rules, result["ruleIndex"]);
      const spec: DiagnosticSpec = {
        ...rangeOf(region, file, codePoints, options),
        message: stringAt(recordAt(result, "message"), "text") ?? "(no message)",
        severity: severityOf(result, rules),
        rule,
        help: rule?.startsWith("scenet/") ? RULE_REFERENCE : undefined,
      };
      found.set(file, [...(found.get(file) ?? []), spec]);
    }
  }
  return found;
}

/** A result's file: a relative uri against the run's directory, or a `file:` uri. */
function fileOf(uri: string | undefined, options: MappingOptions): string {
  if (uri === undefined) {
    return options.checkedFile;
  }
  if (uri.startsWith("file:")) {
    return fileURLToPath(uri);
  }
  let path = uri;
  try {
    path = decodeURIComponent(uri);
  } catch {
    // Not percent-encoded after all: Scenet writes plain relative paths.
  }
  return isAbsolute(path) ? path : resolve(options.cwd, path);
}

/**
 * A SARIF region as a 0-based UTF-16 range, with the defaults section 3.30 gives.
 *
 * No region, or no start line, means the result is about the file, and is shown on its
 * first line.
 */
function rangeOf(
  region: Record<string, unknown> | undefined,
  file: string,
  codePoints: boolean,
  options: MappingOptions,
): { start: Place; end: Place } {
  const startLine = Math.max((numberAt(region, "startLine") ?? 1) - 1, 0);
  const endLine = Math.max((numberAt(region, "endLine") ?? startLine + 1) - 1, startLine);
  const startText = options.lineText(file, startLine);
  const endText = endLine === startLine ? startText : options.lineText(file, endLine);

  const character = (text: string | undefined, column: number): number =>
    codePoints && text !== undefined ? utf16Offset(text, column - 1) : column - 1;

  const start = character(startText, numberAt(region, "startColumn") ?? 1);
  const endColumn = numberAt(region, "endColumn");
  // An absent end column is the end of the line, not counting its line ending.
  const end = endColumn === undefined ? (endText?.length ?? start) : character(endText, endColumn);
  return {
    start: { line: startLine, character: start },
    end: { line: endLine, character: Math.max(end, endLine === startLine ? start : 0) },
  };
}

/** The UTF-16 offset of the code point at `index` in `text`, counting past its end too. */
function utf16Offset(text: string, index: number): number {
  let offset = 0;
  let seen = 0;
  for (const codePoint of text) {
    if (seen === index) {
      return offset;
    }
    offset += codePoint.length;
    seen += 1;
  }
  return offset + Math.max(index - seen, 0);
}

/** SARIF's `level`, else the rule's default, else SARIF's own default: a warning. */
function severityOf(result: Record<string, unknown>, rules: readonly unknown[]): Severity {
  const ruleIndex = result["ruleIndex"];
  const rule = typeof ruleIndex === "number" ? rules[ruleIndex] : undefined;
  const level =
    stringAt(result, "level") ??
    stringAt(recordAt(isRecord(rule) ? rule : undefined, "defaultConfiguration"), "level") ??
    "warning";
  switch (level) {
    case "error":
      return "error";
    case "warning":
      return "warning";
    default:
      return "information";
  }
}

function ruleAt(rules: readonly unknown[], index: unknown): string | undefined {
  const rule = typeof index === "number" ? rules[index] : undefined;
  return isRecord(rule) ? stringAt(rule, "id") : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function recordAt(value: Record<string, unknown> | undefined, key: string): Record<string, unknown> | undefined {
  const field = value?.[key];
  return isRecord(field) ? field : undefined;
}

function stringAt(value: Record<string, unknown> | undefined, key: string): string | undefined {
  const field = value?.[key];
  return typeof field === "string" ? field : undefined;
}

function numberAt(value: Record<string, unknown> | undefined, key: string): number | undefined {
  const field = value?.[key];
  return typeof field === "number" && Number.isInteger(field) ? field : undefined;
}

function arrayOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : [];
}
