/**
 * Several panels' pictures side by side, each labelled with its panel's name.
 *
 * What the image-model tabs show for a document of several panels -- a depth map or a mask
 * per panel -- and what the Panels layout shows of the panels themselves. There is no page
 * layout here: the exports stay one per panel, as `scenet build --conditioning` writes them,
 * and this only puts them where they can all be seen at once.
 *
 * Each picture goes in as an `<image>` of its own rather than inline. Every map names its
 * regions and ramps -- `actor-alice`, `ramp-2` -- and two maps inline in one document would
 * share those ids, so the second's `url(#ramp-2)` would paint with the first's ramp. An image
 * is a document of its own, and nothing in one can reach another.
 */

import { svgSize } from "./viewport.ts";

/** A picture to place: its panel's name and its size. */
export interface MapSize {
  readonly name: string;
  readonly width: number;
  readonly height: number;
}

/** A picture placed: where it goes, and where its label goes above it. */
export interface PlacedMap extends MapSize {
  readonly x: number;
  readonly y: number;
  /** The label's baseline. */
  readonly labelY: number;
}

export interface MapLayout {
  readonly width: number;
  readonly height: number;
  /** The labels' size. */
  readonly fontSize: number;
  readonly maps: readonly PlacedMap[];
}

/** Space between two maps, as a fraction of the tallest: what a strip leaves between panels. */
const GAP_FRACTION = 0.04;

/** A label's size, as a fraction of the tallest map. */
const LABEL_FRACTION = 0.05;

function rounded(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * Lay maps out in rows, in document order, as square a grid as their count allows.
 *
 * Each row is as tall as its tallest map, under a band for the labels; the maps in it hang
 * from the top of the row. A row of three is easier to take in than a line of nine.
 */
export function layoutMaps(maps: readonly MapSize[]): MapLayout {
  if (maps.length === 0) return { width: 0, height: 0, fontSize: 0, maps: [] };
  const tallest = Math.max(...maps.map((map) => map.height));
  const gap = tallest * GAP_FRACTION;
  const fontSize = tallest * LABEL_FRACTION;
  const band = fontSize * 1.5;
  const columns = Math.ceil(Math.sqrt(maps.length));

  const placed: PlacedMap[] = [];
  let top = 0;
  let width = 0;
  for (let start = 0; start < maps.length; start += columns) {
    const row = maps.slice(start, start + columns);
    let left = 0;
    for (const map of row) {
      placed.push({
        ...map,
        x: rounded(left),
        y: rounded(top + band),
        labelY: rounded(top + fontSize),
      });
      left += map.width + gap;
    }
    width = Math.max(width, left - gap);
    top += band + Math.max(...row.map((map) => map.height)) + gap;
  }
  return { width: rounded(width), height: rounded(top - gap), fontSize: rounded(fontSize), maps: placed };
}

function escapeXml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * One SVG holding every panel's picture, labelled, or a lone picture as it is.
 *
 * The labels are lettered in `currentColor`, the page's own text colour, so they read on a
 * light page and a dark one alike.
 *
 * @throws Error A picture declares no size to place it at.
 */
export function composeMaps(maps: readonly { readonly name: string; readonly svg: string }[]): string {
  const [only] = maps;
  if (only !== undefined && maps.length === 1) return only.svg;
  const sized = maps.map((map) => {
    const size = svgSize(map.svg);
    if (size === undefined) throw new Error(`the picture of ${map.name} has no size to place it at`);
    return { name: map.name, ...size };
  });
  const layout = layoutMaps(sized);
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${layout.width}" height="${layout.height}" ` +
      `viewBox="0 0 ${layout.width} ${layout.height}">`,
  ];
  for (const [index, map] of layout.maps.entries()) {
    const href = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(maps[index]?.svg ?? "")}`;
    parts.push(
      `  <text x="${map.x}" y="${map.labelY}" font-family="sans-serif" ` +
        `font-size="${layout.fontSize}" fill="currentColor">${escapeXml(map.name)}</text>`,
      `  <image x="${map.x}" y="${map.y}" width="${map.width}" height="${map.height}" href="${href}"/>`,
    );
  }
  parts.push("</svg>");
  return `${parts.join("\n")}\n`;
}
