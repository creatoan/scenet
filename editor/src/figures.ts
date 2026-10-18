/**
 * Several SVG documents inlined into one page share its ids. `getElementById`, and every
 * `url(#…)` and `href="#…"` resolved through it, finds the first element with an id, so a
 * second slanted panel was clipped by the first one's `outline`, and page 2's panels by
 * page 1's `p1-frame`. Each figure's ids, and every reference to one, get a prefix of
 * their own: what SVGO's `prefixIds` does, and what `scenet build` already does within a
 * strip or a page.
 *
 * Only tags are rewritten, never the text between them: the compiler escapes `<`, `>` and
 * `&` in every attribute and every word, so a tag runs from `<` to the next `>`, and a
 * line of dialogue that says `url(#outline)` is left saying it.
 */

/** An attribute naming one id, or several: `id`, and `aria-labelledby`. */
const NAMING = /(\s(?:id|aria-labelledby)=)(["'])(.*?)\2/g;
/** A reference by fragment: `href="#x"`, or `xlink:href`. */
const LINKING = /(\shref=|\sxlink:href=)(["'])#(.*?)\2/g;
/** A reference inside a value: `clip-path="url(#x)"`, `filter="url(#x)"`. */
const POINTING = /url\(#([^)]+)\)/g;

/**
 * The SVG with every id it defines, and every reference to one, prefixed.
 *
 * @param svg One document, as `scenet build` wrote it.
 * @param prefix What to put in front, unique in the page: `f1-`, `f2-`, ….
 */
export function ownIds(svg: string, prefix: string): string {
  return svg.replace(/<[^>]*>/g, (tag) =>
    tag
      .replace(NAMING, (_, name: string, quote: string, ids: string) => {
        const owned = ids
          .split(" ")
          .map((id) => (id === "" ? id : prefix + id))
          .join(" ");
        return `${name}${quote}${owned}${quote}`;
      })
      .replace(LINKING, (_, name: string, quote: string, id: string) => `${name}${quote}#${prefix}${id}${quote}`)
      .replace(POINTING, (_, id: string) => `url(#${prefix}${id})`),
  );
}
