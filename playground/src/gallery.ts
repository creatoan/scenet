/**
 * The order the gallery is shown and walked in, and links to an example by name.
 *
 * The manifest lists examples in the order they were added, and only ever appends: a draft
 * remembers its example by that position (`./persist`), so an entry's index never changes.
 * The order a reader meets them in is set apart from it, by the manifest's `groups:` and
 * each entry's `group:`, with the example the playground opens on (`start:`) first in its
 * group. The menu, and Previous and Next, follow that order; an index is still what the
 * menu's options carry and what a draft keeps.
 */

/** The fragment key a link to a gallery example uses: `#example=<file>`. */
const EXAMPLE_KEY = "example";

/** What ordering needs of an entry. */
export interface Grouped {
  readonly file: string;
  readonly group: string;
}

/** The gallery as `examples.json` carries it: its themes, its opening example, its entries. */
export interface Gallery<Entry extends Grouped = Grouped> {
  readonly groups: readonly string[];
  /** The index of the example the playground opens on, or -1 for none. */
  readonly start: number;
  readonly examples: readonly Entry[];
}

/** One theme of the menu: its name, and its entries' indices in the order shown. */
export interface Group {
  readonly name: string;
  readonly indices: readonly number[];
}

/**
 * The menu's groups, in the manifest's order, each holding at least one entry.
 *
 * An entry whose group the manifest does not list is still shown, in a group of its own
 * after the others: an example the menu dropped would be an example nobody can open.
 */
export function grouped(gallery: Gallery): Group[] {
  const names = [...gallery.groups];
  for (const example of gallery.examples) {
    if (!names.includes(example.group)) names.push(example.group);
  }
  const groups = names.map((name) => {
    const indices: number[] = [];
    gallery.examples.forEach((example, index) => {
      if (example.group === name) indices.push(index);
    });
    const first = indices.indexOf(gallery.start);
    if (first > 0) indices.unshift(...indices.splice(first, 1));
    return { name, indices };
  });
  return groups.filter((group) => group.indices.length > 0);
}

/** Every example's index, in the order the menu shows them. */
export function displayOrder(gallery: Gallery): number[] {
  return grouped(gallery).flatMap((group) => group.indices);
}

/**
 * The examples before and after `current` in the order shown, where there are any.
 *
 * From a document that is no example -- a shared link, a draft of your own -- there is
 * nothing before it, and the next is the first.
 */
export function neighbours(
  order: readonly number[],
  current: number,
): { previous: number | undefined; next: number | undefined } {
  const at = order.indexOf(current);
  if (at === -1) return { previous: undefined, next: order[0] };
  return { previous: order[at - 1], next: order[at + 1] };
}

/** The fragment that opens a gallery example by its file name. */
export function exampleHash(file: string): string {
  return `#${new URLSearchParams({ [EXAMPLE_KEY]: file }).toString()}`;
}

/** The file a `#example=` fragment names, if it is one. */
export function exampleNameFromHash(hash: string): string | undefined {
  const name = new URLSearchParams(hash.replace(/^#/, "")).get(EXAMPLE_KEY);
  return name === null || name === "" ? undefined : name;
}

/** The index of the example with this file name, if the gallery has it. */
export function exampleIndex(
  examples: readonly { readonly file: string }[],
  file: string,
): number | undefined {
  const index = examples.findIndex((example) => example.file === file);
  return index === -1 ? undefined : index;
}

/**
 * Where an entry's `doc:` is on the site: the same version's documentation, built.
 *
 * `doc:` names a page of `docs/` as written, `reference/language.md#camera`. Every
 * version's playground sits at `playground/` inside that version's documentation, which
 * Sphinx builds page for page into HTML -- so the header's own Documentation link is `../`.
 */
export function docHref(doc: string): string {
  const [page = "", anchor] = doc.split("#", 2);
  const built = `../${page.replace(/\.md$/, ".html")}`;
  return anchor === undefined || anchor === "" ? built : `${built}#${anchor}`;
}
