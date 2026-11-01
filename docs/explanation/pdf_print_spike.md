# PDF print emitter spike (#80)

## Decision

Keep PDF emission as a third emitter over resolved Panel Core. Do not convert the SVG: the SVG has already discarded the semantic distinction between lettering, balloon borders, figure outlines and large dark masses, and it cannot express PDF overprint. The existing Page Core supplies page dimensions and resolved frames; trim and bleed should be added to page geometry rather than inferred by the emitter.

This note records the design decision and prototype findings, not a claim of PDF/X conformance. A real PDF/X claim requires a PDF/X-capable preflight run and recorded evidence.

## Candidate comparison

| Concern | ReportLab (optional `print` extra) | Small direct PDF writer |
|---|---|---|
| Licence/dependencies | BSD; acceptable under the current licence gate, but adds a runtime dependency outside the base install | No runtime dependency |
| CMYK and separations | Has colour-space and overprint APIs; mature PDF object handling | Must correctly write colour spaces, graphics state, page boxes, metadata and cross-reference data |
| Overprint | Supported with graphics-state controls; still needs inspection of the emitted PDF | Can emit `/OP`, `/op` and `/OPM` directly, but correctness is our responsibility |
| Geometry | Path API is straightforward; map each Core primitive to paths | Core primitives map to PDF path operators, but every operator and number format is ours |
| Determinism | Requires controlling metadata, document IDs, object ordering and compression behaviour; verify byte identity experimentally | Easier to control object ordering and metadata, but byte identity still needs tests for every serialization choice |
| Maintenance risk | Lower PDF-format risk; higher dependency and API coupling | No dependency, but larger security/correctness burden for a format with complex object rules |

## Print rules

- Lettering glyph outlines and balloon borders: process colour C=0, M=0, Y=0, K=100, with fill/stroke overprint enabled. Do not infer lettering from arbitrary SVG paths; emit from named Core fields.
- Neutral greys: represent as K-only tints. Preserve the resolved neutral tone ladder without RGB-to-CMYK conversion.
- Large near-black backdrop masses: use a declared rich-black recipe (initial default C=40, M=0, Y=0, K=100) only after confirming it is within the selected printer's ink limit. Keep small type at 100% K.
- Other colours: require explicit CMYK twins alongside authored sRGB values, rather than silently applying an unspecified profile.
- Page boxes: derive MediaBox, TrimBox and BleedBox from Page Core's physical page geometry. Use 0.125 in bleed only when the document/printer preset explicitly requests it; do not assume every printer uses that value.
- Metadata: derive CreationDate, ModDate and document ID from a stable content digest or `SOURCE_DATE_EPOCH`; never use wall-clock time or random identifiers.
- Fonts: outlined lettering remains the default and avoids font embedding. Live text is out of scope for the first print emitter.

## Atmosphere and conformance

The SVG atmosphere veil uses `feTurbulence`, which has no direct PDF vector equivalent. Do not pretend that it is reproduced faithfully. For the first implementation, omit the veil in print and document the limitation; keep already-resolved vector streaks and flecks. Revisit rasterising the veil only if a deterministic, licence-compatible raster path is available.

Target a constrained PDF suitable for print first, but do not label output PDF/X-1a or PDF/X-4 until a preflight tool validates it. PDF/X-1a would require CMYK/spot colours and flattened transparency; PDF/X-4 permits live transparency and requires an output intent. The first release should state its exact guarantees and limitations in the CLI and print how-to.

## Runnable prototype and findings

`tools/pdf_print_spike.py` emits the same one-page fixture with a dependency-free PDF writer
or ReportLab. It records the byte count, SHA-256, and structural checks. Run each backend
twice and compare hashes; inspect page boxes and the content stream with a PDF inspector.
ReportLab is an optional install for the spike only, not a base dependency.

The prototype comparison produced valid, readable one-page PDFs from both backends. `pdfinfo`
reported PDF 1.4 and Letter-size media pages; `pdftotext` extracted the fixture lettering;
Ghostscript parsed both with `-sDEVICE=nullpage` without errors. Both PDFs exposed the expected
TrimBox (9, 9, 603, 783), BleedBox (0, 0, 612, 792), CMYK operators and fill/stroke overprint
state. Two repeated emissions from each backend were byte-identical in the prototype run.
Direct writer output was 1,111 bytes; ReportLab output was 1,568 bytes. These figures describe
the fixed fixture, not a production renderer.

**Black-plate check (manual).** To verify that lettering lands on K alone and that colour
plates beneath it survive without knockout, run Ghostscript's `tiffsep` device:

```sh
gs -dNOPAUSE -dBATCH -sDEVICE=tiffsep \
   -sOutputFile=/tmp/spike-%d.tif \
   /tmp/scenet-direct.pdf
```

In Ghostscript's `tiffsep` device, `%d` formats the page number rather than the plate. For a
one-page document, Ghostscript writes the composite as `/tmp/spike-1.tif` and writes one separation
TIFF per colorant named after the separation: `/tmp/spike-1(Cyan).tif`, `/tmp/spike-1(Magenta).tif`,
`/tmp/spike-1(Yellow).tif`, and `/tmp/spike-1(Black).tif`. (Alternatively, `-sOutputFile=/tmp/spike.tif`
produces `/tmp/spike(Cyan).tif`, `/tmp/spike(Black).tif`, etc.).

Tested with Ghostscript 10.04.0:
- The fixture positions 100% K lettering (`0 0 0 1 k`) over a tint rectangle with no K (a plain C40 tint, `0.4 0 0 0 k`).
- **Cyan plate (`spike-1(Cyan).tif`)**: Shows the solid 40% cyan rectangular tint block with **no lettering-shaped knockout hole** beneath the lettering, proving that `/OP true` and `/OPM 1` overprinted rather than knocked out the underlying cyan channel.
- **Black plate (`spike-1(Black).tif`)**: Shows the lettering "SCENET PRINT SPIKE" and the bounding box border in 100% black over an uninked background, confirming the text lands cleanly on K alone.
- **Magenta (`spike-1(Magenta).tif`) and Yellow (`spike-1(Yellow).tif`) plates**: Completely blank (0% ink), confirming no unintended ink contamination or colour conversion occurred.
- **Composite (`spike-1.tif`)**: Displays the black lettering and border cleanly over the cyan tint.

This was a structural/parser check, **not PDF/X preflight**. No PDF/X-capable preflight tool
is available in the execution environment, so conformance, output intent, printer-specific ink
limits, and colour separations still require manual prepress validation. The fixture uses a
built-in Helvetica face and live text for simplicity; it does not yet exercise Scenet Panel
Core glyph outlines or its full range of drawing primitives.

## Implementation sequence

1. Add a `print` optional dependency group for ReportLab only if the spike's working prototype proves it materially reduces code and risk; it must remain outside base dependencies and pass the existing licence gate.
2. Prototype the same small Core fixture using ReportLab and a direct writer. Compare source size, emitted PDF object structure, overprint state, metadata stability and repeated-build byte identity.
3. Inspect both PDFs in a PDF inspector and run a print preflight tool. Record tool/version and findings before selecting the implementation. This environment/repository change does not itself perform that manual preflight, so no conformance claim is made here.
4. Add focused tests for K-only lettering, overprint graphics state, rich-black mass colour, page boxes, deterministic metadata and byte-identical repeated output.
5. Implement the chosen emitter beside `emit/svg.py`, then wire page output and `scenet build --format pdf` (or a clearly documented equivalent) through the CLI.
6. Update dependency/licence notices, CLI documentation, print how-to and determinism documentation. Keep MCP out of scope.

## Acceptance boundary

The dual-backend structural prototype now exists and has been parser-checked. The issue’s manual PDF/X preflight acceptance item remains open, as does exercising actual Panel Core output. Do not claim PDF/X conformance or start production integration until those checks resolve the implementation choice.
