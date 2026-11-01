/**
 * The bridge to the compiler.
 *
 * There is deliberately no compiler in this file, or anywhere else in this directory.
 *
 * The obvious way to build a browser playground for a DSL is to reimplement the
 * compiler in TypeScript. That forks the geometry into two codebases which then drift
 * apart, and the browser version is always the one that is subtly wrong. Pyodide ships
 * shapely, geos, numpy, pydantic and kiwisolver compiled to WebAssembly, so the actual
 * Python compiler runs unmodified and this file only moves strings across the boundary.
 *
 * The wheel installed here is the exact artefact `uv build` produces. Not a copy of the
 * source, not a browser-specific build -- the same file that goes to PyPI.
 */

import { loadPyodide, type PyodideInterface } from "pyodide";

import { decodeBase64, type DocumentFile } from "./examples";
import { FONT_FOLDER } from "./fonts";
import type { Shown } from "./options";

/**
 * The folder the playground's document is in, in Pyodide's in-memory file system. A
 * document compiled here has no file behind it; this is the folder its declared fonts
 * are read from, and the one added fonts are written into.
 */
const DOCUMENT_FOLDER = "/scenet/document";

/**
 * One problem with the source, located. The same shape `scenet check` reports, so a
 * squiggle in the editor and a line of `scenet check` output always agree.
 */
export interface Finding {
  readonly rule: string;
  readonly message: string;
  /** One-based. */
  readonly line: number;
  /** One-based. */
  readonly column: number;
  readonly endLine: number;
  /** One-based and exclusive. */
  readonly endColumn: number;
  /** An error stops the document compiling; a note reports a house limit, and does not. */
  readonly level: "error" | "note";
}

export interface CompileSuccess {
  readonly ok: true;
  readonly core: string;
  readonly notes: readonly string[];
  /** The panels' names, in the document's order. */
  readonly panels: readonly string[];
  /** How many pages it lays its panels out on: none for a panel, or a scene without `pages:`. */
  readonly pages: number;
  /** What `scenet check` says of a document that compiles: notes only, if anything. */
  readonly findings: readonly Finding[];
}

export interface CompileFailure {
  readonly ok: false;
  readonly error: string;
  /** Never empty: a failure the checker cannot place is reported on line 1. */
  readonly findings: readonly Finding[];
}

/** How the compiler reports back. Errors are data, not exceptions. */
export type CompileResult = CompileSuccess | CompileFailure;

/**
 * One picture of the last document that compiled, and its overlay: the whole of it, laid out
 * as pages or a strip, with no name; or one panel, under its own.
 */
export interface Picture {
  readonly name: string;
  readonly svg: string;
  readonly debug: string;
}

export type RenderResult =
  | { readonly ok: true; readonly pictures: readonly Picture[] }
  | { readonly ok: false; readonly error: string };

/** One panel's exports for image models, and the pose and the boxes drawn to be seen. */
export interface PanelExports {
  readonly panel: string;
  /** By the suffix `scenet build --conditioning` gives each file. */
  readonly files: Readonly<Record<string, string>>;
  /** The pose's and the boxes' pictures, by the suffix of the export each draws. */
  readonly previews: Readonly<Record<string, string>>;
}

/** Progress messages, so a twenty-second boot does not look like a hang. */
export type ProgressReporter = (message: string) => void;

interface WheelManifest {
  readonly wheel: string;
  /** Content-addressed path, so a rebuild at the same version is never served stale. */
  readonly path: string;
  readonly sha256: string;
}

/**
 * The Python side of the bridge.
 *
 * Exceptions are caught here and returned as JSON rather than allowed to cross the WASM
 * boundary. Letting them propagate loses the carefully written message, and for a
 * language playground the message is most of the value -- a diagnostic naming the
 * offending construct is the difference between a tool you can learn from and one that
 * simply says no.
 */
const BRIDGE = `
import json
import os
from pathlib import Path

# The document's folder, in Pyodide's in-memory file system. A document compiled here has
# no file behind it, so it is given this folder, and a font the author adds is written
# into its fonts/ -- where lettering: {font: fonts/Name.ttf} finds it, as it would
# beside a file on disk.
_SCENET_FOLDER = Path("${DOCUMENT_FOLDER}")
os.makedirs(_SCENET_FOLDER / "${FONT_FOLDER}", exist_ok=True)


def _scenet_check(source, kind, *, deep):
    """What \`scenet check\` finds, as the editor's findings."""
    from scenet.diagnostics import diagnose_script, diagnose_source

    diagnose = diagnose_script if kind == "script" else diagnose_source
    findings = []
    for item in diagnose(source, base=_SCENET_FOLDER, deep=deep):
        region = item.region
        findings.append({
            "rule": item.rule,
            "message": item.message,
            "line": region.start.line if region else 1,
            "column": region.start.column if region else 1,
            "endLine": region.end.line if region else 1,
            "endColumn": region.end.column if region else 2,
            "level": item.level,
        })
    return findings


def _scenet_findings(source, kind, exc):
    """Locate what is wrong, with the checker \`scenet check\` runs.

    The cheap pass first, which is what places a bad key or an unknown actor on its
    line. Layout failures only surface in a real compile, so if the cheap pass finds no
    error -- a note is not one -- it is run again with deep=True. Anything still unplaced
    goes on line 1.
    """
    try:
        findings = _scenet_check(source, kind, deep=False)
        if not any(item["level"] == "error" for item in findings):
            findings = _scenet_check(source, kind, deep=True)
    except Exception:
        findings = []

    if not any(item["level"] == "error" for item in findings):
        findings.append({
            "rule": getattr(exc, "rule", None) or type(exc).__name__,
            "message": str(exc),
            "line": 1,
            "column": 1,
            "endLine": 1,
            "endColumn": 2,
            "level": "error",
        })
    return findings


# The last document that compiled. Drawing it, its exports for image models and their ZIP
# are asked for apart from compiling it: a change of output options draws it again without
# compiling it again, and the exports are made only while a tab shows them.
_scenet_last = None


def _scenet_compile(source, kind):
    global _scenet_last
    try:
        from scenet import compile_book, compile_script

        # Compiled as \`scenet build\` compiles it, whichever kind it is.
        compile = compile_script if kind == "script" else compile_book
        book = compile(source, base=_SCENET_FOLDER)
        results = book.panels
        pages = book.pages

        names = list(results)
        single = len(names) == 1
        if pages:
            core = json.dumps(
                {
                    "pages": [json.loads(page.to_json()) for page in pages],
                    "panels": {
                        name: json.loads(result.core.to_json()) for name, result in results.items()
                    },
                },
                indent=2,
                sort_keys=True,
            )
        elif single:
            core = results[names[0]].core.to_json()
        else:
            core = json.dumps(
                {name: json.loads(result.core.to_json()) for name, result in results.items()},
                indent=2,
                sort_keys=True,
            )

        notes = []
        for name, result in results.items():
            for note in result.notes:
                notes.append(note if single else f"{name}: {note}")

        _scenet_last = book
        return json.dumps({
            "ok": True,
            "core": core,
            "notes": notes,
            "panels": names,
            "pages": len(pages),
            # A document that compiles has no error, but may have notes -- a balloon over
            # the words a publisher asks for -- which the editor shows as information.
            "findings": _scenet_check(source, kind, deep=False),
        })
    except Exception as exc:
        return json.dumps({
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "findings": _scenet_findings(source, kind, exc),
        })


def _scenet_render(live_text, shown):
    """Draw the last document that compiled: its pages, a strip, or each panel on its own."""
    try:
        from scenet.emit.debug_svg import render_debug
        from scenet.emit.page import render_pages
        from scenet.emit.strip import render_strip
        from scenet.emit.svg import render

        book = _scenet_last
        results = book.panels
        # Every declared font the panels were measured in, which is what they are drawn in.
        fonts = {
            digest: font for result in results.values() for digest, font in result.fonts.items()
        }
        # Every picture embedded: the preview is inlined into this page, and a download is
        # opened anywhere, or turned into a PNG, none of which could follow a link.
        images = book.images

        if shown == "pages":
            cores = {name: result.core for name, result in results.items()}
            pictures = [{
                "name": "",
                "svg": render_pages(
                    book.pages, cores, fonts=fonts, embed=images, live_text=live_text
                ),
                "debug": render_pages(book.pages, cores, debug=True),
            }]
        elif shown == "strip":
            pairs = [(name, result.core) for name, result in results.items()]
            pictures = [{
                "name": "",
                "svg": render_strip(pairs, fonts=fonts, embed=images, live_text=live_text),
                "debug": render_strip(pairs, debug=True),
            }]
        else:
            # Each panel on its own, as \`scenet build\` writes one SVG per panel.
            pictures = [
                {
                    "name": name,
                    "svg": render(result.core, fonts=fonts, embed=images, live_text=live_text),
                    "debug": render_debug(result.core),
                }
                for name, result in results.items()
            ]
        return json.dumps({"ok": True, "pictures": pictures})
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _scenet_conditioning():
    """Every panel's exports for image models, and the pose and the boxes drawn."""
    from scenet import render_conditioning
    from scenet.emit.preview import render_boxes_preview, render_pose_preview

    return json.dumps([
        {
            "panel": name,
            "files": dict(render_conditioning(result.core).files()),
            "previews": {
                ".pose.json": render_pose_preview(result.core),
                ".boxes.json": render_boxes_preview(result.core),
            },
        }
        for name, result in _scenet_last.panels.items()
    ])


def _scenet_archive(stem):
    """Every panel's exports in one ZIP, under the names \`build --conditioning\` gives them."""
    import base64

    from scenet.emit.export import conditioning_archive

    cores = {name: result.core for name, result in _scenet_last.panels.items()}
    return base64.b64encode(conditioning_archive(cores, stem)).decode("ascii")
`;

/** A booted compiler, ready to be handed source. */
export interface Compiler {
  compile(source: string, kind: string): Promise<CompileResult>;
  /**
   * Draw the last document that compiled.
   *
   * @param liveText - Letter with `<text>` rather than glyph outlines, as `--live-text` does.
   * @param shown - Its pages, a strip, or each panel on its own; `single` for a lone panel.
   */
  render(liveText: boolean, shown: Shown): Promise<RenderResult>;
  /** Every panel's exports for image models, of the last document that compiled. */
  conditioning(): Promise<readonly PanelExports[]>;
  /** The same as one ZIP, each file named as `scenet build --conditioning` names it. */
  archive(stem: string): Promise<Uint8Array>;
  /** Every file beside the document, as the compiler reads them. */
  files(): DocumentFile[];
  /**
   * Put a font file in the document's `fonts/` folder, replacing one of the same name.
   *
   * @param name - A safe file name, from `fontFileName`.
   * @param bytes - The file's contents.
   */
  addFont(name: string, bytes: Uint8Array): void;
  /**
   * Put a file beside the document, replacing one at the same path.
   *
   * @param path - Relative to the document's folder, as a document names it; checked by
   *   `staysInside` first.
   * @param bytes - The file's contents.
   */
  addFile(path: string, bytes: Uint8Array): void;
  readonly version: string;
}

function assetUrl(path: string): string {
  return new URL(path, document.baseURI).href;
}

/**
 * Boot Pyodide, install Scenet, and return something that compiles.
 *
 * Takes ten to twenty seconds on a first visit and is mostly download; afterwards the
 * browser cache makes it fast. Every asset comes from this origin -- there is no CDN
 * involved, which is what allows the strict Content-Security-Policy on the page.
 *
 * @param report - Called with a human-readable message at each stage of the boot.
 */
export async function bootCompiler(report: ProgressReporter): Promise<Compiler> {
  report("Starting Python…");
  const pyodide: PyodideInterface = await loadPyodide({
    indexURL: assetUrl("pyodide/"),
  });

  report("Loading numeric libraries…");
  // Built for Pyodide and served from this origin; see scripts/fetch-assets.ts.
  await pyodide.loadPackage(
    ["micropip", "numpy", "pydantic", "kiwisolver", "shapely", "fonttools", "pyyaml"],
    { messageCallback: () => undefined },
  );

  report("Installing Scenet…");
  const response = await fetch(assetUrl("wheel.json"));
  if (!response.ok) {
    throw new Error("wheel.json is missing; run `uv build --wheel` then `npm run build`");
  }
  const manifest = (await response.json()) as WheelManifest;

  const fontWheels = (await (await fetch(assetUrl("font-wheels.json"))).json()) as string[];

  pyodide.globals.set("_scenet_wheel", assetUrl(manifest.path));
  pyodide.globals.set(
    "_scenet_fonts",
    fontWheels.map((name) => assetUrl(`pyodide/${name}`)),
  );
  await pyodide.runPythonAsync(`
import micropip
# The lettering font arrives as an ordinary Python dependency rather than a system
# lookup, because measuring text identically everywhere is what makes the output
# deterministic. Both wheels are vendored at build time and served from this origin, so
# the page reaches no other host -- which is what lets the CSP say 'self' and mean it.
await micropip.install(list(_scenet_fonts))
await micropip.install(_scenet_wheel)
`);

  await pyodide.runPythonAsync(BRIDGE);
  const version = String(await pyodide.runPythonAsync("__import__('scenet').__version__"));

  return {
    version,
    async compile(source: string, kind: string): Promise<CompileResult> {
      // Passed through globals rather than interpolated into Python source. Panel text
      // is arbitrary and would otherwise need escaping, which is a bug waiting for the
      // first person who writes a quotation mark in a line of dialogue.
      pyodide.globals.set("_scenet_source", source);
      pyodide.globals.set("_scenet_kind", kind);
      const raw = await pyodide.runPythonAsync("_scenet_compile(_scenet_source, _scenet_kind)");
      return JSON.parse(String(raw)) as CompileResult;
    },
    async render(liveText: boolean, shown: Shown): Promise<RenderResult> {
      pyodide.globals.set("_scenet_live_text", liveText);
      pyodide.globals.set("_scenet_shown", shown);
      const raw = await pyodide.runPythonAsync("_scenet_render(_scenet_live_text, _scenet_shown)");
      return JSON.parse(String(raw)) as RenderResult;
    },
    async conditioning(): Promise<readonly PanelExports[]> {
      const raw = await pyodide.runPythonAsync("_scenet_conditioning()");
      return JSON.parse(String(raw)) as PanelExports[];
    },
    async archive(stem: string): Promise<Uint8Array> {
      pyodide.globals.set("_scenet_stem", stem);
      return decodeBase64(String(await pyodide.runPythonAsync("_scenet_archive(_scenet_stem)")));
    },
    files(): DocumentFile[] {
      const found: DocumentFile[] = [];
      const walk = (folder: string, prefix: string): void => {
        for (const name of pyodide.FS.readdir(folder) as string[]) {
          if (name === "." || name === "..") continue;
          const path = `${folder}/${name}`;
          if (pyodide.FS.isDir(pyodide.FS.stat(path).mode)) {
            walk(path, `${prefix}${name}/`);
          } else {
            found.push({ path: `${prefix}${name}`, bytes: pyodide.FS.readFile(path) as Uint8Array });
          }
        }
      };
      walk(DOCUMENT_FOLDER, "");
      return found;
    },
    addFont(name: string, bytes: Uint8Array): void {
      // The compiler caches fonts by what is in them, so a file replaced here under the
      // same name is read again on the next compile.
      pyodide.FS.writeFile(`${DOCUMENT_FOLDER}/${FONT_FOLDER}/${name}`, bytes);
    },
    addFile(path: string, bytes: Uint8Array): void {
      const target = `${DOCUMENT_FOLDER}/${path}`;
      pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
      pyodide.FS.writeFile(target, bytes);
    },
  };
}
