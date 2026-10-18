/**
 * The preview inlines every SVG a build wrote into one page, and a page has one set of ids:
 * `getElementById` -- and so `clip-path="url(#outline)"` -- finds the first. Two slanted
 * panels both define `outline`, and two pages both define `p1-frame`, so the second was
 * clipped by the first's shape. Each figure's ids are made its own.
 */

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { ownIds } from "../src/figures";

const SLANTED = (points: string): string =>
  '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" role="img" ' +
  'aria-labelledby="scenet-ab-title scenet-ab-desc">\n' +
  '  <title id="scenet-ab-title">A panel.</title>\n' +
  '  <desc id="scenet-ab-desc">Alice: see url(#outline) and id="x".</desc>\n' +
  `  <clipPath id="outline"><polygon points="${points}"/></clipPath>\n` +
  '  <g clip-path="url(#outline)"><use href="#outline"/></g>\n' +
  "</svg>\n";

/** Every id a figure defines, and every id it refers to, read from attributes. */
function idsOf(svg: string): { defined: string[]; referred: string[] } {
  const tags = svg.match(/<[^>]*>/g) ?? [];
  const defined: string[] = [];
  const referred: string[] = [];
  for (const tag of tags) {
    for (const [, id] of tag.matchAll(/\sid=["']([^"']+)["']/g)) defined.push(id ?? "");
    for (const [, id] of tag.matchAll(/url\(#([^)]+)\)/g)) referred.push(id ?? "");
    for (const [, id] of tag.matchAll(/href=["']#([^"']+)["']/g)) referred.push(id ?? "");
    for (const [, ids] of tag.matchAll(/aria-labelledby=["']([^"']+)["']/g)) {
      referred.push(...(ids ?? "").split(" "));
    }
  }
  return { defined, referred };
}

describe("ownIds", () => {
  const first = ownIds(SLANTED("0,0 10,0 8,10 0,10"), "f1-");
  const second = ownIds(SLANTED("2,0 10,0 10,10 0,10"), "f2-");

  test("no two figures share an id", () => {
    const all = [...idsOf(first).defined, ...idsOf(second).defined];
    assert.equal(new Set(all).size, all.length);
  });

  test("every reference is to an id in its own figure", () => {
    for (const svg of [first, second]) {
      const { defined, referred } = idsOf(svg);
      assert.ok(referred.length >= 4);
      for (const id of referred) assert.ok(defined.includes(id), id);
    }
  });

  test("the words are left as they are written", () => {
    assert.ok(first.includes('Alice: see url(#outline) and id="x".'));
  });

  test("an id quoted with single quotes, as an attribute holding a double quote is", () => {
    const svg = `<svg><g id='actor-a"b'/><use href='#actor-a"b'/></svg>`;
    assert.equal(ownIds(svg, "f3-"), `<svg><g id='f3-actor-a"b'/><use href='#f3-actor-a"b'/></svg>`);
  });

  test("a document with no ids is unchanged", () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1"/></svg>';
    assert.equal(ownIds(svg, "f1-"), svg);
  });
});
