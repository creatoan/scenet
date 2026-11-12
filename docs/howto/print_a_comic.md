# Print a comic

A screen takes the SVG; a printer takes a PDF, cut to a size, with a bleed around it and the
lettering on the black plate. `scenet build --pdf` writes one beside the SVGs, from the same
drawing.

## Give the page its printed size

A page unit prints as a tenth of a millimetre. Write the trim, the size the page is cut to, as
`page.size`, and how far the printed sheet runs past it on every side as `page.bleed`, in the same
units:

```{code-block} yaml
:caption: Part of a scene document

# A US comic: 6.625 x 10.25 in, with the 0.125 in bleed US printers ask for.
page: {size: [1682.75, 2603.5], bleed: 31.75, margin: 90, gutter: 30, tier_gutter: 45}
```

| Format | `size` | `bleed` |
|---|---|---|
| US comic, 6.625 × 10.25 in | `[1682.75, 2603.5]` | `31.75` (0.125 in) |
| Tankōbon, B6, 128 × 182 mm | `[1280, 1820]` | ask the printer; `30` is 3 mm |
| The default page, 200 × 300 mm | `[2000, 3000]` | `0` |

The bleed is paper around the page: nothing on it moves, and a page without one prints at its
trim. Ask the printer for both numbers; a Franco-Belgian album, for one, varies by publisher.
A document with no pages prints each panel at its own size, at the same scale.

A panel whose art should run off the cut page says so on its placement: `bleed: true`, or the
sides, `bleed: [top, left]`. Its frame then runs out to the bleed line with no border
there, its cast is framed to the trim and its lettering kept inside the page margin, so the
cutter takes nothing but art. Such a panel needs the page's `bleed`; without one it stops at the
trim, and print notes it. See [the language reference](../reference/language/page.md#page-and-pages).

## Build it

```bash
scenet build examples/gallery/70-a-page-for-print.scene.yaml --pdf -o out/
```

That writes `out/70-a-page-for-print.pdf` beside the SVGs: one PDF page per page of the
document, or one per panel for a document with no pages. With pages, a panel on no page is not
printed. `-o` still names the SVG, and a name ending in `.pdf` there is refused. In the
[playground](https://creatoan.github.io/scenet/playground/), the Print tab shows the same PDF,
and Download saves it.

From Python, `render_pdf` returns the bytes:

```python
from scenet import compile_book, render_pdf

book = compile_book("""
cast: {a: {reference: alice}}
page: {size: [1682.75, 2603.5], bleed: 31.75}
pages: [{tiers: [{panels: [one]}]}]
panels: {one: {script: [{say: {by: a, text: "Off to the printer."}}]}}
""")
cores = {name: result.core for name, result in book.panels.items()}
pdf = render_pdf(book.pages, cores, fonts=book.fonts, images=book.images)
assert pdf.startswith(b"%PDF-1.6")
```

## What it prints in which ink

Print is told inks, not colours, and each mark is set by what it *is*:

- **Lettering, balloon borders and every line are 100% black and overprint.** A colour plate
  drifting out of register cannot blur them, and they never cut a white hole in the art under
  them.
- **The paper knocks out**: a balloon, the panel's ground, letters reversed out of a dark caption.
- **Greys are black tints**, at the K that prints their lightness under the same condition the
  colours print under, below: black's own ramp, measured through the condition's profile. A grey
  darker than black alone can print takes it all. Proof before a long run.
- **The night foreground prints rich black**, C40 K100, for even, dense coverage within any
  printer's ink limit. Small type stays 100% K.
- **A tinted palette prints in colour**: each of its colours in its CMYK twin, below. `--mono`
  prints the greys every colour was chosen against instead, as it draws them in the SVG.
- **Supplied pictures go in with their pixels unchanged.** An RGB picture stays RGB, tagged
  with the ICC's sRGB profile so the printer's RIP converts it from what a browser shows rather
  than from a guess; a JPEG and most PNGs go in as the file's own data. A picture's own `gAMA`,
  `iCCP` or `sRGB` chunk, or a JPEG's own profile, is not carried over: it is read as sRGB. A
  grey picture prints on black alone, and a CMYK JPEG as it is.
- **Every page blends in CMYK.** Rain at 85% and the veil's mask are live transparency, and each
  page says to blend it in the inks it prints in, so no RIP blends a grey into four colours.

**The colours print as one printing condition's CMYK.** Every colour a tinted palette draws -- its
twenty masses of the ladder, its veil and rain, the `warm` caption -- has a CMYK twin under
CGATS21-2-CRPC6 (GRACoL 2013, coated #1 sheetfed), converted from its sRGB colour through that
condition's profile with littleCMS: relative colorimetric, with black point compensation, which is
how a layout program converts artwork. Lettering and every line stay 100% black over them,
overprinting. A few things to know:

- **The tints, and black's ramp, were checked against the profile and on screen, never on
  paper.** No print proof was made: proof before a long run.
- **It is a US condition.** A printer on another one, FOGRA39 or FOGRA51 in Europe, re-separates
  the file for its press, as it would any artwork; that is expected, not a fault.
- **The darkest twin takes 310% ink** (the night foreground, C85 M73 Y55 K97): under GRACoL's
  limit, above the 300% some comic printers ask for.
- **Transparency blends in ink.** Rain at 85% and the veil's mask mix in CMYK on press, where the
  screen mixes them in RGB, so a composite drifts slightly from the SVG.

**The fog and cloud print as the SVG draws them.** The veil is noise the SVG draws with a filter
that PDF does not have, so print computes the same noise -- SVG 1.1's reference `feTurbulence`,
with the seed and frequencies the compiler chose -- and lays it over the veil's ink as a soft
mask, where the SVG puts it: above the masses behind the cast, below the ones in front, fading
whatever is under it rather than darkening it. It is sampled once every two page units, 127 dpi,
which prints no differently from twice as fine; a veiled panel grows by a few hundred kilobytes.

`scenet build` says, in its notes, what print leaves out or changes:

- a **colour that is none of the palette's**, which only a hand-edited Panel Core can hold,
  printed in its grey;
- a **picture below 300 dpi** at its size on the page, which is soft in print;
- with `--live-text`, a **face that may not be embedded**, whose lettering prints in outlines.

## Lettering as text

`--live-text` letters the PDF in text rather than outlines, as it letters the SVG, so the
words can be selected, searched and copied:

```sh
scenet build comic.scene.yaml --pdf --live-text
```

The letters do not move. Each face is embedded, as a subset of the glyphs it draws, and every
glyph is set where its outline would be, at the advance and kerning the solver measured. Ink is
the same 100% K, overprinting. Sound effects stay outlines: they are letters treated as picture.

A face goes in only if its licence allows it, as the font itself says in its `OS/2` table
(`fsType`). Installable, print-and-preview and editable faces are embedded, and one that may not
be subset is embedded whole. A face with a restricted licence, or one whose bitmaps alone may go
in, keeps its lettering in outlines, and a note names it. So does a CFF2 face, which a PDF 1.6 file
cannot carry. Source Sans Pro, Bangers and the gallery's Comic Neue are under the SIL Open Font
License, which lets a document embed them, whole or as a subset.

A PDF made in the playground uses its own build of fontTools, which may subset a face to
slightly different bytes than the command line does: the same letters, in the same places.

## What it does not do

- **No PDF/X conformance is claimed.** No free tool can check PDF/X-4, and none was run, so
  the file says nothing about it. It goes as far as it can without one: PDF 1.6, a TrimBox and a
  BleedBox, CMYK vectors, every font embedded, RGB pictures tagged sRGB, every page blending in
  CMYK, `/Trapped /False`, and an output intent naming GRACoL 2013, `CGATS21-2-CRPC6`, without
  embedding its profile. What PDF/X-4 still needs is dates, XMP metadata with `GTS_PDFXVersion`,
  and the condition's profile embedded. If the printer asks for PDF/X-4, convert it with Acrobat
  Pro's Preflight ("Convert to PDF/X-4"), callas pdfToolbox or Enfocus PitStop, with GRACoL 2013
  as the output condition, and let that tool's report, not Scenet, say it conforms. PDF/X-1a is
  further: rain at 85% is live transparency, and pictures are RGB.
- **No crop marks.** The TrimBox and the BleedBox carry the trim; a printer's imposition adds the
  marks.
- **No tagged text.** With `--live-text` the words can be selected and searched, but the PDF has
  no structure tree: it is not PDF/UA. Without it, lettering is outlines, as in the SVG, so no
  font is embedded and none can be missing.

## Check the plates

Ghostscript separates a PDF as a press does, one TIFF per ink, with overprint honoured:

```sh
gs -dSAFER -dBATCH -dNOPAUSE -sDEVICE=tiffsep -sCompression=none -r254 \
   -sOutputFile=plates/page.tif out/70-a-page-for-print.pdf
```

At 254 dpi a page unit is one pixel. `page(Black).tif` holds the lettering, every line and the
rich black; `page(Cyan).tif` has no hole where lettering crosses the picture, because the
lettering overprints. `qpdf --check` reads the file's structure. Both run in CI on every change
(`tests/test_print_separations.py`), which uploads the plates as an artifact.
