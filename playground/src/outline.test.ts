import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { outline, type OutlineNode } from "./outline.ts";

/** A fake element: what `outline` reads of a DOM node, and nothing else. */
function node(
  localName: string,
  attributes: Readonly<Record<string, string>> = {},
  children: readonly OutlineNode[] = [],
  text = "",
): OutlineNode {
  return {
    localName,
    getAttribute: (name) => attributes[name] ?? null,
    children,
    textContent: text + children.map((child) => child.textContent ?? "").join(""),
  };
}

const title = (text: string): OutlineNode => node("title", {}, [], text);

describe("what a screen reader announces", () => {
  it("is a panel's one image and its name", () => {
    const panel = node("svg", { role: "img" }, [title("Alice waves. Hello!"), node("g")]);
    assert.deepEqual(outline(panel), [{ depth: 0, role: "img", name: "Alice waves. Hello!" }]);
  });

  it("is a page's groups and the images in them, nested", () => {
    const pages = node("svg", { role: "group" }, [
      title("2 pages."),
      node("rect", { "aria-hidden": "true" }),
      node("g", { role: "group" }, [
        title("Page 1 of 2, 2 panels."),
        node("g", { transform: "translate(10 10)" }, [node("svg", { role: "img" }, [title("One.")])]),
        node("svg", { role: "img" }, [title("Two.")]),
      ]),
      node("g", { role: "group" }, [title("Page 2 of 2, 1 panel."), node("svg", { role: "img" }, [title("Three.")])]),
    ]);
    assert.deepEqual(outline(pages), [
      { depth: 0, role: "group", name: "2 pages." },
      { depth: 1, role: "group", name: "Page 1 of 2, 2 panels." },
      { depth: 2, role: "img", name: "One." },
      { depth: 2, role: "img", name: "Two." },
      { depth: 1, role: "group", name: "Page 2 of 2, 1 panel." },
      { depth: 2, role: "img", name: "Three." },
    ]);
  });

  it("skips whatever is hidden, and everything inside it", () => {
    const strip = node("svg", { role: "group" }, [
      title("A strip of 1 panel."),
      node("g", { "aria-hidden": "true" }, [node("svg", { role: "img" }, [title("Hidden.")])]),
      node("svg", { role: "img" }, [title("Shown.")]),
    ]);
    assert.deepEqual(
      outline(strip).map((entry) => entry.name),
      ["A strip of 1 panel.", "Shown."],
    );
  });

  it("does not look inside an image, whose children are presentational", () => {
    const panel = node("svg", { role: "img" }, [
      title("Outer."),
      node("g", { role: "group" }, [title("Inner.")]),
    ]);
    assert.deepEqual(outline(panel), [{ depth: 0, role: "img", name: "Outer." }]);
  });

  it("names an element by its first title only, its own and not a descendant's", () => {
    const panel = node("svg", { role: "img" }, [title("First."), title("Second.")]);
    assert.equal(outline(panel)[0]?.name, "First.");
    const nested = node("svg", { role: "group" }, [node("g", {}, [title("Not mine.")])]);
    assert.equal(outline(nested)[0]?.name, undefined);
  });

  it("says when an image has no name", () => {
    assert.deepEqual(outline(node("svg", { role: "img" }, [title("   ")])), [
      { depth: 0, role: "img", name: undefined },
    ]);
  });

  it("reads a title's words as one line", () => {
    assert.equal(outline(node("svg", { role: "img" }, [title("  Alice\n  says  hi. ")]))[0]?.name, "Alice says hi.");
  });

  it("reads the first of several roles, as a browser does", () => {
    assert.equal(outline(node("svg", { role: "img graphics-document" }, [title("A.")]))[0]?.role, "img");
  });

  it("is nothing for markup written with no accessibility", () => {
    assert.deepEqual(outline(node("svg", {}, [node("g", {}, [node("path")])])), []);
  });
});
