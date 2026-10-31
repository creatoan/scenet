/**
 * What a screen reader announces of the output: the Screen reader tab.
 *
 * The compiler makes a panel one image named by its first `<title>` -- the description, then
 * every line said in it, in reading order -- and a strip or a page a group of them (#76). None
 * of that is on screen. This walks the emitted SVG as a screen reader does and lists what it
 * would announce, so the tab shows exactly what was emitted.
 *
 * A pure function over the little of a DOM node it reads, so it is tested under Node with
 * fake nodes; the page feeds it the SVG parsed with `DOMParser`.
 */

/** What the walk reads of an element. A DOM `Element` is one. */
export interface OutlineNode {
  readonly localName: string;
  getAttribute(name: string): string | null;
  readonly children: Iterable<OutlineNode>;
  readonly textContent: string | null;
}

/** One thing announced: an image or a group, how deep it is, and its name. */
export interface OutlineEntry {
  readonly depth: number;
  readonly role: "img" | "group";
  /** Undefined for one with no name, which a screen reader announces as just its role. */
  readonly name: string | undefined;
}

/** The name an element's first `<title>` child gives it, as one line. */
function titleOf(element: OutlineNode): string | undefined {
  for (const child of element.children) {
    if (child.localName !== "title") continue;
    const words = (child.textContent ?? "").replace(/\s+/g, " ").trim();
    return words === "" ? undefined : words;
  }
  return undefined;
}

/**
 * Every image and group a screen reader announces, in document order.
 *
 * What is `aria-hidden` is skipped with everything inside it. An image's children are
 * presentational, so nothing inside one is announced. Any other element is passed through:
 * a `<g>` that only moves a panel is not announced, and neither is a shape.
 */
export function outline(root: OutlineNode): OutlineEntry[] {
  const entries: OutlineEntry[] = [];
  const walk = (element: OutlineNode, depth: number): void => {
    if (element.getAttribute("aria-hidden") === "true") return;
    const role = (element.getAttribute("role") ?? "").trim().split(/\s+/)[0];
    if (role === "img" || role === "group") {
      entries.push({ depth, role, name: titleOf(element) });
      if (role === "img") return;
      for (const child of element.children) walk(child, depth + 1);
      return;
    }
    for (const child of element.children) walk(child, depth);
  };
  walk(root, 0);
  return entries;
}
