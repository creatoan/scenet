/**
 * What the checker and the compiler say of a document that compiles: the list of notes
 * over the picture (#240).
 *
 * Two kinds of note reach it. `scenet check` notes a house limit where it is written -- a
 * balloon over the words a publisher asks for, a page whose count its panels do not match --
 * and the compiler notes what it decided that the source did not literally ask for: a
 * camera that retreated, a tail that bent. A check's note has a place, and its row puts the
 * cursor there; a compile note names its panel, in a document of several. Each row says its
 * rule or its name, which is what a gallery entry's `notes:` declares.
 */

import type { CompileNote, Finding } from "./compiler";

/** Where a row puts the cursor: one-based, as a finding says it. */
export interface Place {
  readonly line: number;
  readonly column: number;
}

/** One row of the list. */
export interface NoteRow {
  /** `line:column` for a check's note; a compile note's panel, in a document of several. */
  readonly where: string;
  readonly rule: string;
  readonly message: string;
  /** Where the cursor goes when the row is chosen: a check's note only. */
  readonly at?: Place;
}

/**
 * The rows, the checker's notes first in the order it gives them, which is the source's,
 * then the compiler's, panel by panel.
 *
 * @param findings - What `scenet check` found; an error among them is no note, and is left
 *   out, though a document that compiles has none.
 * @param notes - What the compiler noted.
 */
export function noteRows(findings: readonly Finding[], notes: readonly CompileNote[]): NoteRow[] {
  const checked = findings
    .filter((finding) => finding.level === "note")
    .map((finding) => ({
      where: `${finding.line}:${finding.column}`,
      rule: finding.rule,
      message: finding.message,
      at: { line: finding.line, column: finding.column },
    }));
  const compiled = notes.map((note) => ({
    where: note.panel ?? "",
    rule: note.rule,
    message: note.message,
  }));
  return [...checked, ...compiled];
}
