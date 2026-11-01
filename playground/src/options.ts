/**
 * The output options: what `scenet build` would be told on the command line.
 *
 * Live text letters with `<text>` rather than glyph outlines (`--live-text`). The layout is
 * how a document of several panels is shown: its pages, a strip (`--strip`), or each panel on
 * its own, as `build` writes one SVG per panel. They are this viewer's choice, remembered in
 * this browser and nowhere else: a share link carries the document, not how it is looked at.
 */

import type { KeyValueStore } from "./persist.ts";

export type Layout = "pages" | "strip" | "panels";

/** What is shown: a layout, or the panel itself when there is nothing to lay out. */
export type Shown = Layout | "single";

export interface OutputOptions {
  readonly liveText: boolean;
  /** The layout asked for; a document that does not offer it is shown as it can be. */
  readonly layout: Layout;
}

/** What `scenet build` writes with no flags: glyph outlines, and the pages. */
export const DEFAULT_OPTIONS: OutputOptions = { liveText: false, layout: "pages" };

const LAYOUTS: readonly Layout[] = ["pages", "strip", "panels"];

const KEY = "scenet.playground.options";

/**
 * The layouts a document offers, in the order the menu lists them.
 *
 * Pages if it has any; a strip, or each panel on its own, if it has more than one panel. A
 * lone panel with no page offers none: it is shown as it is.
 */
export function offeredLayouts(shape: { readonly pages: number; readonly panels: number }): Layout[] {
  return [...(shape.pages > 0 ? (["pages"] as const) : []), ...(shape.panels > 1 ? (["strip", "panels"] as const) : [])];
}

/** The layout shown: the one asked for if the document offers it, else the first it does. */
export function chosenLayout(preferred: Layout, offered: readonly Layout[]): Shown {
  return offered.includes(preferred) ? preferred : (offered[0] ?? "single");
}

/** The options remembered, field by field: anything unreadable is the default. */
export function loadOptions(store: KeyValueStore | undefined): OutputOptions {
  let raw: unknown;
  try {
    raw = JSON.parse(store?.getItem(KEY) ?? "null");
  } catch {
    return DEFAULT_OPTIONS;
  }
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return DEFAULT_OPTIONS;
  const { liveText, layout } = raw as Record<string, unknown>;
  return {
    liveText: typeof liveText === "boolean" ? liveText : DEFAULT_OPTIONS.liveText,
    layout: LAYOUTS.find((known) => known === layout) ?? DEFAULT_OPTIONS.layout,
  };
}

export function saveOptions(store: KeyValueStore | undefined, options: OutputOptions): void {
  try {
    store?.setItem(KEY, JSON.stringify(options));
  } catch {
    // Not remembered, then: the options still apply until the page is closed.
  }
}
