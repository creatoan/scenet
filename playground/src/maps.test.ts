import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { composeMaps, layoutMaps, type PlacedMap } from "./maps.ts";

const svg = (width: number, height: number, body = ""): string =>
  `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${body}</svg>\n`;

const overlaps = (one: PlacedMap, other: PlacedMap): boolean =>
  one.x < other.x + other.width &&
  other.x < one.x + one.width &&
  one.y < other.y + other.height &&
  other.y < one.y + one.height;

describe("laying the maps out", () => {
  it("puts a lone map under its label, at its own size", () => {
    const layout = layoutMaps([{ name: "one", width: 1000, height: 800 }]);
    const [only] = layout.maps;
    assert.ok(only !== undefined);
    assert.equal(only.x, 0);
    assert.equal(only.width, 1000);
    assert.equal(only.height, 800);
    assert.ok(only.y >= layout.fontSize, "the label is above the map");
    assert.ok(only.labelY <= only.y && only.labelY > 0);
    assert.equal(layout.width, 1000);
    assert.equal(layout.height, only.y + 800);
  });

  it("fills rows in document order, as square a grid as the count allows", () => {
    const sized = (count: number) =>
      Array.from({ length: count }, (_, index) => ({ name: `p${index}`, width: 100, height: 100 }));
    const rows = (count: number): number[] => {
      const ys = layoutMaps(sized(count)).maps.map((map) => map.y);
      return [...new Set(ys)].map((y) => ys.filter((other) => other === y).length);
    };
    assert.deepEqual(rows(2), [2]);
    assert.deepEqual(rows(4), [2, 2]);
    assert.deepEqual(rows(5), [3, 2]);
    assert.deepEqual(rows(9), [3, 3, 3]);
    const xs = layoutMaps(sized(9)).maps.slice(0, 3).map((map) => map.x);
    assert.deepEqual(xs, [...xs].sort((one, other) => one - other), "left to right");
  });

  it("never overlaps two maps of different sizes", () => {
    const layout = layoutMaps([
      { name: "wide", width: 2000, height: 600 },
      { name: "tall", width: 500, height: 1500 },
      { name: "small", width: 300, height: 200 },
      { name: "square", width: 900, height: 900 },
      { name: "last", width: 700, height: 1000 },
    ]);
    for (const [index, one] of layout.maps.entries()) {
      for (const other of layout.maps.slice(index + 1)) {
        assert.ok(!overlaps(one, other), `${one.name} and ${other.name} overlap`);
      }
      assert.ok(one.x + one.width <= layout.width);
      assert.ok(one.y + one.height <= layout.height);
    }
  });

  it("starts a row below the tallest map of the row before", () => {
    const layout = layoutMaps([
      { name: "a", width: 100, height: 300 },
      { name: "b", width: 100, height: 100 },
      { name: "c", width: 100, height: 100 },
    ]);
    const [a, , c] = layout.maps;
    assert.ok(a !== undefined && c !== undefined);
    assert.ok(c.labelY - layout.fontSize > a.y + a.height);
  });

  it("keeps each map's name", () => {
    const names = layoutMaps([
      { name: "one", width: 10, height: 10 },
      { name: "two", width: 10, height: 10 },
    ]).maps.map((map) => map.name);
    assert.deepEqual(names, ["one", "two"]);
  });

  it("is empty for no maps", () => {
    assert.deepEqual(layoutMaps([]), { width: 0, height: 0, fontSize: 0, maps: [] });
  });
});

describe("composing the maps into one picture", () => {
  it("shows a lone map as it is: nothing to label it against", () => {
    const only = svg(400, 300, '<rect id="mass-m0"/>');
    assert.equal(composeMaps([{ name: "panel", svg: only }]), only);
  });

  it("embeds each map as an image of its own, so no id meets another map's", () => {
    const one = svg(400, 300, '<linearGradient id="ramp-0"/><rect fill="url(#ramp-0) #fff"/>');
    const two = svg(400, 300, '<linearGradient id="ramp-0"/>');
    const composed = composeMaps([
      { name: "one", svg: one },
      { name: "two", svg: two },
    ]);
    const hrefs = [...composed.matchAll(/<image [^>]*href="([^"]+)"/g)].map((match) => match[1]);
    assert.deepEqual(hrefs, [
      `data:image/svg+xml;charset=utf-8,${encodeURIComponent(one)}`,
      `data:image/svg+xml;charset=utf-8,${encodeURIComponent(two)}`,
    ]);
    assert.ok(!composed.includes('id="ramp-0"'));
  });

  it("is as large as the layout, each map where it is placed", () => {
    const maps = [
      { name: "one", svg: svg(400, 300) },
      { name: "two", svg: svg(200, 500) },
    ];
    const layout = layoutMaps([
      { name: "one", width: 400, height: 300 },
      { name: "two", width: 200, height: 500 },
    ]);
    const composed = composeMaps(maps);
    assert.match(composed, new RegExp(`^<svg [^>]*width="${layout.width}" height="${layout.height}"`));
    for (const map of layout.maps) {
      assert.ok(
        composed.includes(`x="${map.x}" y="${map.y}" width="${map.width}" height="${map.height}"`),
        map.name,
      );
    }
  });

  it("labels each map with its panel's name, escaped", () => {
    const composed = composeMaps([
      { name: "one", svg: svg(10, 10) },
      { name: 'a<b>&"c"', svg: svg(10, 10) },
    ]);
    const labels = [...composed.matchAll(/<text [^>]*>([^<]*)<\/text>/g)].map((match) => match[1]);
    assert.deepEqual(labels, ["one", "a&lt;b&gt;&amp;&quot;c&quot;"]);
  });

  it("letters the labels in the page's own colour, so they read in light and dark", () => {
    const composed = composeMaps([
      { name: "one", svg: svg(10, 10) },
      { name: "two", svg: svg(10, 10) },
    ]);
    assert.match(composed, /<text [^>]*fill="currentColor"/);
  });

  it("refuses a map with no size to place", () => {
    assert.throws(() =>
      composeMaps([
        { name: "one", svg: svg(10, 10) },
        { name: "two", svg: "<svg/>" },
      ]),
    );
  });
});
