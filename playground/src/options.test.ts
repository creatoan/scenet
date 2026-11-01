import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  chosenLayout,
  DEFAULT_OPTIONS,
  loadOptions,
  offeredLayouts,
  saveOptions,
  type OutputOptions,
} from "./options.ts";
import type { KeyValueStore } from "./persist.ts";

class MemoryStore implements KeyValueStore {
  readonly items = new Map<string, string>();
  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }
  removeItem(key: string): void {
    this.items.delete(key);
  }
}

const BROKEN: KeyValueStore = {
  getItem: () => {
    throw new Error("SecurityError");
  },
  setItem: () => {
    throw new Error("QuotaExceededError");
  },
  removeItem: () => {
    throw new Error("SecurityError");
  },
};

describe("the layouts a document offers", () => {
  it("are none for a lone panel, which is shown as it is", () => {
    assert.deepEqual(offeredLayouts({ pages: 0, panels: 1 }), []);
  });

  it("are its pages, for a lone panel on a page", () => {
    assert.deepEqual(offeredLayouts({ pages: 1, panels: 1 }), ["pages"]);
  });

  it("are a strip or each panel on its own, for panels with no pages", () => {
    assert.deepEqual(offeredLayouts({ pages: 0, panels: 3 }), ["strip", "panels"]);
  });

  it("are all three, for panels laid out on pages", () => {
    assert.deepEqual(offeredLayouts({ pages: 2, panels: 5 }), ["pages", "strip", "panels"]);
  });
});

describe("the layout shown", () => {
  it("is the one asked for, when the document offers it", () => {
    assert.equal(chosenLayout("panels", ["pages", "strip", "panels"]), "panels");
  });

  it("is the first the document offers otherwise: pages, if it has them", () => {
    assert.equal(chosenLayout("pages", ["strip", "panels"]), "strip");
    assert.equal(chosenLayout("strip", ["pages"]), "pages");
  });

  it("is the panel itself, for a lone panel", () => {
    assert.equal(chosenLayout("strip", []), "single");
  });
});

describe("the output options, remembered", () => {
  it("default to glyph outlines and pages, as `scenet build` writes", () => {
    assert.deepEqual(DEFAULT_OPTIONS, { liveText: false, layout: "pages" });
    assert.deepEqual(loadOptions(new MemoryStore()), DEFAULT_OPTIONS);
  });

  it("come back as they were saved", () => {
    const store = new MemoryStore();
    const options: OutputOptions = { liveText: true, layout: "panels" };
    saveOptions(store, options);
    assert.deepEqual(loadOptions(store), options);
  });

  it("fall back field by field on anything damaged", () => {
    const store = new MemoryStore();
    for (const [raw, expected] of [
      ["not json", DEFAULT_OPTIONS],
      ["[]", DEFAULT_OPTIONS],
      ['{"liveText": "yes", "layout": "strip"}', { liveText: false, layout: "strip" }],
      ['{"liveText": true, "layout": "sideways"}', { liveText: true, layout: "pages" }],
    ] as const) {
      store.items.set("scenet.playground.options", raw);
      assert.deepEqual(loadOptions(store), expected, raw);
    }
  });

  it("survive storage that refuses everything", () => {
    assert.deepEqual(loadOptions(BROKEN), DEFAULT_OPTIONS);
    assert.doesNotThrow(() => saveOptions(BROKEN, DEFAULT_OPTIONS));
    assert.deepEqual(loadOptions(undefined), DEFAULT_OPTIONS);
  });
});
